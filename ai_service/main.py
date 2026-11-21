"""SunPower AI microservice.

FastAPI app that Odoo calls over HTTP (default http://localhost:8000).

Models are tried in this order:
  1. Hugging Face Inference Providers (remote): only if HF_TOKEN has credits; optional.
  2. Free local CPU models (local_models.py): Qwen2.5-1.5B, whisper-small, MiniLM, RapidOCR.
  3. Deterministic fallbacks (regex / knowledge base) where that still gives a useful answer.

Every endpoint returns JSON. If nothing can produce an answer, the response is a non-2xx
status with body:
    {"ok": false, "error": {"code": "...", "message": "...", "model": "..."},
     "fallback": "manual_entry"}
so Odoo can fall back to manual data entry.
"""
from __future__ import annotations

import os

# Plain HTTP downloads were ~10x faster than the Xet protocol on this network; must be set
# before huggingface_hub is imported. Override with HF_HUB_DISABLE_XET=0.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import asyncio
import base64
import contextvars
import io
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from huggingface_hub import InferenceClient
from PIL import Image
from pydantic import BaseModel

import local_models as lm

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")  # project root .env
load_dotenv(BASE_DIR / ".env")         # optional local override

HF_TOKEN = os.getenv("HF_TOKEN")
TIMEOUT_S = float(os.getenv("AI_TIMEOUT", "60"))

# Remote models: primary first, then fallbacks (tried in order on failure).
VLM_MODELS = ["Qwen/Qwen2.5-VL-7B-Instruct", "Qwen/Qwen3-VL-8B-Instruct", "Qwen/Qwen2.5-VL-72B-Instruct"]
VLM_MODEL = VLM_MODELS[0]
LLM_MODELS = ["Qwen/Qwen2.5-7B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "Qwen/Qwen2.5-72B-Instruct"]
ASR_MODEL = "openai/whisper-large-v3"
EMBED_MODELS = ["BAAI/bge-m3", "sentence-transformers/all-MiniLM-L6-v2"]
DEFECT_REPO = "Swarmdrones/convnext-solar-panel-defect-classifier-v1"
CLIP_MODEL = "openai/clip-vit-base-patch32"
# Display labels (title case, as Odoo expects)
DEFECT_LABELS = ["Bird-drop", "Clean", "Dusty", "Electrical-damage", "Physical-damage", "Snow-covered"]

log = logging.getLogger("sunpower_ai")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

client = InferenceClient(token=HF_TOKEN, timeout=TIMEOUT_S)

# Remote inference is an optional first try. AI_REMOTE=off disables it entirely.
# After a credits/auth failure it is skipped for AI_REMOTE_COOLDOWN seconds, so requests
# go straight to the local models instead of paying for a failed round-trip each time.
AI_REMOTE = os.getenv("AI_REMOTE", "auto").lower()
REMOTE_COOLDOWN = float(os.getenv("AI_REMOTE_COOLDOWN", "900"))
_remote_blocked_until = 0.0
_remote_block_reason: str | None = None


def remote_ok() -> bool:
    return bool(HF_TOKEN) and AI_REMOTE != "off" and time.time() >= _remote_blocked_until


def _trip_remote(reason: str) -> None:
    global _remote_blocked_until, _remote_block_reason
    _remote_blocked_until = time.time() + REMOTE_COOLDOWN
    _remote_block_reason = reason
    log.warning("remote inference disabled for %ds: %s", REMOTE_COOLDOWN, reason)


# ---------------------------------------------------------------- status ---
MODEL_STATUS: dict[str, dict[str, Any]] = {}


def _mark(model: str, ok: bool, err: str | None = None, code: str | None = None) -> None:
    MODEL_STATUS[model] = {"available": ok, "error_code": None if ok else code,
                           "last_checked": int(time.time()), "last_error": err}


class AIError(Exception):
    def __init__(self, code: str, message: str, status: int = 502, model: str | None = None):
        super().__init__(message)
        self.code, self.message, self.status, self.model = code, message, status, model


# Per-request deadline so chained fallbacks never exceed the overall budget.
_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar("deadline", default=None)


def start_deadline(seconds: float = TIMEOUT_S) -> None:
    _deadline.set(time.monotonic() + seconds)


def remaining(default: float = TIMEOUT_S) -> float:
    dl = _deadline.get()
    return default if dl is None else dl - time.monotonic()


def _safe(fn: Callable[[], Any]) -> Callable[[], Any]:
    def inner():
        try:
            return fn()
        except StopIteration:  # e.g. no provider for a task; must not reach the future
            raise RuntimeError("no inference provider serves this model for this task")
    return inner


def _classify(msg: str, status: int | None = None) -> tuple[str, int]:
    """Map a provider failure to (error_code, http_status). Prefer the real HTTP status."""
    low = msg.lower()
    if status == 402 or "pre-paid credits" in low:
        return "provider_credits_exhausted", 402
    if "model_not_supported" in low or "not supported by any provider" in low or "no inference provider" in low:
        return "model_not_served", 502
    if status in (401, 403):
        return "auth_error", 502
    if status in (408, 504):
        return "timeout", 504
    return "provider_error", 502


def _http_status(e: Exception) -> int | None:
    return getattr(getattr(e, "response", None), "status_code", None)


async def call_model(model: str, fn: Callable[[], Any], timeout: float = TIMEOUT_S) -> Any:
    """Run a blocking remote HF call in a thread under the request deadline; map errors to AIError."""
    timeout = min(timeout, remaining(timeout))
    if timeout <= 0.5:
        raise AIError("timeout", f"request exceeded its {int(TIMEOUT_S)}s budget before trying {model}", 504, model)
    try:
        result = await asyncio.wait_for(asyncio.to_thread(_safe(fn)), timeout=timeout)
        _mark(model, True)
        return result
    except asyncio.TimeoutError:
        _mark(model, False, "timeout", "timeout")
        raise AIError("timeout", f"{model} did not respond within {int(timeout)}s", 504, model)
    except AIError:
        raise
    except Exception as e:  # provider/network failure
        msg = f"{type(e).__name__}: {str(e)[:300]}"
        code, status = _classify(msg, _http_status(e))
        _mark(model, False, msg, code)
        if code in ("provider_credits_exhausted", "auth_error"):
            _trip_remote(code)
        raise AIError(code, msg, status, model)


async def call_local(name: str, fn: Callable[[], Any], timeout: float = TIMEOUT_S) -> Any:
    """Run a local (CPU) model call in a thread under the request deadline."""
    timeout = min(timeout, remaining(timeout))
    if timeout <= 0.5:
        raise AIError("timeout", f"request exceeded its {int(TIMEOUT_S)}s budget before trying {name}", 504, name)
    try:
        result = await asyncio.wait_for(asyncio.to_thread(fn), timeout=timeout)
        _mark(name, True)
        return result
    except asyncio.TimeoutError:
        _mark(name, False, "timeout", "timeout")
        raise AIError("timeout", f"local model {name} did not finish within {int(timeout)}s", 504, name)
    except ValueError as e:  # bad input detected by a local pipeline (e.g. undecodable audio)
        raise AIError("invalid_input", str(e)[:300], 422, name)
    except Exception as e:
        msg = f"{type(e).__name__}: {str(e)[:300]}"
        _mark(name, False, msg, "local_model_error")
        raise AIError("local_model_error", msg, 503, name)


# ------------------------------------------------------------------- app ---
app = FastAPI(title="SunPower AI Service", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8069", "http://127.0.0.1:8069"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def err_response(code: str, message: str, status: int, model: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "ok": False,
        "error": {"code": code, "message": message, "model": model},
        "fallback": "manual_entry",
    })


@app.exception_handler(AIError)
async def _ai_error_handler(_: Request, exc: AIError):
    return err_response(exc.code, exc.message, exc.status, exc.model)


@app.exception_handler(RequestValidationError)
async def _validation_handler(_: Request, exc: RequestValidationError):
    return err_response("invalid_input", str(exc.errors())[:500], 422)


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception):
    log.exception("unhandled error")
    return err_response("internal_error", f"{type(exc).__name__}: {str(exc)[:300]}", 500)


# --------------------------------------------------------------- helpers ---
def extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM reply (handles ```json fences)."""
    if not text:
        raise AIError("bad_model_output", "empty model output", 502)
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    if start < 0:
        raise AIError("bad_model_output", f"no JSON in model output: {text[:200]}", 502)
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                blob = text[start:i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    fixed = re.sub(r",\s*([}\]])", r"\1", blob)  # trailing commas
                    try:
                        return json.loads(fixed)
                    except json.JSONDecodeError:
                        raise AIError("bad_model_output", f"unparseable JSON: {blob[:200]}", 502)
    raise AIError("bad_model_output", f"unterminated JSON: {text[start:start + 200]}", 502)


def to_float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v).replace(",", ""))
    return float(m.group()) if m else None


def to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in {"null", "none", "n/a", "na", "unknown"} else None


def to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"true", "yes", "1", "y", "haan", "ha"}


async def chat_remote(messages: list[dict], max_tokens: int, models: list[str]) -> tuple[str, str]:
    """Remote chat completion over a model fallback chain. Returns (text, model_used)."""
    last: AIError | None = None
    for model in models:
        if not remote_ok():
            break
        try:
            resp = await call_model(model, lambda m=model: client.chat_completion(
                model=m, messages=messages, max_tokens=max_tokens, temperature=0.1))
            return resp.choices[0].message.content or "", model
        except AIError as e:
            log.warning("remote %s failed: %s", model, e.message)
            last = e
            if e.code == "timeout":
                break
    raise last or AIError("remote_disabled", "remote inference disabled or unavailable", 503)


async def chat_llm(messages: list[dict], max_tokens: int = 400, models: list[str] | None = None,
                   local_tokens: int | None = None) -> tuple[str, str]:
    """Remote chain first (only when credits/token work), then the free local LLM."""
    if remote_ok():
        try:
            return await chat_remote(messages, max_tokens, models or LLM_MODELS)
        except AIError as e:
            log.info("falling back to local LLM after remote failure (%s)", e.code)
    budget = remaining()
    text = await call_local(lm.LLM_ID, lambda: lm.llm_chat(
        messages, max_new_tokens=local_tokens or max_tokens, max_time=budget - 1.5))
    return text, f"local:{lm.LLM_ID}"


async def read_image(upload: UploadFile) -> tuple[bytes, Image.Image]:
    data = await upload.read()
    if not data:
        raise AIError("invalid_input", "empty image upload", 422)
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return data, img.convert("RGB")
    except Exception:
        raise AIError("invalid_input", "uploaded file is not a readable image", 422)


def image_data_url(img: Image.Image, max_side: int = 1600) -> str:
    img = img.copy()
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ------------------------------------------------------------ /bill/parse ---
BILL_PROMPT = """You are reading an Indian electricity bill image. Extract these fields and reply with ONLY a JSON object:
{"consumer_no": string or null, "discom": string or null (the electricity distribution company name, e.g. BSES Rajdhani, TPDDL, MSEDCL, BESCOM),
 "monthly_units_kwh": number or null (units consumed in this billing month, kWh; if the bill covers 2 months, divide by 2),
 "bill_amount": number or null (total amount payable in INR),
 "sanctioned_load_kw": number or null (sanctioned/contract load in kW; convert kVA ~ kW)}
Use null for anything not visible. Numbers only, no units or currency symbols."""

BILL_TEXT_PROMPT = """Below is OCR text from an Indian electricity bill. Extract the fields and reply with ONLY a JSON object:
{"consumer_no": string or null, "discom": string or null (electricity company name),
 "monthly_units_kwh": number or null (units consumed in this bill; if it covers 2 months, divide by 2),
 "bill_amount": number or null (total amount payable, INR), "sanctioned_load_kw": number or null}
Use null if a value is not present. Numbers only.

OCR text:
<<<
@@TEXT@@
>>>"""

BILL_FIELDS = ("consumer_no", "discom", "monthly_units_kwh", "bill_amount", "sanctioned_load_kw")


@app.post("/bill/parse")
async def bill_parse(file: UploadFile = File(...)):
    start_deadline()
    _, img = await read_image(file)
    data: dict = {}
    model = method = None
    warnings: list[str] = []
    ocr = ""
    # 1) optional remote vision model (only when HF credits work)
    if remote_ok():
        try:
            messages = [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": image_data_url(img)}},
                {"type": "text", "text": BILL_PROMPT}]}]
            raw, model = await chat_remote(messages, 400, VLM_MODELS)
            data, method = extract_json(raw), "remote_vlm"
        except AIError as e:
            log.info("remote VLM unavailable (%s); using local OCR", e.code)
    # 2) local: OCR -> regex (instant) + small LLM to fill the gaps
    if not data:
        work = img.copy()
        if max(work.size) > 2000:
            work.thumbnail((2000, 2000))
        ocr = await call_local(lm.OCR_ID, lambda: lm.ocr_text(work), timeout=40)
        if not ocr.strip():
            raise AIError("unreadable_image", "no text found on the image; please enter bill details manually",
                          422, lm.OCR_ID)
        rx = lm.regex_bill(ocr)
        data, method, model = dict(rx), "ocr+regex", None
        if any(rx.get(k) in (None, "") for k in BILL_FIELDS):
            try:
                raw, model = await chat_llm(
                    [{"role": "user", "content": BILL_TEXT_PROMPT.replace("@@TEXT@@", ocr[:2500])}],
                    max_tokens=200, local_tokens=120)
                llm = extract_json(raw)
                # regex wins where it matched a printed label; the LLM fills the rest
                data = {k: rx.get(k) if rx.get(k) not in (None, "") else llm.get(k) for k in BILL_FIELDS}
                method = "ocr+regex+llm"
            except AIError as e:
                warnings.append(f"LLM step skipped ({e.code}); fields from OCR pattern matching only")
                model = None
    units = to_float(data.get("monthly_units_kwh"))
    rec_kw = int(min(5, max(1, round(units / 120)))) if units else None
    resp = {
        "ok": True,
        "consumer_no": to_str(data.get("consumer_no")),
        "discom": to_str(data.get("discom")),
        "monthly_units_kwh": units,
        "bill_amount": to_float(data.get("bill_amount")),
        "sanctioned_load_kw": to_float(data.get("sanctioned_load_kw")),
        "recommended_kw": rec_kw,
        "recommended_type": "on_grid",
        "model": model,
        "method": method,
    }
    if ocr:
        resp["ocr_text"] = ocr[:2000]
    if warnings:
        resp["warning"] = "; ".join(warnings)
    return resp


# ------------------------------------------------------------ /lead/parse ---
LEAD_PROMPT = """You extract CRM data for a rooftop solar company in India from a customer message
(email, WhatsApp text or call transcript). The message may be in English, Hindi (Devanagari) or Hinglish.
Reply with ONLY a JSON object with exactly these keys:
{"intent": "new_enquiry" | "complaint" | "other",
 "name": string or null, "phone": string or null (digits, keep +91 if given), "email": string or null,
 "street": string or null, "city": string or null,
 "system_kw": number or null (requested system size in kW),
 "system_type": "on_grid" | "off_grid" (default "on_grid"; off_grid if they want battery backup / no grid),
 "subsidy": true | false (true if they mention subsidy / PM Surya Ghar / sarkari yojana),
 "monthly_bill": number or null (monthly electricity bill in INR),
 "summary": string (one-line English summary)}
intent = complaint if an existing customer reports a problem (not working, kam units, inverter error, etc).
Write names and cities in English letters (transliterate Hindi).

Message:
<<<
@@TEXT@@
>>>"""


_PLACEHOLDERS = {"customer", "name", "user", "client", "sir", "madam", "john doe", "jane doe", "your name",
                 "123 main street", "main street", "street", "city", "address"}


def _ground_lead(d: dict, rx: dict, transcript: str) -> None:
    """Guard against small-model hallucinations (in place).

    - intent: keyword rules win when they fire (small models over-predict "complaint").
    - numbers: must be in a plausible range, otherwise the regex value (or null).
    - name/street/city: for Latin-script messages the value must actually occur in the text;
      Devanagari messages are exempt because the model is asked to transliterate them.
    """
    if rx.get("intent"):
        d["intent"] = rx["intent"]
    if rx.get("system_type"):
        d["system_type"] = rx["system_type"]
    for key, lo, hi in (("system_kw", 0.5, 500), ("monthly_bill", 100, 500000)):
        v = to_float(d.get(key))
        if v is None or not (lo <= v <= hi):
            r = rx.get(key)
            d[key] = r if r is not None and lo <= r <= hi else None
    latin = not re.search(r"[ऀ-ॿ]", transcript)
    low = transcript.lower()
    for key in ("name", "street", "city"):
        v = to_str(d.get(key))
        if not v or v.lower() in _PLACEHOLDERS:
            d[key] = None
        elif latin:
            words = [w for w in re.findall(r"[a-z0-9]+", v.lower()) if len(w) > 2]
            if not words or not all(w in low for w in words):
                d[key] = None


def _lead_summary(intent: str, d: dict, stype: str, transcript: str = "") -> str:
    """One-line English summary built from extracted fields (small local models often omit it)."""
    who = " ".join(x for x in (to_str(d.get("name")), f"({to_str(d.get('city'))})" if to_str(d.get("city")) else None) if x)
    if intent == "complaint":
        latin = not re.search(r"[ऀ-ॿ]", transcript)
        gist = re.sub(r"\s+", " ", transcript).strip()[:120] if latin else "service issue reported"
        return f"Complaint from {who or 'customer'}: {gist}"
    bits = []
    kw = to_float(d.get("system_kw"))
    bits.append(f"{kw:g} kW {stype.replace('_', '-')} system" if kw else f"{stype.replace('_', '-')} solar system")
    bill = to_float(d.get("monthly_bill"))
    if bill:
        bits.append(f"monthly bill Rs {bill:,.0f}")
    if to_bool(d.get("subsidy")):
        bits.append("asked about subsidy")
    head = "New solar enquiry" if intent == "new_enquiry" else "Customer message"
    return f"{head}{' from ' + who if who else ''}: " + ", ".join(bits)


@app.post("/lead/parse")
async def lead_parse(text: Optional[str] = Form(None), audio: Optional[UploadFile] = File(None)):
    start_deadline()
    transcript = (text or "").strip()
    asr_model = None
    if audio is not None and audio.filename:
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise AIError("invalid_input", "empty audio upload", 422)
        heard = None
        if remote_ok():
            try:
                out = await call_model(ASR_MODEL, lambda: client.automatic_speech_recognition(audio_bytes, model=ASR_MODEL))
                heard = (getattr(out, "text", None) or (out.get("text") if isinstance(out, dict) else str(out)) or "").strip()
                asr_model = ASR_MODEL
            except AIError as e:
                log.info("remote ASR unavailable (%s); using local whisper", e.code)
        if heard is None:
            heard = await call_local(lm.ASR_ID, lambda: lm.transcribe(audio_bytes))
            asr_model = f"local:{lm.ASR_ID}"
        transcript = f"{text.strip()}\n{heard}" if text else heard
    if not transcript:
        raise AIError("invalid_input", "provide form field 'text' or multipart file 'audio'", 422)

    rx = lm.regex_lead(transcript)
    warning = None
    try:
        raw, model = await chat_llm([{"role": "user", "content": LEAD_PROMPT.replace("@@TEXT@@", transcript[:4000])}],
                                    max_tokens=400, local_tokens=200)
        d = extract_json(raw)
        # pattern matches are exact for phone/email; prefer them over a small model's copy
        for k in ("phone", "email"):
            if rx.get(k):
                d[k] = rx[k]
        for k in ("system_kw", "monthly_bill"):
            if to_float(d.get(k)) is None and rx.get(k) is not None:
                d[k] = rx[k]
        if rx.get("subsidy"):
            d["subsidy"] = True
    except AIError as e:
        d, model = dict(rx), None
        warning = f"LLM unavailable ({e.code}); name/address not extracted, other fields from pattern matching"
    _ground_lead(d, rx, transcript)
    intent = str(d.get("intent") or "other").lower().strip()
    if intent not in {"new_enquiry", "complaint", "other"}:
        intent = "other"
    stype = str(d.get("system_type") or "on_grid").lower().replace("-", "_").replace(" ", "_")
    stype = "off_grid" if "off" in stype else "on_grid"
    phone = to_str(d.get("phone"))
    if phone:
        phone = re.sub(r"[^\d+]", "", phone) or None
    resp = {
        "ok": True,
        "intent": intent,
        "name": to_str(d.get("name")),
        "phone": phone,
        "email": to_str(d.get("email")),
        "street": to_str(d.get("street")),
        "city": to_str(d.get("city")),
        "system_kw": to_float(d.get("system_kw")),
        "system_type": stype,
        "subsidy": to_bool(d.get("subsidy")),
        "monthly_bill": to_float(d.get("monthly_bill")),
        "summary": to_str(d.get("summary")) or _lead_summary(intent, d, stype, transcript),
        "transcript": transcript,
        "model": model,
        "asr_model": asr_model,
    }
    if warning:
        resp["warning"] = warning
    return resp


# --------------------------------------------------------- /fault/diagnose ---
KB: list[dict] = json.loads((BASE_DIR / "kb" / "fault_codes.json").read_text(encoding="utf-8"))
_kb_lock = threading.Lock()
_kb_emb: dict[str, np.ndarray] = {}  # model -> (N, D) normalized


def kb_doc(e: dict) -> str:
    return f"{e['title']}. Codes: {', '.join(e['codes'])}. {e['symptoms']} Causes: {'; '.join(e['causes'])}"


def _normalize(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    if m.ndim == 3:  # token-level output -> mean pool
        m = m.mean(axis=1)
    if m.ndim == 1:
        m = m[None, :]
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


async def embed(texts: list[str], model: str) -> np.ndarray:
    out = await call_model(model, lambda: client.feature_extraction(texts if len(texts) > 1 else texts[0], model=model))
    return _normalize(np.asarray(out))


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def keyword_rank(query: str, code: str) -> list[tuple[float, int]]:
    q = _tokens(query)
    scores = []
    for i, e in enumerate(KB):
        s = len(q & _tokens(kb_doc(e))) / (len(q) + 1)
        if code and any(code.strip().lower() == c.lower() for c in e["codes"]):
            s += 1.0
        scores.append((s, i))
    return sorted(scores, reverse=True)


def code_boost(code: str) -> np.ndarray:
    b = np.zeros(len(KB), dtype=np.float32)
    if code:
        c = code.strip().lower()
        for i, e in enumerate(KB):
            if any(c == a.lower() for a in e["codes"]):
                b[i] = 0.3
    return b


class FaultIn(BaseModel):
    fault_code: Optional[str] = ""
    description: Optional[str] = ""
    inverter_brand: Optional[str] = ""


FAULT_PROMPT = """You are a senior solar O&M engineer helping a field technician in India.
Inverter brand: {brand}
Reported fault code: {code}
Technician/customer description: {desc}

Relevant knowledge-base entries (most relevant first):
{context}

Using the knowledge base (and general inverter knowledge only if needed), reply with ONLY a JSON object:
{{"likely_cause": string (one or two sentences),
  "steps": [3 to 6 short, SAFE field troubleshooting steps in order; always isolate AC and DC before touching wiring],
  "needs_site_visit": true | false,
  "likely_parts": [list of parts that may need replacement, empty if none],
  "confidence": number between 0 and 1}}"""


SAFETY_STEP = ("Safety first: switch the AC breaker and DC isolator OFF and wait 5 minutes before touching "
               "any wiring; PV strings stay live in daylight, so wear insulated gloves.")


@app.post("/fault/diagnose")
async def fault_diagnose(body: FaultIn):
    start_deadline()
    code = (body.fault_code or "").strip()
    desc = (body.description or "").strip()
    brand = (body.inverter_brand or "").strip()
    if not code and not desc:
        raise AIError("invalid_input", "provide fault_code and/or description", 422)
    query = f"Fault code {code}. {desc}".strip()

    retrieval = "keyword"
    ranked: list[tuple[float, int]] = []
    for model in EMBED_MODELS:  # optional remote embeddings
        if not remote_ok():
            break
        try:
            if model not in _kb_emb:
                mat = await embed([kb_doc(e) for e in KB], model)
                with _kb_lock:
                    _kb_emb[model] = mat
            qv = await embed([query], model)
            sims = (_kb_emb[model] @ qv[0]) + code_boost(code)
            ranked = sorted(((float(s), i) for i, s in enumerate(sims)), reverse=True)
            retrieval = model
            break
        except AIError as e:
            log.warning("embedding %s failed: %s", model, e.message)
    if not ranked:  # free local embeddings
        key = f"local:{lm.EMB_ID}"
        try:
            if key not in _kb_emb:
                mat = await call_local(lm.EMB_ID, lambda: lm.embed([kb_doc(e) for e in KB]), timeout=30)
                with _kb_lock:
                    _kb_emb[key] = mat
            qv = await call_local(lm.EMB_ID, lambda: lm.embed([query]), timeout=15)
            # blend with keyword/alias overlap so exact fault codes always win
            kw = {i: s for s, i in keyword_rank(query, code)}
            sims = _kb_emb[key] @ qv[0] + code_boost(code) + np.array([0.3 * kw[i] for i in range(len(KB))])
            ranked = sorted(((float(s), i) for i, s in enumerate(sims)), reverse=True)
            retrieval = key
        except AIError as e:
            log.warning("local embeddings failed: %s", e.message)
    if not ranked:
        ranked = keyword_rank(query, code)

    top = [(round(s, 4), KB[i]) for s, i in ranked[:3]]
    context = "\n\n".join(
        f"[{n + 1}] {e['title']} (codes: {', '.join(e['codes'])})\nCauses: {'; '.join(e['causes'])}\n"
        f"Steps: {' | '.join(e['steps'])}\nSite visit typical: {e['needs_site_visit']}; "
        f"Parts: {', '.join(e['likely_parts']) or 'none'}"
        for n, (_, e) in enumerate(top))
    matches = [{"id": e["id"], "title": e["title"], "score": s} for s, e in top]

    try:
        raw, model = await chat_llm([{"role": "user", "content": FAULT_PROMPT.format(
            brand=brand or "unknown", code=code or "none", desc=desc or "none", context=context)}],
            max_tokens=600, local_tokens=280)
        d = extract_json(raw)
        conf = to_float(d.get("confidence"))
        steps = d.get("steps") or []
        parts = d.get("likely_parts") or []
        if not steps:
            raise AIError("bad_model_output", "model returned no steps", 502)
        best = top[0][1]
        steps = [str(s) for s in steps] if isinstance(steps, list) else [str(steps)]
        parts = [str(p) for p in parts] if isinstance(parts, list) else [str(parts)]
        # Safety/consistency guards (small local models reorder or drop these):
        # isolation always comes first; site-visit and parts never fall below the KB entry.
        if not re.search(r"isolat|switch\w* (?:the )?(?:ac|dc)|off\b|de-?energi", steps[0], re.I):
            steps.insert(0, SAFETY_STEP)
        conf = max(0.0, min(1.0, conf)) if conf is not None else 0.5
        if model.startswith("local:"):
            conf = min(conf, 0.8)
        return {
            "ok": True,
            "likely_cause": to_str(d.get("likely_cause")) or best["causes"][0],
            "steps": steps,
            "needs_site_visit": to_bool(d.get("needs_site_visit")) or bool(best["needs_site_visit"]),
            "likely_parts": parts or list(best["likely_parts"]),
            "confidence": round(conf, 2),
            "matches": matches,
            "retrieval": retrieval,
            "model": model,
            "source": "llm+kb",
        }
    except AIError as e:
        # No LLM answer: degrade to the best KB entry rather than failing outright.
        log.warning("fault LLM failed, returning KB answer: %s", e.message)
        best = top[0][1]
        return {
            "ok": True,
            "likely_cause": f"{best['title']}: " + "; ".join(best["causes"][:2]),
            "steps": best["steps"],
            "needs_site_visit": best["needs_site_visit"],
            "likely_parts": best["likely_parts"],
            "confidence": 0.4,
            "matches": matches,
            "retrieval": retrieval,
            "model": None,
            "source": "kb_only",
            "warning": f"LLM unavailable ({e.code}); answer taken directly from knowledge base",
        }


# ----------------------------------------------------------- /photo/check ---
_defect_lock = threading.Lock()
_defect: dict[str, Any] = {"fn": None, "labels": None, "error": None}


def _load_defect_model():
    """Download (once) and load the TF SavedModel. Thread-safe, lazy."""
    with _defect_lock:
        if _defect["fn"] is not None:
            return _defect["fn"], _defect["labels"]
        import tensorflow as tf  # heavy import, only on first call
        from huggingface_hub import snapshot_download

        path = snapshot_download(DEFECT_REPO, token=HF_TOKEN, allow_patterns=[
            "saved_model.pb", "fingerprint.pb", "variables/*"])
        # NOTE: the repo's labels.json lists classes in REVERSE alphabetical order, but the
        # model actually outputs them alphabetically (Keras image_dataset_from_directory
        # default). Verified on real photos: snow-covered panels fire index 5, clean panels
        # fire index 1. So we ignore labels.json and use the alphabetical list.
        labels = list(DEFECT_LABELS)
        loaded = tf.saved_model.load(path)
        sig = loaded.signatures["serving_default"]
        in_name = list(sig.structured_input_signature[1].keys())[0]

        def predict(batch: np.ndarray) -> np.ndarray:
            out = sig(**{in_name: tf.constant(batch, dtype=tf.float32)})
            return list(out.values())[0].numpy()

        _defect.update(fn=predict, labels=labels, model=loaded)
        return predict, labels


def _softmax_if_needed(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    if v.min() < 0 or abs(v.sum() - 1.0) > 1e-3:
        e = np.exp(v - v.max())
        return e / e.sum()
    return v


def _run_local(img: Image.Image) -> dict:
    predict, labels = _load_defect_model()
    # Keras ConvNeXt has its own normalization layer: feed raw 0-255 RGB, 224x224.
    x = np.asarray(img.resize((224, 224), Image.BILINEAR), dtype=np.float32)[None, ...]
    probs = _softmax_if_needed(predict(x)[0])
    return {labels[i]: float(p) for i, p in enumerate(probs)}


@app.post("/photo/check")
async def photo_check(file: UploadFile = File(...)):
    # First call downloads + loads the TF model; later calls take <1s.
    start_deadline(max(TIMEOUT_S, 240))
    raw_bytes, img = await read_image(file)
    backend = f"local:{DEFECT_REPO}"
    scores: dict[str, float] | None = None
    local_err = None
    try:
        scores = await call_local(DEFECT_REPO, lambda: _run_local(img), timeout=max(TIMEOUT_S, 180))
    except AIError as e:
        local_err = e.message
        log.warning("local defect model failed: %s", e.message)
    if scores is None:
        if not remote_ok():
            raise AIError("local_model_error", f"defect model unavailable: {local_err}", 503, DEFECT_REPO)
        backend = f"hf-api:{CLIP_MODEL}"
        prompts = {f"a photo of a solar panel that is {p}": lbl for lbl, p in [
            ("Bird-drop", "covered with bird droppings"), ("Clean", "clean"), ("Dusty", "dusty and dirty"),
            ("Electrical-damage", "electrically damaged with burn marks"),
            ("Physical-damage", "physically damaged with cracked glass"), ("Snow-covered", "covered with snow")]}
        out = await call_model(CLIP_MODEL, lambda: client.zero_shot_image_classification(
            raw_bytes, model=CLIP_MODEL, candidate_labels=list(prompts)))
        scores = {prompts[o.label]: float(o.score) for o in out}
    label = max(scores, key=scores.get)
    resp = {
        "ok": True,
        "label": label,
        "confidence": round(scores[label], 4),
        "all_scores": {k: round(v, 4) for k, v in sorted(scores.items(), key=lambda kv: -kv[1])},
        "flag": label != "Clean",
        "backend": backend,
    }
    if local_err:
        resp["warning"] = f"local model unavailable: {local_err}"
    return resp


# ---------------------------------------------------------------- /health ---
def _tf_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("tensorflow") is not None


async def _probe(model: str, fn: Callable[[], Any]) -> None:
    try:
        await call_model(model, fn, timeout=30)
    except AIError:
        pass


def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (128, 128, 128)).save(buf, "PNG")
    return buf.getvalue()


_warmup_state: dict[str, Any] = {"status": "disabled"}


@app.get("/health")
async def health(probe: bool = False):
    """Per-model availability. Remote status comes from the last real call; ?probe=true sends
    a tiny live request to every remote model (and re-enables remote if it had been tripped)."""
    global _remote_blocked_until
    if probe and HF_TOKEN and AI_REMOTE != "off":
        _remote_blocked_until = 0.0
        await asyncio.gather(
            *[_probe(m, lambda m=m: client.chat_completion(model=m, messages=[{"role": "user", "content": "ok"}],
                                                           max_tokens=1)) for m in [*VLM_MODELS, *LLM_MODELS]],
            *[_probe(m, lambda m=m: client.feature_extraction("ok", model=m)) for m in EMBED_MODELS],
            _probe(CLIP_MODEL, lambda: client.zero_shot_image_classification(_tiny_png(), model=CLIP_MODEL,
                                                                           candidate_labels=["a", "b"])),
        )
    remote = {}
    for m in [*VLM_MODELS, *LLM_MODELS, ASR_MODEL, *EMBED_MODELS, CLIP_MODEL]:
        remote[m] = MODEL_STATUS.get(m, {"available": None, "error_code": None, "last_checked": None, "last_error": None})
    local = {}
    for m, is_loaded in lm.loaded().items():
        st = MODEL_STATUS.get(m, {})
        local[m] = {"loaded": is_loaded, "load_seconds": lm.LOAD_SECONDS.get(m),
                    "available": st.get("available"), "last_error": st.get("last_error")}
    st = MODEL_STATUS.get(DEFECT_REPO, {})
    local[DEFECT_REPO] = {"loaded": _defect["fn"] is not None, "available": st.get("available"),
                          "last_error": st.get("last_error")}
    enabled = remote_ok()
    return {
        "ok": True,
        "status": "up",
        "remote": {
            "mode": AI_REMOTE,
            "enabled": enabled,
            "blocked_reason": None if enabled else (
                "no HF_TOKEN" if not HF_TOKEN else "AI_REMOTE=off" if AI_REMOTE == "off" else _remote_block_reason),
            "retry_in_s": max(0, int(_remote_blocked_until - time.time())),
            "models": remote,
        },
        "local_models": local,
        "warmup": _warmup_state,
        "hf_token_configured": bool(HF_TOKEN),
        "tensorflow_installed": _tf_available(),
        "kb_entries": len(KB),
        "timeout_s": TIMEOUT_S,
    }


@app.on_event("startup")
async def _start_warmup():
    """Load local models in the background so the first real request is fast.
    Disable with AI_WARMUP=0 (models then load on first use)."""
    if os.getenv("AI_WARMUP", "1") == "0":
        return

    def run():
        _warmup_state.update(status="running", started=int(time.time()))
        t = time.time()
        lm.warm_up()
        try:
            _load_defect_model()
        except Exception as e:  # noqa
            log.warning("defect model warm-up failed: %s", e)
        _warmup_state.update(status="done", seconds=round(time.time() - t, 1))
        log.info("warm-up finished in %.1fs", time.time() - t)

    threading.Thread(target=run, name="warmup", daemon=True).start()


@app.get("/")
async def root():
    return {"ok": True, "service": "SunPower AI",
            "endpoints": ["/bill/parse", "/lead/parse", "/fault/diagnose", "/photo/check", "/health"]}

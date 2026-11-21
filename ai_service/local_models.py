"""Free local CPU models for the SunPower AI service (no API credits needed).

Everything is lazy: nothing heavy is imported or downloaded until first use
(or until warm_up() is called at startup). Each model has its own lock so
concurrent requests queue instead of loading twice. Models are cached in the
standard Hugging Face cache (~/.cache/huggingface), outside the repo.

  LLM        Qwen/Qwen2.5-1.5B-Instruct  (override with env LOCAL_LLM, e.g. Qwen/Qwen2.5-0.5B-Instruct)
  ASR        openai/whisper-small
  Embeddings sentence-transformers/all-MiniLM-L6-v2 (mean pooling, via transformers)
  OCR        RapidOCR (ONNX, pip package `rapidocr` + onnxruntime)
"""
from __future__ import annotations

import io
import logging
import os
import re
import threading
import time
from typing import Any, Optional

import numpy as np

log = logging.getLogger("sunpower_ai.local")

LLM_ID = os.getenv("LOCAL_LLM", "Qwen/Qwen2.5-1.5B-Instruct")
ASR_ID = os.getenv("LOCAL_ASR", "openai/whisper-small")
EMB_ID = os.getenv("LOCAL_EMB", "sentence-transformers/all-MiniLM-L6-v2")
OCR_ID = "rapidocr"
THREADS = int(os.getenv("LOCAL_THREADS", str(max(1, (os.cpu_count() or 2) // 2))))

_locks = {k: threading.Lock() for k in ("llm", "asr", "emb", "ocr")}
_cache: dict[str, Any] = {}
LOAD_SECONDS: dict[str, float] = {}


def _torch():
    import torch
    torch.set_num_threads(THREADS)
    return torch


def loaded() -> dict[str, bool]:
    return {LLM_ID: "llm" in _cache, ASR_ID: "asr" in _cache, EMB_ID: "emb" in _cache, OCR_ID: "ocr" in _cache}


# ------------------------------------------------------------------- LLM ---
def _load_llm():
    if "llm" in _cache:
        return _cache["llm"]
    t = time.time()
    torch = _torch()
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(LLM_ID)
    model = AutoModelForCausalLM.from_pretrained(LLM_ID, torch_dtype=torch.float32)
    model.eval()
    _cache["llm"] = (tok, model)
    LOAD_SECONDS[LLM_ID] = round(time.time() - t, 1)
    log.info("loaded %s in %.1fs", LLM_ID, LOAD_SECONDS[LLM_ID])
    return _cache["llm"]


def llm_chat(messages: list[dict], max_new_tokens: int = 320, max_time: Optional[float] = None) -> str:
    """Greedy generation; stops as soon as the first JSON object is closed."""
    with _locks["llm"]:
        tok, model = _load_llm()
        torch = _torch()
        from transformers import StoppingCriteria, StoppingCriteriaList

        text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        enc = tok(text, return_tensors="pt")
        start = enc.input_ids.shape[1]

        class JsonClosed(StoppingCriteria):
            def __call__(self, input_ids, scores, **kw):
                s = tok.decode(input_ids[0, start:], skip_special_tokens=True)
                i = s.find("{")
                return i >= 0 and s.count("{", i) > 0 and s.count("{", i) == s.count("}", i)

        kwargs = dict(max_new_tokens=max_new_tokens, do_sample=False,
                      stopping_criteria=StoppingCriteriaList([JsonClosed()]),
                      pad_token_id=tok.eos_token_id)
        if max_time:
            kwargs["max_time"] = max(1.0, max_time)
        with torch.inference_mode():
            out = model.generate(**enc, **kwargs)
        return tok.decode(out[0, start:], skip_special_tokens=True)


# ------------------------------------------------------------------- ASR ---
def _load_asr():
    if "asr" in _cache:
        return _cache["asr"]
    t = time.time()
    _torch()
    from transformers import pipeline
    _cache["asr"] = pipeline("automatic-speech-recognition", model=ASR_ID, device="cpu")
    LOAD_SECONDS[ASR_ID] = round(time.time() - t, 1)
    log.info("loaded %s in %.1fs", ASR_ID, LOAD_SECONDS[ASR_ID])
    return _cache["asr"]


def decode_audio(data: bytes) -> np.ndarray:
    """Decode wav/flac/ogg/mp3 (libsndfile) to mono float32 at 16 kHz."""
    import soundfile as sf
    try:
        audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    except Exception as e:
        raise ValueError(f"unsupported or corrupt audio (use wav, mp3, ogg or flac): {e}")
    audio = audio.mean(axis=1)
    if sr != 16000 and len(audio):
        n = int(round(len(audio) * 16000 / sr))
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
    return audio


def transcribe(data: bytes) -> str:
    audio = decode_audio(data)
    if len(audio) < 1600:
        raise ValueError("audio too short")
    with _locks["asr"]:
        asr = _load_asr()
        out = asr({"raw": audio, "sampling_rate": 16000}, chunk_length_s=30, batch_size=4,
                  generate_kwargs={"task": "transcribe"})
    return (out.get("text") or "").strip()


# ------------------------------------------------------------ embeddings ---
def _load_emb():
    if "emb" in _cache:
        return _cache["emb"]
    t = time.time()
    _torch()
    from transformers import AutoModel, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(EMB_ID)
    model = AutoModel.from_pretrained(EMB_ID).eval()
    _cache["emb"] = (tok, model)
    LOAD_SECONDS[EMB_ID] = round(time.time() - t, 1)
    return _cache["emb"]


def embed(texts: list[str]) -> np.ndarray:
    """Mean-pooled, L2-normalised sentence embeddings, shape (N, 384)."""
    with _locks["emb"]:
        tok, model = _load_emb()
        torch = _torch()
        enc = tok(texts, padding=True, truncation=True, max_length=256, return_tensors="pt")
        with torch.inference_mode():
            hidden = model(**enc).last_hidden_state
        mask = enc.attention_mask.unsqueeze(-1).float()
        vec = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        vec = torch.nn.functional.normalize(vec, dim=1)
        return vec.numpy()


# ------------------------------------------------------------------- OCR ---
def _load_ocr():
    if "ocr" in _cache:
        return _cache["ocr"]
    t = time.time()
    from rapidocr import RapidOCR
    _cache["ocr"] = RapidOCR()
    LOAD_SECONDS[OCR_ID] = round(time.time() - t, 1)
    return _cache["ocr"]


def ocr_text(img) -> str:
    """OCR a PIL image; returns lines top-to-bottom, left-to-right."""
    arr = np.asarray(img.convert("RGB"))
    with _locks["ocr"]:
        engine = _load_ocr()
        res = engine(arr)
    txts = getattr(res, "txts", None)
    boxes = getattr(res, "boxes", None)
    if txts is None:  # older tuple API: ([[box, text, score], ...], elapse)
        items = res[0] if isinstance(res, tuple) else res
        items = items or []
        boxes = [it[0] for it in items]
        txts = [it[1] for it in items]
    if not txts:
        return ""
    # group into rows by box centre y so "label   value" pairs stay on one line
    entries = []
    for b, t in zip(boxes, txts):
        b = np.asarray(b, dtype=float)
        entries.append((b[:, 1].mean(), b[:, 0].min(), b[:, 1].max() - b[:, 1].min(), t))
    entries.sort()
    rows: list[list] = []
    for e in entries:
        if rows and abs(e[0] - rows[-1][0][0]) < max(8.0, 0.5 * e[2]):
            rows[-1].append(e)
        else:
            rows.append([e])
    return "\n".join("  ".join(x[3] for x in sorted(r, key=lambda x: x[1])) for r in rows)


# ------------------------------------------------------- regex extractors ---
DISCOMS = [
    "BSES Rajdhani", "BSES Yamuna", "Tata Power-DDL", "TPDDL", "Tata Power", "Adani Electricity", "BEST",
    "MSEDCL", "Mahavitaran", "BESCOM", "HESCOM", "GESCOM", "MESCOM", "CESCOM", "TANGEDCO", "TNPDCL", "KSEB",
    "UHBVN", "DHBVN", "PSPCL", "JVVNL", "AVVNL", "JdVVNL", "PVVNL", "MVVNL", "DVVNL", "PuVVNL", "KESCO", "UPPCL",
    "CESC", "WBSEDCL", "TSSPDCL", "TSNPDCL", "APSPDCL", "APEPDCL", "APCPDCL", "Torrent Power", "MGVCL", "DGVCL",
    "PGVCL", "UGVCL", "CSPDCL", "MPPKVVCL", "MPMKVVCL", "MPPoKVVCL", "NBPDCL", "SBPDCL", "TPCODL", "TPSODL",
    "TPWODL", "TPNODL", "JBVNL", "HPSEB", "JKPDD", "UPCL", "APDCL", "Goa Electricity",
]


def _num(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def regex_bill(text: str) -> dict:
    t = text
    out: dict[str, Any] = {}
    m = re.search(r"(?:consumer|ca|account|k|service|connection)\s*(?:no|number|id|num)\.?\s*[:/\-.]?\s*([A-Z0-9][A-Z0-9\-/]{5,19})", t, re.I)
    if m:
        out["consumer_no"] = m.group(1).strip("-/")
    low = t.lower()
    for d in DISCOMS:
        if d.lower() in low:
            out["discom"] = d
            break
    for line in t.splitlines():  # units: prefer explicit "units consumed/billed"
        if re.search(r"unit|consumption|kwh", line, re.I) and not re.search(r"rate|charge|per unit|reading", line, re.I):
            nums = [n for n in re.findall(r"\d[\d,]*(?:\.\d+)?", line) if 1 <= (_num(n) or 0) <= 20000]
            if nums:
                out["monthly_units_kwh"] = _num(nums[-1])
                break
    m = re.search(r"(?:total\s*amount\s*payable|net\s*amount\s*payable|amount\s*payable|total\s*payable|net\s*payable|"
                  r"bill\s*amount|amount\s*due|total\s*amount|payable\s*amount)\D{0,25}?(\d[\d,]*(?:\.\d{1,2})?)", t, re.I)
    if m:
        out["bill_amount"] = _num(m.group(1))
    m = re.search(r"(?:sanction(?:ed)?|contract(?:ed)?|connected)\s*load\D{0,20}?(\d+(?:\.\d+)?)\s*(kw|kva|hp)?", t, re.I)
    if m:
        v = _num(m.group(1))
        if v is not None and (m.group(2) or "").lower() == "hp":
            v = round(v * 0.746, 2)
        out["sanctioned_load_kw"] = v
    return out


COMPLAINT_WORDS = r"not working|kaam nahi|kam nahi|band ho|kharab|error|fault|problem|issue|complaint|shikayat|" \
                  r"trip|repair|stopped|less units|kam units|leak|damage|technician"


def regex_lead(text: str) -> dict:
    out: dict[str, Any] = {}
    m = re.search(r"(?:\+?91[\s-]?)?([6-9]\d{4}[\s-]?\d{5})", text)
    if m:
        out["phone"] = re.sub(r"\D", "", m.group(1))
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if m:
        out["email"] = m.group(0).rstrip(".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:kw|kilo\s*watt|किलोवाट)", text, re.I)
    if m:
        out["system_kw"] = _num(m.group(1))
    m = re.search(r"(?:bill|बिल)\D{0,40}?(\d[\d,]{2,6})|(?:rs\.?|₹|inr)\s*(\d[\d,]{2,6})|(\d[\d,]{2,6})\s*(?:rupaye|rupees|rupay|रुपये)", text, re.I)
    if m:
        out["monthly_bill"] = _num(next(g for g in m.groups() if g))
    out["subsidy"] = bool(re.search(r"subsid|surya ghar|yojana|सब्सिडी|योजना", text, re.I))
    if re.search(r"off[\s-]?grid|battery|backup|bina grid", text, re.I):
        out["system_type"] = "off_grid"
    if re.search(COMPLAINT_WORDS, text, re.I):
        out["intent"] = "complaint"
    elif re.search(r"solar|panel|install|lagwana|lagana|kw|quote|enquiry|inquiry", text, re.I):
        out["intent"] = "new_enquiry"
    return out


# ---------------------------------------------------------------- warm-up ---
def warm_up(parts: tuple[str, ...] = ("emb", "ocr", "llm", "asr")) -> None:
    """Load (and download on first run) the local models. Safe to call in a thread."""
    loaders = {"emb": _load_emb, "ocr": _load_ocr, "llm": _load_llm, "asr": _load_asr}
    for p in parts:
        try:
            with _locks[p]:
                loaders[p]()
        except Exception as e:  # never crash the service on warm-up
            log.warning("warm-up of %s failed: %s", p, e)

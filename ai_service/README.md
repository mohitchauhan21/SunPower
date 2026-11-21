# SunPower AI Service

A standalone FastAPI microservice that Odoo calls at `http://localhost:8000`. It runs natively on Windows in a Python venv (no Docker), and **everything works for free on CPU**: no API credits are needed.

## Run

```powershell
cd ai_service
powershell -ExecutionPolicy Bypass -File .\run.ps1          # -Port 8000 by default, -Reinstall to force pip install
.venv\Scripts\python download_models.py                     # optional: pre-download the local models (~2 GB)
```

`run.ps1` does the following:
- creates `.venv` if it is missing (prefers Python 3.12/3.11, otherwise 3.13, which this machine has);
- installs `requirements.txt` whenever an import check fails;
- starts `uvicorn main:app` on 127.0.0.1:8000.

On startup the service **warms up** the local models in a background thread; set `AI_WARMUP=0` to load them on first use instead. Warm-up downloads any model that isn't in the HF cache yet, so the first run takes a while. Track progress with `GET /health` → `warmup` / `local_models`.

**Configuration:**

| Setting | Default | Meaning |
|---|---|---|
| `HF_TOKEN` (in `../.env`) | — | Only used for the optional remote models and to download public models. Never printed or logged. |
| `AI_TIMEOUT` | `60` | Overall budget per request, across all fallbacks. |
| `AI_REMOTE` | `auto` | `auto` tries HF Inference Providers first while the token has credits. `off` never calls remote. |
| `AI_REMOTE_COOLDOWN` | `900` | After a 402 or auth failure, remote is skipped for this many seconds. |
| `LOCAL_LLM` | `Qwen/Qwen2.5-0.5B-Instruct` | Set `Qwen/Qwen2.5-1.5B-Instruct` for better extraction (~3 GB, slower). |
| `LOCAL_THREADS` | half the CPU threads | Torch threads used for local inference. |

- **CORS:** allowed from `http://localhost:8069` and `http://127.0.0.1:8069`.
- **Model storage:** local models live in the standard Hugging Face cache (`%USERPROFILE%\.cache\huggingface`) and the RapidOCR models inside `.venv`, both outside git.

## How each endpoint works

The order of attempts is: remote (only when HF credits exist) → free local CPU model → deterministic fallback.

| Endpoint | Free local path | Last-resort fallback |
|---|---|---|
| `POST /bill/parse` | **RapidOCR** reads the bill. Regex pulls consumer no., DISCOM (60+ known names), units, amount and sanctioned load. **Qwen2.5-0.5B** fills only the fields the regex missed. | Regex-only result with a `warning`. If no text is found: 422 `unreadable_image`. |
| `POST /lead/parse` | Audio goes through **whisper-small** (Hindi/English, auto language). **Qwen2.5-0.5B** extracts the JSON. Regex backstops phone, email, kW, bill, subsidy and intent. | Regex-only result (`name`/`city` null) with a `warning`. |
| `POST /fault/diagnose` | **all-MiniLM-L6-v2** embeddings blended with keyword and fault-code alias matching give the top-3 KB entries. **Qwen2.5-0.5B** writes the answer. | Best KB entry as is (`source: "kb_only"`). |
| `POST /photo/check` | ConvNeXt defect classifier (TensorFlow, CPU). | Remote CLIP, only if remote is enabled. |

## Contract (for Odoo)

Every response is JSON. A success has `"ok": true` plus the fields below (and sometimes a `warning`). A failure has a non-2xx status and this body:

```json
{"ok": false,
 "error": {"code": "invalid_input | unreadable_image | timeout | local_model_error | provider_credits_exhausted | model_not_served | provider_error | auth_error | bad_model_output | internal_error",
           "message": "...", "model": "model that failed last (or null)"},
 "fallback": "manual_entry"}
```

| HTTP status | Meaning |
|---|---|
| 422 | Bad input or unreadable image |
| 503 | A local model failed to load or run |
| 504 | Timeout |
| 402/502 | Remote only; with local models these are normally absorbed by fallbacks |
| 500 | Unexpected error |

**Odoo rule:** if `ok` is not `true`, show the manual-entry form. Use a client timeout of at least 65 s.

| Endpoint | Input | Output fields |
|---|---|---|
| `POST /bill/parse` | multipart `file` (image) | `consumer_no, discom, monthly_units_kwh, bill_amount, sanctioned_load_kw, recommended_kw` (units/120, rounded, clamped 1-5), `recommended_type` ("on_grid"), `model, method` (`ocr+regex`, `ocr+regex+llm` or `remote_vlm`), `ocr_text` |
| `POST /lead/parse` | form field `text` and/or multipart `audio` (wav/mp3/ogg/flac) | `intent` (new_enquiry\|complaint\|other), `name, phone, email, street, city, system_kw, system_type` (on_grid\|off_grid), `subsidy` (bool), `monthly_bill, summary, transcript, model, asr_model` |
| `POST /fault/diagnose` | JSON `{"fault_code", "description", "inverter_brand"}` (code or description required) | `likely_cause, steps[], needs_site_visit, likely_parts[], confidence` (0-1), `matches[]` (top-3 KB hits), `retrieval, source` ("llm+kb" or "kb_only"), `model` |
| `POST /photo/check` | multipart `file` (image) | `label` (Bird-drop\|Clean\|Dusty\|Electrical-damage\|Physical-damage\|Snow-covered), `confidence, all_scores{}, flag` (label != Clean), `backend` |
| `GET /health` | `?probe=true` re-tests the remote models | `remote{enabled, blocked_reason, models}, local_models{<id>: {loaded, load_seconds, available}}, warmup, kb_entries` |

## curl examples

Sample inputs live in `samples/`; regenerate the images with `py samples/make_samples.py`. Run these from Git Bash or with `curl.exe` (in Windows PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest`).

```bash
curl -s http://localhost:8000/health

curl -s -F "file=@samples/bill.jpg" http://localhost:8000/bill/parse

curl -s --form-string "text=Namaste, mera naam Suresh Yadav hai, Jaipur se. 3 kW grid wala solar chahiye, bill 2800 aata hai, subsidy milegi? 9876543210" http://localhost:8000/lead/parse
curl -s -F "audio=@samples/complaint.wav" http://localhost:8000/lead/parse

curl -s -H "Content-Type: application/json" \
  -d '{"fault_code":"ISO Fault","description":"Inverter not starting in the morning after rain","inverter_brand":"Growatt"}' \
  http://localhost:8000/fault/diagnose

curl -s -F "file=@samples/panel_dusty.jpg" http://localhost:8000/photo/check
```

## Local models: sizes and timings

Measured on this laptop (Ryzen 7 7435HS, 8 cores, 24 GB RAM, CPU only):

| Model | Used for | On disk | Load (warm) | Typical call |
|---|---|---|---|---|
| Qwen/Qwen2.5-0.5B-Instruct (fp32) | lead/bill/fault JSON | 1.0 GB | 3 s | 2–10 s |
| openai/whisper-small | audio → text | 0.97 GB | 2 s | 9.6 s for a 14 s clip |
| sentence-transformers/all-MiniLM-L6-v2 | fault retrieval | 88 MB | 1–8 s | <0.1 s |
| RapidOCR (PP-OCR ONNX) | bill OCR | 31 MB (in `.venv`) | 1 s | 1.5 s per bill |
| Swarmdrones ConvNeXt defect classifier (TF) | photo check | 214 MB | ~10 s | <1 s |
| CPU torch 2.15 + transformers 5.23 | runtime | ~0.6 GB (in `.venv`) | — | — |

**Warm-up** loads everything in about 21 s once the files are downloaded. Downloading the two ~1 GB models took 8.5 minutes in parallel.

**End-to-end** on the `run.ps1` server, after warm-up:

| Request | Time |
|---|---|
| `/bill/parse` sample bill (OCR + regex; LLM skipped because regex found every field) | 2.6 s |
| `/lead/parse` Hinglish text | 7.8 s |
| `/lead/parse` Hindi text | 7.0 s |
| `/lead/parse` 14 s audio (whisper + LLM) | 16 s |
| `/fault/diagnose` | 12–16 s |
| `/photo/check` | 1.8–2.4 s |

**Quality notes for the 0.5B model.** It is small, so the service adds guardrails:
- **Intent:** keyword rules win when they fire.
- **Numbers:** phone, email, kW and bill are range-checked and backed by regex.
- **Names and addresses:** for Latin-script text, `name`/`street`/`city` are dropped unless they actually appear in the message. For Hindi text the model transliterates, and `street` can be invented (e.g. "Lakhawat"), so Odoo should treat `street` from Hindi input as a suggestion.
- **Fault answers:** a safety isolation step is forced first, and `needs_site_visit`/`likely_parts` never fall below the matched KB entry.
- **Confidence:** capped at 0.8 for local answers.
- **Summary:** when the model omits it, a one-line English summary is built from the extracted fields.

- **Downloads:** HF downloads ran at about 1.2 MB/s on plain HTTP but only ~0.1 MB/s over the Xet protocol, so the service sets `HF_HUB_DISABLE_XET=1`.
- **Why 0.5B is the default:** the 1.5B model is ~3 GB (about 45 minutes to download here) and roughly 3× slower per token.

## Remote models (optional, currently unavailable)

The HF account has no Inference Provider credits: every remote model returns `402 Payment Required`, and `Qwen2.5-VL-7B`/`Qwen2.5-7B` are served only by featherless-ai, which isn't enabled. With `AI_REMOTE=auto` the service tries remote once, gets the 402, then skips remote for 15 minutes, so the cost is about 2 s once every 15 minutes. Set `AI_REMOTE=off` to skip it entirely.

If credits are ever added, re-test with `.venv\Scripts\python smoke_test.py` or `GET /health?probe=true`; no code change is needed.

| Remote model | Result (2026-11-21) |
|---|---|
| Qwen/Qwen2.5-VL-7B-Instruct, Qwen/Qwen2.5-7B-Instruct | 400 `model_not_supported` (featherless-ai not enabled) |
| Qwen/Qwen3-VL-8B-Instruct, Qwen/Qwen2.5-VL-72B-Instruct, meta-llama/Llama-3.1-8B-Instruct, Qwen/Qwen2.5-72B-Instruct, openai/whisper-large-v3, BAAI/bge-m3, sentence-transformers/all-MiniLM-L6-v2 | 402 (no credits) |
| openai/clip-vit-base-patch32 | Not served by any provider |

## Defect classifier notes (verified)

- **Input:** raw RGB 0-255 float32, 224×224. The Keras ConvNeXt model normalises internally.
- **Class order:** outputs are **alphabetical**: `[Bird-drop, Clean, Dusty, Electrical-damage, Physical-damage, Snow-covered]`. The repo's `labels.json` lists them reversed and is wrong.
- **Evidence:** 3/3 real snow photos fired index 5 (Snow-covered) at ≥0.86; 3/4 real clean photos fired index 1 (Clean) at ~0.91.
- **Accuracy on out-of-domain photos is mixed:**
  - Of 5 real "dirty" photos, 2 came back Dusty, 2 came back **Clean** (`flag` false) and 1 Electrical-damage.
  - One clean photo came back Electrical-damage at 0.91.
  - Treat `label`/`flag` as a hint for the technician; don't gate anything on `flag` alone.

## Files

- `main.py`: the service (routing, fallbacks, error envelope)
- `local_models.py`: lazy local LLM, whisper, embeddings, OCR, and the regex extractors
- `kb/fault_codes.json`: 31 inverter faults with code aliases, causes, safe steps, site-visit flag and parts
- `download_models.py`: pre-downloads the local models
- `bench_local.py`: times each local model
- `smoke_test.py`: one tiny call per remote model
- `samples/`: fake bill, synthetic panels, Hinglish and Hindi leads, and a TTS complaint call
- `run.ps1`: venv creation, install and launch

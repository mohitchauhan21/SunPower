# SunPower AI Service

A standalone FastAPI microservice that Odoo calls at `http://localhost:8000`. It runs natively on Windows in a Python venv (no Docker).

## Run

```powershell
cd ai_service
powershell -ExecutionPolicy Bypass -File .\run.ps1          # -Port 8000 by default, -Reinstall to force pip install
```

`run.ps1` creates `.venv` if it is missing. It prefers Python 3.12/3.11 when installed and otherwise uses 3.13, which is what this machine has; TensorFlow 2.21 works on 3.13. It installs `requirements.txt` when dependencies are missing and then starts `uvicorn main:app` on 127.0.0.1:8000. The first install downloads TensorFlow (~350 MB).

- **Token:** `HF_TOKEN` is read from `../.env` (the project root) with python-dotenv. It is never printed or logged.
- **CORS:** allowed from `http://localhost:8069` and `http://127.0.0.1:8069`.
- **Timeout:** each request has one overall 60 s budget across every model fallback (`AI_TIMEOUT` env var). The exception is `/photo/check`: its first call downloads and loads the TF model (~15-40 s, up to 240 s allowed), and later calls take under 1 s.

## Contract (for Odoo)

Every response is JSON. A success has `"ok": true` plus the fields below. A failure has a non-2xx status and this body:

```json
{"ok": false,
 "error": {"code": "provider_credits_exhausted | model_not_served | timeout | provider_error | auth_error | bad_model_output | invalid_input | internal_error",
           "message": "...", "model": "model that failed last (or null)"},
 "fallback": "manual_entry"}
```

| HTTP status | Meaning |
|---|---|
| 402 | The HF account has no inference credits |
| 422 | Bad input |
| 502 | Provider or model failure, or unparseable model output |
| 504 | Timeout |
| 500 | Unexpected error |

**Odoo rule:** if `ok` is not `true`, show the manual-entry form.

| Endpoint | Input | Output fields |
|---|---|---|
| `POST /bill/parse` | multipart `file` (image) | `consumer_no, discom, monthly_units_kwh, bill_amount, sanctioned_load_kw, recommended_kw` (units/120, rounded, clamped 1-5), `recommended_type` ("on_grid"), `model` |
| `POST /lead/parse` | form field `text` **or** multipart `audio` (wav/mp3/m4a/ogg); both allowed | `intent` (new_enquiry\|complaint\|other), `name, phone, email, street, city, system_kw, system_type` (on_grid\|off_grid), `subsidy` (bool), `monthly_bill, summary, transcript, model, asr_model` |
| `POST /fault/diagnose` | JSON `{"fault_code", "description", "inverter_brand"}` (code or description required) | `likely_cause, steps[], needs_site_visit, likely_parts[], confidence` (0-1), `matches[]` (top-3 KB hits), `retrieval` (embedding model or "keyword"), `source` ("llm+kb" or "kb_only"), optional `warning` |
| `POST /photo/check` | multipart `file` (image) | `label` (Bird-drop\|Clean\|Dusty\|Electrical-damage\|Physical-damage\|Snow-covered), `confidence, all_scores{}, flag` (label != Clean), `backend` |
| `GET /health` | `?probe=true` sends a tiny live call to every remote model | `hf_token_configured, tensorflow_installed, kb_entries, models{<id>: {available, error_code, last_error, last_checked}}` |

### Graceful degradation

| Endpoint | Fallback chain | When everything remote fails |
|---|---|---|
| `/fault/diagnose` | Retrieval: bge-m3 → all-MiniLM-L6-v2 → keyword/alias match. LLM: Qwen2.5-7B → Llama-3.1-8B → Qwen2.5-72B. | Still returns **200** with the best KB entry (`source: "kb_only"`, `confidence: 0.4`, `warning`). |
| `/photo/check` | Runs locally on CPU (no credits needed). CLIP zero-shot via the API is the fallback only if TF fails. | — |
| `/bill/parse` | Qwen2.5-VL-7B → Qwen3-VL-8B → Qwen2.5-VL-72B | Error envelope |
| `/lead/parse` | whisper-large-v3 for audio, then the LLM chain above | Error envelope |

## curl examples

Sample inputs live in `samples/`; regenerate the images with `py samples/make_samples.py`. Run these from Git Bash or `curl.exe` (in Windows PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest`).

```bash
curl -s http://localhost:8000/health
curl -s "http://localhost:8000/health?probe=true"

curl -s -F "file=@samples/bill.jpg" http://localhost:8000/bill/parse

curl -s --form-string "text=Namaste, mera naam Suresh Yadav hai, Jaipur se. 3 kW grid wala solar chahiye, bill 2800 aata hai, subsidy milegi? 9876543210" http://localhost:8000/lead/parse
curl -s -F "audio=@samples/complaint.wav" http://localhost:8000/lead/parse

curl -s -H "Content-Type: application/json" \
  -d '{"fault_code":"ISO Fault","description":"Inverter not starting in the morning after rain","inverter_brand":"Growatt"}' \
  http://localhost:8000/fault/diagnose

curl -s -F "file=@samples/panel_dusty.jpg" http://localhost:8000/photo/check
```

## Model smoke-test results (2026-11-21)

Re-run with `.venv\Scripts\python smoke_test.py`, or call `GET /health?probe=true`.

**Remote models:** the account currently has no Hugging Face Inference Provider credits. Every remotely served model returns `402 Payment Required` ("Purchase pre-paid credits ... or subscribe to PRO"), so **no remote model works right now**.

| Model | Result | Notes |
|---|---|---|
| Qwen/Qwen2.5-VL-7B-Instruct | 400 `model_not_supported` | Only provider is featherless-ai, which is not enabled on the account. With `:featherless-ai` forced it reaches 402. |
| Qwen/Qwen2.5-7B-Instruct | 400 `model_not_supported` | Same reason (featherless-ai only). |
| Qwen/Qwen3-VL-8B-Instruct (VLM fallback) | 402 | Has providers (expected to work once there are credits; unverified): novita. |
| Qwen/Qwen2.5-VL-72B-Instruct (VLM fallback) | 402 | Has providers (expected to work once there are credits; unverified): ovhcloud/featherless. |
| meta-llama/Llama-3.1-8B-Instruct | 402 | Has providers (expected to work once there are credits; unverified): deepinfra/novita. |
| Qwen/Qwen2.5-72B-Instruct (LLM fallback) | 402 | Has providers (expected to work once there are credits; unverified): deepinfra/novita. |
| openai/whisper-large-v3 | 402 | Has providers (expected to work once there are credits; unverified): fal-ai/hf-inference/deepinfra. |
| BAAI/bge-m3 | 402 | hf-inference. |
| sentence-transformers/all-MiniLM-L6-v2 | 402 | hf-inference. |
| openai/clip-vit-base-patch32 | Not served | No inference provider offers it, so this fallback can never work remotely. |
| **Swarmdrones/convnext-solar-panel-defect-classifier-v1** | **Works (local TF 2.21, CPU)** | — |

**To turn the remote AI on:**
1. Add pre-paid credits or HF PRO at https://huggingface.co/settings/billing, or put a token from an account with credits in `.env`.
2. Optionally, enable **featherless-ai** at https://huggingface.co/settings/inference-providers so the listed primary Qwen2.5 7B models are used. Without it, the fallbacks (Qwen3-VL-8B, Llama-3.1-8B) are tried automatically.

No code change is needed for either step.

**What was verified without credits:**
- **Timeout budget:** with `AI_TIMEOUT=2` and a mocked client that hangs, bill and lead return the 504 envelope in 2.0 s and fault returns 200 `kb_only` in 2.0 s, on a real uvicorn.
- **Not yet exercised against a live provider:** the VLM image payload, ASR, and the batched embeddings call. `smoke_test.py` covers all of them (primaries and fallbacks), so re-run it once credits are added.
- The bill, lead and fault success paths (JSON extraction from fenced/messy output, number and phone normalisation, the kW recommendation, retrieval scoring) were tested against a mocked HF client.
- With real models, extraction quality (Hindi/Hinglish included) is untested until credits are added.

### Defect classifier notes (verified)

- **Input:** raw RGB 0-255 float32, 224×224. The Keras ConvNeXt model normalises internally. Dividing by 255 makes every image output the same thing.
- **Class order:** the model's outputs are in **alphabetical** order `[Bird-drop, Clean, Dusty, Electrical-damage, Physical-damage, Snow-covered]`. The repo's `labels.json` lists them reversed and is wrong.
- **Evidence:**
  - 3/3 real snow photos (Wikimedia Commons) fire index 5 at ≥0.86, i.e. Snow-covered.
  - 3/4 real clean photos (HF dataset `adityashirsatrao007/solar-dust-data-combined`) fire index 1 at ~0.91, i.e. Clean.
- **Accuracy on out-of-domain photos is mixed:**
  - Of 5 real "dirty" photos from that dataset, 2 came back Dusty, 2 came back **Clean** (`flag` false) and 1 Electrical-damage.
  - One clean photo came back Electrical-damage at 0.91.
  - Odoo should treat `label`/`flag` as a hint for the technician and not gate anything on `flag` alone.

## Files

- `main.py`: the service
- `kb/fault_codes.json`: 31 inverter faults with code aliases, causes, safe steps, site-visit flag and parts
- `smoke_test.py`: one tiny call per model
- `samples/`: fake bill, synthetic panels, a Hinglish lead and a TTS complaint call
- `run.ps1`: venv creation, install and launch

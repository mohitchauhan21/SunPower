"""Tiny smoke test of every Hugging Face model the service uses (primaries AND fallbacks).

Usage:  .venv\\Scripts\\python smoke_test.py
Prints OK/FAIL per model. Never prints the token. Model lists come from main.py,
so this always matches what the service will actually try.
"""
import base64
import io
import math
import os
import struct
import wave

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
import main  # noqa: E402  (loads .env, builds the client)
from PIL import Image  # noqa: E402

client = main.client


def img_data_url():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (30, 60, 200)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def wav_bytes():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(16000)))
    return buf.getvalue()


def run(name, fn):
    try:
        out = fn()
        print(f"OK    {name}: {str(out)[:120]!r}")
    except StopIteration:
        print(f"FAIL  {name}: no inference provider serves this model for this task")
    except Exception as e:  # noqa
        status = getattr(getattr(e, "response", None), "status_code", None)
        print(f"FAIL  {name}: [{status}] {type(e).__name__}: {str(e).splitlines()[-1][:200] if str(e) else ''}")


def chat(model, content):
    r = client.chat_completion(model=model, messages=[{"role": "user", "content": content}], max_tokens=20)
    return r.choices[0].message.content


for m in main.VLM_MODELS:  # same image payload shape as /bill/parse
    run(f"VLM {m}", lambda m=m: chat(m, [{"type": "image_url", "image_url": {"url": img_data_url()}},
                                         {"type": "text", "text": "What colour is this image? One word."}]))
for m in main.LLM_MODELS:
    run(f"LLM {m}", lambda m=m: chat(m, "Say OK"))
run(f"ASR {main.ASR_MODEL}", lambda: client.automatic_speech_recognition(wav_bytes(), model=main.ASR_MODEL))
docs = [main.kb_doc(e) for e in main.KB]
for m in main.EMBED_MODELS:  # single query + the full batched KB call /fault/diagnose makes
    run(f"EMB {m} (single)", lambda m=m: main._normalize(client.feature_extraction("hello", model=m)).shape)
    run(f"EMB {m} (batch {len(docs)})", lambda m=m: main._normalize(client.feature_extraction(docs, model=m)).shape)
run(f"CLIP {main.CLIP_MODEL}", lambda: client.zero_shot_image_classification(
    base64.b64decode(img_data_url().split(",")[1]), model=main.CLIP_MODEL, candidate_labels=["clean", "dusty"]))
run(f"LOCAL {main.DEFECT_REPO}", lambda: main._run_local(Image.new("RGB", (224, 224), (40, 60, 120))))

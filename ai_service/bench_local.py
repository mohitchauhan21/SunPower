"""Download (first run) and time every local model. Usage: .venv\\Scripts\\python bench_local.py [llm|asr|emb|ocr ...]"""
import os
import sys
import time

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
from PIL import Image  # noqa: E402

import local_models as lm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
parts = sys.argv[1:] or ["emb", "ocr", "llm", "asr"]


def timed(label, fn):
    t = time.time()
    out = fn()
    print(f"{label}: {time.time() - t:.1f}s -> {str(out)[:300]!r}", flush=True)
    return out


if "emb" in parts:
    timed("emb load", lm._load_emb)
    timed("emb 31 docs", lambda: lm.embed(["inverter fault text"] * 31).shape)
    timed("emb 1 query", lambda: lm.embed(["isolation fault after rain"]).shape)
if "ocr" in parts:
    timed("ocr load", lm._load_ocr)
    txt = timed("ocr bill.jpg", lambda: lm.ocr_text(Image.open(os.path.join(HERE, "samples", "bill.jpg"))))
    print(txt)
    print("regex:", lm.regex_bill(txt))
if "llm" in parts:
    timed("llm load", lm._load_llm)
    msgs = [{"role": "user", "content": 'Reply with ONLY JSON {"city": string, "kw": number} for: "Jaipur se hoon, 3 kW chahiye"'}]
    timed("llm short json", lambda: lm.llm_chat(msgs, max_new_tokens=60))
if "asr" in parts:
    timed("asr load", lm._load_asr)
    data = open(os.path.join(HERE, "samples", "complaint.wav"), "rb").read()
    timed("asr complaint.wav (~14s audio)", lambda: lm.transcribe(data))

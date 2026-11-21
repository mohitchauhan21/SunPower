"""Pre-download the free local models (run once; ~2 GB). Usage: .venv\\Scripts\\python download_models.py [--big]   (macOS: .venv/bin/python)"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # plain HTTP was ~10x faster than xet on this network
from huggingface_hub import snapshot_download  # noqa: E402

PATTERNS = ["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*", "merges.txt", "vocab*"]
MODELS = ["Qwen/Qwen2.5-0.5B-Instruct", "openai/whisper-small", "sentence-transformers/all-MiniLM-L6-v2"]
if "--big" in sys.argv:
    MODELS.append("Qwen/Qwen2.5-1.5B-Instruct")


def get(repo):
    t = time.time()
    path = snapshot_download(repo, allow_patterns=PATTERNS, ignore_patterns=["onnx/*", "openvino/*", "*.onnx"])
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(path) for f in fs)
    print(f"{repo}: {size / 1e6:.0f} MB in {time.time() - t:.0f}s", flush=True)


with ThreadPoolExecutor(len(MODELS)) as ex:
    list(ex.map(get, MODELS))

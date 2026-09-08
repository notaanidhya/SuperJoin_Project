import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from google import genai
from app.config import settings

client = genai.Client(api_key=settings.gemini_api_key)

models_to_test = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest"
]

print("Testing candidate models for active quota:", flush=True)
for m in models_to_test:
    try:
        res = client.models.generate_content(model=m, contents="Say hi in one word")
        print(f"[AVAILABLE] {m}: {res.text.strip()}", flush=True)
    except Exception as e:
        err_msg = str(e)
        if "404" in err_msg:
            print(f"[404 NOT FOUND] {m}", flush=True)
        elif "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            print(f"[QUOTA EXHAUSTED/LIMITED] {m}: {err_msg[:80]}", flush=True)
        else:
            print(f"[FAILED] {m}: {err_msg[:80]}", flush=True)

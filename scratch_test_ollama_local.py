import requests
import time

url = "http://127.0.0.1:11434/api/generate"
print("1. Testing qwen3.5:9b on local host...")
t0 = time.time()
try:
    r = requests.post(url, json={"model": "qwen3.5:9b", "prompt": "Merhaba kendini bir cumleyle tanit", "stream": False}, timeout=60)
    print(f"Done in {time.time()-t0:.2f}s:")
    print(r.json().get('response'))
except Exception as e:
    print("qwen3.5:9b failed:", e)

print("\n2. Testing second request (warm cache)...")
t0 = time.time()
try:
    r = requests.post(url, json={"model": "qwen3.5:9b", "prompt": "Nasılsın?", "stream": False}, timeout=60)
    print(f"Done in {time.time()-t0:.2f}s:")
    print(r.json().get('response'))
except Exception as e:
    print("qwen3.5:9b failed:", e)

import os
import sys
import time
from huggingface_hub import hf_hub_download

REPO_ID = "convaiinnovations/laya"
FILES = [
    "multilingual/rl_agent_config.json",
    "multilingual/encoder/config.json",
    "multilingual/tokenizer/tokenizer_config.json",
    "multilingual/tokenizer/tokenizer.json",
    "multilingual/model.safetensors",
]

print("=" * 60)
print("Laya Multilingual Model İndirme Başlatılıyor...")
print("Hedef Repo:", REPO_ID)
print("=" * 60)

for i, filename in enumerate(FILES, 1):
    print(f"\n[{i}/{len(FILES)}] İndiriliyor: {filename} ...")
    start = time.time()
    path = hf_hub_download(repo_id=REPO_ID, filename=filename)
    size_mb = os.path.getsize(path) / (1024 * 1024)
    elapsed = time.time() - start
    print(f"Tamamlandı: {size_mb:.2f} MB ({elapsed:.1f} sn) -> {path}")

print("\n" + "=" * 60)
print("Tüm model dosyaları başarıyla indirildi!")
print("=" * 60)

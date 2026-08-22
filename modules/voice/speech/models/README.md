# Vosk Models

Buraya Vosk offline model klasörünü yerleştirin.

**Otomatik kurulum (Pi):**

```bash
python tools/install_vosk_tr.py
```

SSL hatası (`CERTIFICATE_VERIFY_FAILED`) alırsanız:

```bash
sudo apt update && sudo apt install -y ca-certificates
python tools/install_vosk_tr.py
# veya acil:
python tools/install_vosk_tr.py --insecure
```

Manuel: `vosk-model-small-tr-0.3` klasörünü `vosk-tr` adına kopyalayın (0.22 artık yayımlanmıyor).

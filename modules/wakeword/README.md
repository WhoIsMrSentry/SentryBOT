# Wakeword Module

Lightweight wakeword detector that keeps speech recognition off until a wakeword is detected.

## Behavior
- Always-on wakeword listener using Vosk ASR.
- When a wakeword is detected, it starts speech recognition for a short window.
- When the window ends (or a final command is received), speech recognition stops.

## Quick Start
### Python
```python
from modules.wakeword import WakewordService
svc = WakewordService()
svc.start_background()
```

### CLI / API
- Run: `python -m modules.wakeword.xWakewordService --api`
- Status: GET `/wakeword/status`
- Start: POST `/wakeword/start`
- Stop: POST `/wakeword/stop`

## Configuration
See config file at `modules/wakeword/config/config.yml`.

## Notes
- Supports Vosk-based wakeword detection or OpenWakeWord inference.
- For OpenWakeWord, configure `openwakeword.model_paths` and set `wakeword.engine: openwakeword`.
- Uses the `actions` section to call speech/interactions endpoints.
- This module is designed to be mounted inside the Gateway.

## Training a custom verifier (your own voice)
If you want the wakeword system to be stricter for *your* voice, train an OpenWakeWord custom verifier using your recorded positive and negative samples.

1) Prepare folders:

```
wakeword_data/positive   # your voice samples saying the wakeword (16kHz, mono WAV)
wakeword_data/negative   # other speech/noise (16kHz, mono WAV)
```

2) Train verifier locally (PC):

```powershell
# Activate virtualenv then run:
C:/path/to/venv/Scripts/python.exe -m pip install openwakeword
C:/path/to/venv/Scripts/python.exe modules/wakeword/tools/train_verifier.py --positive wakeword_data/positive --negative wakeword_data/negative --out modules/wakeword/models/verifier.joblib --base-model alexa
```

3) Configure wakeword module to use verifier:

Edit `modules/wakeword/config/config.yml` and set `openwakeword.verifier_path: "models/verifier.joblib"` and `wakeword.engine: openwakeword`.

4) Restart gateway/wakeword and test.

Note: For full custom model training (new ONNX models) use the openWakeWord training notebooks (recommended for production-quality models).

## References
- Speech module: audio capture and recognition pipeline.
- Interactions module: event bus for wakeword signals.

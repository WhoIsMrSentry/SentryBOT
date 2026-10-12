# SentryBOT Raspberry Pi deployment

## Order

```bash
sudo bash tools/pi_dependency_installer.sh
bash tools/pi_model_downloader_layout.sh
python tools/pi_runtime_readiness.py
python tools/pi_camera_imx500_live_test.py --seconds 8
sudo bash tools/pi_systemd_install.sh
sudo systemctl start sentrybot.service
journalctl -u sentrybot.service -f
python tools/companion_e2e_robot_test.py --base http://127.0.0.1:8080
```

## Network bind

Camera, autonomy, VLM bridge, and the Ollama/ai_provider HTTP servers listen on `127.0.0.1` by default. The gateway process is unchanged and still follows `server.host` plus `SENTRYBOT_HOST` in the systemd unit.

To reach one of those four services from another machine on the LAN, set its existing `server.host` key to `0.0.0.0` (module `config/config.yml`, or the matching section in `config/agent.yaml`). An environment variable overrides that key when it is set:

| Service | Config section | Environment override |
| --- | --- | --- |
| Camera | `server.host` | `CAM_HOST` |
| Autonomy | `server.host` | `AUTONOMY_HOST` |
| VLM bridge | `vlm_bridge.server.host` | `VLM_HOST` |
| Ollama / ai_provider | `ollama_service.server.host` | `OLLAMA_SERVICE_HOST` |

`OLLAMA_HOST` is the Ollama daemon URL, not this bind address.

## Motion safety

Base movement remains disabled until `/autonomy/pi-runtime/status`, `/autonomy/assets/status`, camera, ESP bridge, and clearance sensors are all valid.
Enable physical base motion only after manual bench testing.

```bash
sudoedit /etc/sentrybot/sentrybot.env
# SENTRYBOT_SAFE_BASE_MOTION=1
sudo systemctl restart sentrybot.service
```

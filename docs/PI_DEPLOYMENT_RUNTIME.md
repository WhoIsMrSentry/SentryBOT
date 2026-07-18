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

## Motion safety

Base movement remains disabled until `/autonomy/pi-runtime/status`, `/autonomy/assets/status`, camera, ESP bridge, and clearance sensors are all valid.
Enable physical base motion only after manual bench testing.

```bash
sudoedit /etc/sentrybot/sentrybot.env
# SENTRYBOT_SAFE_BASE_MOTION=1
sudo systemctl restart sentrybot.service
```

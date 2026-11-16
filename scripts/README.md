# SentryBOT Kurulum, Kalibrasyon ve Başlatma Betikleri (`scripts/`)

Bu dizin kurulum, veritabanı taşıma, yüz/ses kalibrasyonu ve robot başlatma betiklerini barındırır.

## Başlıca Betikler ve Güncel Arayüzler

- `_camera_capture_helper.py`:
  - `resolve_gateway_snap_url(explicit_url=None) -> str`
  - `fetch_frame_from_gateway(snap_url=None, timeout_s=1.5) -> Any | None`
  - `capture_live_face_frame(*, camera_num=0, gateway_url=None, max_attempts=30, poll_interval_s=0.16, frame_selector=None, prefer_gateway=True) -> Any | None`
  - Gateway `/camera/snap` -> `CameraCapture` (`finally: cap.stop()`) -> OpenCV `VideoCapture` (`finally: vcap.release()`) sırasıyla çalışır.
- `enroll_face.py` ve `verify_face.py`: Ortak `capture_live_face_frame` yardımcısını kullanır ve yalnızca :8080 Gateway `/camera/snap` uç noktasına başvurur.
- `calibrate_doa.py`: Geri sayım ve 5 saniyelik kayıt penceresi için duvar saati yerine `time.monotonic()` kullanır.
- `serial_stepper_test.py`: `main(argv=None) -> int` içinde çalışır ve `finally:` bloğunda PID/hedef sıfırlayıp seri portu kapatır.
- `run_robot.py`: `_SHUTDOWN_LOCK` + `_STOPPED_SERVICE_IDS` ile tek seferlik servis kapatma (`_stop_started_services(app)`) ve çıkışta `logging.shutdown()` garanti eder.
- `install_all_requirements.py` / `install_all_requirements.sh`: Depo kökünü `Path(__file__).resolve().parents[1]` ile çözer, göreli `--venv-path` değerini depo köküne göre çözümler ve `--profile {all,pi,pc,ci}` profil filtresi sunar (`filter_requirements_for_profile(files, profile, repo_root)`).
- `install_all.sh`: Bayrak sırasından bağımsız `case` ayrıştırıcısı, CPU `torch`/`torchvision` için ayrılmış `--index-url`, Qt4 kalıntılarından arındırılmış sistem paketleri ve `(cd /tmp && ...)` alt kabuğu kullanır.
- `setup/install_piper_models.py`: İndirmeleri `.tmp` üzerine yazıp atomik olarak taşır; `compute_sha256`, `verify_sha256`, `_load_sha256_manifest` ile `--checksum-manifest` ve `--verify` doğrulaması sunar.
- `migrations/social_db_migrate.py`: `_ROOT = Path(__file__).resolve().parents[2]` ve `_merge_chat_episodes()` ile idempotent sohbet bölümü birleştirmesi yapar (mevcut sohbetleri silmez).
- `assets/sync_pip_eyes_catalog.py`: `_ROOT = Path(__file__).resolve().parents[2]` ve güncel `modules/visual_output/oled_faces/services/eyes/` hedef yolunu raporlar.

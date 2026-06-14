"""xStream_HW: Ana kamera servisi başlatıcı.

Bu dosya modüler kamera servisinin çalıştırılabilir giriş noktasıdır.
FastAPI uygulamasını `xCameraService.create_app` ile oluşturur.

Hem paket modülü (python -m modules.camera.xStream_HW) hem de doğrudan
script olarak (python modules/camera/xStream_HW.py) çalıştırmayı destekler.
"""

# Paket içi import (modül olarak çalıştırma) veya script fallback
try:
    from .xCameraService import create_app
    from .config_loader import load_config
except Exception:  # relative import failed when run as script
    import os
    import sys

    _HERE = os.path.dirname(os.path.abspath(__file__))
    _PARENT = os.path.dirname(_HERE)
    # Yerel paket klasörü ve ebeveynini sys.path'e ekle
    for p in (_HERE, _PARENT):
        if p not in sys.path:
            sys.path.insert(0, p)
    from xCameraService import create_app  # type: ignore
    from config_loader import load_config  # type: ignore

if __name__ == "__main__":
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(),
        host=str(cfg.get("server", {}).get("host", "0.0.0.0")),
        port=int(cfg.get("server", {}).get("port", 8000)),
    )

from .fake_transport_sim import FakeTransportSim
from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService


def test_fake_transport_auto_reply_hello():
    dt = FakeTransportSim()
    svc = xArduinoSerialService(config_overrides={"transport": "serial"}, transport_factory=lambda *a, **k: dt)
    svc.start()
    try:
        resp = svc.request({"cmd": "hello"}, timeout=1.0)
        assert isinstance(resp, dict)
        assert resp.get("ok") is True
        # confirm write happened
        assert dt._buf, "expected writes to transport"
    finally:
        svc.stop()

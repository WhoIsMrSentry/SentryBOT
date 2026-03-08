def test_wakeword_smoke_import():
    from modules.wakeword import WakewordService
    svc = WakewordService
    assert svc is not None

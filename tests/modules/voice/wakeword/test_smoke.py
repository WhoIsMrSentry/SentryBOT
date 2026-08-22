def test_wakeword_smoke_import():
    from modules.voice.wakeword import WakewordService
    svc = WakewordService
    assert svc is not None

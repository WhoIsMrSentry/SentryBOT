def test_import_speak_service():
    from modules.voice.speak import SpeakService
    assert SpeakService is not None


def test_set_stream_max_chunk_chars():
    from modules.voice.speak.xSpeakService import SpeakService

    svc = SpeakService.__new__(SpeakService)
    svc.stream_max_chunk_chars = 180
    out = SpeakService.set_stream_max_chunk_chars(svc, 90)
    assert out["ok"] is True
    assert svc.stream_max_chunk_chars == 90

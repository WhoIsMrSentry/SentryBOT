from modules.expression.interactions.services.metrics import MetricsCollector


def test_sample_prefers_hardware_snapshot(monkeypatch):
    monkeypatch.setattr(
        MetricsCollector,
        "_hardware_snapshot",
        staticmethod(lambda: {"cpu_temp_c": 61.5, "cpu_load_1m": 2.0}),
    )
    monkeypatch.setattr("os.cpu_count", lambda: 4)
    m = MetricsCollector().sample()
    assert m.cpu_temp == 61.5
    assert m.cpu_load == 0.5

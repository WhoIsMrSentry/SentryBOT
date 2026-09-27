import os
import time

from modules.agent_core.services.sensor_loop import SensorFeedbackLoop


class World:
    def __init__(self):
        self.state_updates = []
        self.scenes = []

    def update_state(self, data):
        self.state_updates.append(dict(data))

    def update_scene(self, data):
        self.scenes.append(dict(data))


class Client:
    def __init__(self):
        self.sensors = []
        self.vision_calls = 0
        self.context_calls = 0

    def read_sensor(self, name):
        self.sensors.append(name)
        return {}

    def get_latest_vision_results(self, limit=1):
        self.vision_calls += 1
        return []

    def get_visual_context(self):
        self.context_calls += 1
        return {"available": True, "context": {"summary": "desk"}}


def test_sensor_loop_skips_hardware_in_pc_mode(monkeypatch):
    monkeypatch.setenv("SENTRYBOT_PC_TEST", "1")
    world = World()
    client = Client()
    loop = SensorFeedbackLoop(world, client=client, hardware_interval_s=0.2, vision_results_interval_s=0.2, visual_context_interval_s=0.2)
    assert loop.pc_test is True
    updates = loop._read_hardware()
    assert updates == {}
    assert client.sensors == []


def test_sensor_loop_reads_hardware_when_not_pc(monkeypatch):
    monkeypatch.delenv("SENTRYBOT_PC_TEST", raising=False)
    monkeypatch.delenv("SENTRYBOT_PROFILE", raising=False)
    world = World()
    client = Client()
    loop = SensorFeedbackLoop(world, client=client, skip_hardware_on_pc=True)
    loop._read_hardware()
    assert client.sensors == ["ultra_read", "imu_read", "rfid_last"]


def test_due_budget_blocks_until_interval():
    loop = SensorFeedbackLoop(World(), client=Client())
    assert loop._due("x", 5.0, 100.0) is True
    assert loop._due("x", 5.0, 101.0) is False
    assert loop._due("x", 5.0, 106.0) is True


def test_sensor_loop_temporarily_boosts_after_recent_high_urgency():
    class Laya:
        enabled = True
        high_urgency_threshold = 1.5
        sensor_boost_hz = 5.0
        sensor_boost_hold_s = 8.0

        @staticmethod
        def get_telemetry():
            return {"last_decisions": [{"urgency": 2.0, "timestamp": time.time()}]}

    loop = SensorFeedbackLoop(World(), poll_hz=2.0, laya_engine=Laya())
    assert loop._current_loop_interval() == 0.2


def test_sensor_loop_ignores_stale_high_urgency():
    class Laya:
        enabled = True
        high_urgency_threshold = 1.5
        sensor_boost_hz = 5.0
        sensor_boost_hold_s = 1.0

        @staticmethod
        def get_telemetry():
            return {"last_decisions": [{"urgency": 2.0, "timestamp": time.time() - 5.0}]}

    loop = SensorFeedbackLoop(World(), poll_hz=2.0, laya_engine=Laya())
    assert loop._current_loop_interval() == loop.loop_interval

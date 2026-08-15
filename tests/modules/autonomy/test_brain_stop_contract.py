from modules.autonomy.services.brain import AutonomyBrain


class _Agent:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


class _Thread:
    def __init__(self):
        self.join_calls = 0

    def join(self):
        self.join_calls += 1


def test_brain_stop_halts_loop_agent_and_thread():
    brain = object.__new__(AutonomyBrain)
    brain.running = True
    brain.agent = _Agent()
    brain.thread = _Thread()

    brain.stop()

    assert brain.running is False
    assert brain.agent.stop_calls == 1
    assert brain.thread.join_calls == 1
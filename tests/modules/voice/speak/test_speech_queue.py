import pytest
from modules.voice.speak.services.speech_queue import SpeechPriorityQueue, SpeechPriority

def test_speech_queue_order():
    q = SpeechPriorityQueue()
    q.submit("Hava biraz serin gibi.", priority=SpeechPriority.IDLE_CHATTER)
    q.submit("Evet, ışıkları kapatıyorum.", priority=SpeechPriority.USER_RESPONSE)
    q.submit("Dikkat! Batarya kritik seviyede!", priority=SpeechPriority.EMERGENCY)

    # 1. First must be EMERGENCY
    req1 = q.get_next()
    assert req1.text == "Dikkat! Batarya kritik seviyede!"

    # 2. Second must be USER_RESPONSE
    req2 = q.get_next()
    assert req2.text == "Evet, ışıkları kapatıyorum."

    # 3. Third must be IDLE_CHATTER
    req3 = q.get_next()
    assert req3.text == "Hava biraz serin gibi."

def test_speech_preemption_callback():
    stopped = False
    def _on_stop():
        nonlocal stopped
        stopped = True

    q = SpeechPriorityQueue(stop_callback=_on_stop)
    q.submit("Bugün ne yapsak acaba...", priority=SpeechPriority.IDLE_CHATTER)
    _ = q.get_next()  # Started playing idle chatter

    # High priority arrives
    q.submit("Tehlike sezildi!", priority=SpeechPriority.EMERGENCY)
    assert stopped  # Low priority was interrupted!

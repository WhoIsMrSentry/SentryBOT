from __future__ import annotations
"""Liveliness Starter

Gateway altında çalışan modüllerle basit bir canlılık döngüsü:
- Heartbeat: periyodik calm olayı (interactions)
- Idle lookaround: küçük pan/tilt salınım (vision/track)

Bu script üretim için hafiftir; Scheduler modülü ile entegre edilmesi önerilir.
"""
import time
import math
import requests

INTERACTIONS_EVENT = "http://localhost:8080/interactions/event"
VISION_TRACK = "http://localhost:8080/vision/track"

def heartbeat(interval_s: float = 30.0):
    try:
        requests.post(INTERACTIONS_EVENT, json={"type": "autonomy.calm"}, timeout=0.5)
    except Exception:
        pass
    time.sleep(interval_s)

def lookaround(t: float):
    # Small sinusoidal pan/tilt movement
    pan = 90 + 10 * math.sin(t / 5.0)
    tilt = 90 + 5 * math.cos(t / 7.0)
    try:
        requests.post(VISION_TRACK, params={"head_pan": pan, "head_tilt": tilt}, timeout=0.5)
    except Exception:
        pass

def run():
    t = 0.0
    last_heartbeat = 0.0
    hb_interval = 30.0
    look_interval = 3.0
    while True:
        now = time.time()
        if now - last_heartbeat > hb_interval:
            heartbeat(0.0)
            last_heartbeat = now
        lookaround(t)
        t += look_interval
        time.sleep(look_interval)

if __name__ == "__main__":
    run()
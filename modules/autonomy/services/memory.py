import time
from collections import deque

class ShortTermMemory:
    def __init__(self, max_items=10):
        self.events = deque(maxlen=max_items)
        
    def add_event(self, description):
        timestamp = time.strftime("%H:%M:%S")
        self.events.append(f"[{timestamp}] {description}")
        
    def get_recent_events(self, limit=5):
        return list(self.events)[-limit:]
        
    def clear(self):
        self.events.clear()

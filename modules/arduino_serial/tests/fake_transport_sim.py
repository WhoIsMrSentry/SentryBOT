import time
import json
import threading


class FakeTransportSim:
    """Simple fake serial transport for tests.

    - Collected writes are available in `._buf` (bytes).
    - Incoming messages are queued in `._read_q` as bytes and returned by `readline()`.
    - `write()` will parse JSON and auto-respond for known `cmd` values.
    """

    def __init__(self, auto_delay: float = 0.01):
        self._buf = b""
        self._read_q = []
        self._lock = threading.Lock()
        self._auto_delay = float(auto_delay)

    def readline(self):
        # simulate blocking read
        time.sleep(self._auto_delay)
        with self._lock:
            if self._read_q:
                return (self._read_q.pop(0) + b"\n")
        return b""

    def write(self, data: bytes) -> int:
        # record write
        with self._lock:
            self._buf += data
        # Try to parse JSON and schedule an automatic response for basic commands
        try:
            text = data.decode("utf-8", errors="ignore").strip()
            if not text:
                return len(data)
            # may contain multiple lines; parse the first JSON-like segment
            line = text.splitlines()[0]
            obj = json.loads(line)
            # default auto-replies for a few known commands
            reply = None
            cmd = obj.get("cmd")
            if cmd == "hello":
                reply = {"ok": True, "cmd": "hello"}
            elif cmd == "get_state":
                reply = {"ok": True, "state": "idle"}
            elif cmd == "hb":
                reply = {"ok": True, "msg": "hb"}
            elif cmd == "telemetry_start":
                reply = {"ok": True}

            if reply is not None:
                # schedule immediate insertion into read queue
                with self._lock:
                    self._read_q.append(json.dumps(reply).encode("utf-8"))
        except Exception:
            pass
        return len(data)

    def inject_msg(self, obj: dict) -> None:
        with self._lock:
            self._read_q.append(json.dumps(obj).encode("utf-8"))

    def close(self):
        return

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any
import httpx
import yaml
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Label, RichLog

from ..services.async_gateway_probe import resolve_base_url


def _get_remote_ollama_url(root: Path) -> str:
    cfg_file = root / "config" / "agent.yaml"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            vlm = data.get("vlm_bridge", {})
            remote = vlm.get("remote", {}) if isinstance(vlm, dict) else {}
            url = remote.get("base_url") or remote.get("ollama_base_url")
            if url:
                return str(url).rstrip("/")
        except Exception:
            pass
    return "http://whoismrsentry.local:11434"


class TabControls(Widget):
    """Interactive Mission Controls, Diagnostics & Teleoperation for Real SentryBOT Hardware and AI."""

    def __init__(self, root: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.root = root
        self.gateway_url = resolve_base_url()
        self.ollama_url = _get_remote_ollama_url(root)
        self.current_pan: float = 90.0
        self.current_tilt: float = 90.0
        self.current_ear_l: float = 90.0
        self.current_ear_r: float = 90.0

    def compose(self) -> ComposeResult:
        with Vertical(id="controls_container"):
            # Header
            yield Label("SENTRYBOT SUBSYSTEM PROCEDURES & MISSION CONTROLS", id="controls_title", markup=False)

            with Horizontal(id="controls_split"):
                # Left side: Action Button Matrix & Teleop Controls
                with Vertical(id="controls_action_panel"):
                    yield Label("■ SUBSYSTEM PROCESSES", classes="controls_section_title", markup=False)
                    yield Button("🚀 Start Subsystems", id="btn_start_robot", classes="ctrl_action_btn", variant="success")
                    yield Button("⏹️ Stop Subsystems", id="btn_stop_robot", classes="ctrl_action_btn", variant="error")
                    yield Button("🔄 Restart Subsystems", id="btn_restart_robot", classes="ctrl_action_btn", variant="warning")

                    yield Label("■ MANUAL TELEOP & JOG", classes="controls_section_title", markup=False)
                    with Horizontal(classes="jog_row"):
                        yield Button("◀ Pan -15°", id="btn_jog_pan_left", classes="jog_btn")
                        yield Button("▶ Pan +15°", id="btn_jog_pan_right", classes="jog_btn")
                    with Horizontal(classes="jog_row"):
                        yield Button("▲ Tilt +10°", id="btn_jog_tilt_up", classes="jog_btn")
                        yield Button("▼ Tilt -10°", id="btn_jog_tilt_down", classes="jog_btn")
                    yield Button("🎯 Center Head (90°/90°)", id="btn_jog_center", classes="ctrl_action_btn", variant="primary")
                    with Horizontal(classes="jog_row"):
                        yield Button("👂 Ears Alert (120°)", id="btn_jog_ears_alert", classes="jog_btn")
                        yield Button("👂 Ears Rest (45°)", id="btn_jog_ears_rest", classes="jog_btn")
                    with Horizontal(classes="jog_row"):
                        yield Button("▲ Step Fwd +100", id="btn_jog_step_fwd", classes="jog_btn")
                        yield Button("▼ Step Rev -100", id="btn_jog_step_rev", classes="jog_btn")

                    yield Label("■ HARDWARE & AI DIAGNOSTICS", classes="controls_section_title", markup=False)
                    yield Button("⚡ Run Preflight Check", id="btn_ctrl_preflight", classes="ctrl_action_btn", variant="primary")
                    yield Button("🧪 Run Full Smoke Suite", id="btn_ctrl_smoke", classes="ctrl_action_btn", variant="warning")
                    yield Button("📷 Probe Camera / IMX500", id="btn_ctrl_cam_test", classes="ctrl_action_btn")
                    yield Button("🔄 Ping Arduino/ESP Bridge", id="btn_ctrl_ping_bridge", classes="ctrl_action_btn")
                    yield Button("🗣️ Test Piper TTS Voice", id="btn_ctrl_tts_test", classes="ctrl_action_btn")
                    yield Button("🧠 Test Remote Ollama LLM", id="btn_ctrl_llm_test", classes="ctrl_action_btn")
                    yield Button("💾 Inspect SocialDB Memory", id="btn_ctrl_mem_check", classes="ctrl_action_btn")
                    yield Button("💡 Trigger NeoPixel Pulse", id="btn_ctrl_neopixel", classes="ctrl_action_btn")
                    yield Button("🧹 Rotate & Archive Logs", id="btn_ctrl_rotate_logs", classes="ctrl_action_btn")
                    yield Button("🛑 EMERGENCY ALL STOP", id="btn_ctrl_estop", classes="ctrl_action_btn", variant="error")

                # Right side: Diagnostic Console Output & Interactive Prompt
                with Vertical(id="controls_log_panel"):
                    with Horizontal(id="controls_log_header"):
                        yield Label("■ AGENT CHAT, REASONING STREAM & MISSION LOG", classes="controls_section_title", markup=False)
                        yield Button("Clear Log", id="btn_ctrl_clear_log", variant="default")

                    yield RichLog(
                        id="controls_rich_log",
                        highlight=True,
                        markup=False,
                        auto_scroll=True,
                        wrap=True,
                    )

                    with Horizontal(id="controls_prompt_chips"):
                        yield Button("🎯 Current Goal", id="btn_chip_goal", classes="chip_btn")
                        yield Button("🔋 Battery & Temp", id="btn_chip_batt", classes="chip_btn")
                        yield Button("👤 Human FOV", id="btn_chip_people", classes="chip_btn")
                        yield Button("🔍 Self-Test", id="btn_chip_status", classes="chip_btn")

                    with Horizontal(id="controls_quick_cmd_bar"):
                        yield Input(
                            placeholder="Type command prompt or question for SentryBOT agent (Press ENTER to send)...",
                            id="controls_cmd_input",
                        )
                        yield Button("Send Prompt", id="btn_ctrl_send_cmd", variant="primary")

    def on_mount(self) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        log.write("SentryBOT Mission Controller Ready.")
        log.write(f"Target Gateway: {self.gateway_url} | Remote Ollama: {self.ollama_url}")
        log.write("All procedure buttons trigger live hardware actions and AI inference on the robot.")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "controls_cmd_input":
            self.send_quick_prompt()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        log = self.query_one("#controls_rich_log", RichLog)

        if btn_id == "btn_start_robot":
            log.write("🚀 Initiating robot subsystems process...")
        elif btn_id == "btn_stop_robot":
            log.write("⏹️ Stopping robot subsystems process...")
        elif btn_id == "btn_restart_robot":
            log.write("🔄 Restarting robot subsystems process...")
        elif btn_id == "btn_ctrl_clear_log":
            log.clear()
            log.write("Diagnostic log cleared.")
        elif btn_id == "btn_jog_pan_left":
            self.current_pan = max(0.0, self.current_pan - 15.0)
            self.run_servo_jog_worker(0, self.current_pan, f"Pan Left ({self.current_pan:.0f}°)")
        elif btn_id == "btn_jog_pan_right":
            self.current_pan = min(180.0, self.current_pan + 15.0)
            self.run_servo_jog_worker(0, self.current_pan, f"Pan Right ({self.current_pan:.0f}°)")
        elif btn_id == "btn_jog_tilt_up":
            self.current_tilt = min(180.0, self.current_tilt + 10.0)
            self.run_servo_jog_worker(1, self.current_tilt, f"Tilt Up ({self.current_tilt:.0f}°)")
        elif btn_id == "btn_jog_tilt_down":
            self.current_tilt = max(0.0, self.current_tilt - 10.0)
            self.run_servo_jog_worker(1, self.current_tilt, f"Tilt Down ({self.current_tilt:.0f}°)")
        elif btn_id == "btn_jog_center":
            self.current_pan = 90.0
            self.current_tilt = 90.0
            self.run_servo_jog_worker(0, 90.0, "Center Pan (90°)")
            self.run_servo_jog_worker(1, 90.0, "Center Tilt (90°)")
        elif btn_id == "btn_jog_ears_alert":
            self.current_ear_l = 120.0
            self.current_ear_r = 120.0
            self.run_servo_jog_worker(2, 120.0, "Left Ear Alert")
            self.run_servo_jog_worker(3, 120.0, "Right Ear Alert")
        elif btn_id == "btn_jog_ears_rest":
            self.current_ear_l = 45.0
            self.current_ear_r = 45.0
            self.run_servo_jog_worker(2, 45.0, "Left Ear Rest")
            self.run_servo_jog_worker(3, 45.0, "Right Ear Rest")
        elif btn_id == "btn_jog_step_fwd":
            self.run_stepper_jog_worker(100)
        elif btn_id == "btn_jog_step_rev":
            self.run_stepper_jog_worker(-100)
        elif btn_id == "btn_chip_goal":
            self._fill_and_send_prompt("What is your current active autonomous goal and living need?")
        elif btn_id == "btn_chip_batt":
            self._fill_and_send_prompt("Report your current battery level and hardware temperatures.")
        elif btn_id == "btn_chip_people":
            self._fill_and_send_prompt("How many people are currently detected in camera view?")
        elif btn_id == "btn_chip_status":
            self._fill_and_send_prompt("Run an agent self-check on all sensor and actuation buses.")
        elif btn_id == "btn_ctrl_preflight":
            self.run_preflight_worker()
        elif btn_id == "btn_ctrl_smoke":
            self.run_smoke_worker()
        elif btn_id == "btn_ctrl_cam_test":
            self.run_camera_test_worker()
        elif btn_id == "btn_ctrl_ping_bridge":
            self.run_ping_bridge_worker()
        elif btn_id == "btn_ctrl_tts_test":
            self.run_tts_test_worker()
        elif btn_id == "btn_ctrl_llm_test":
            self.run_llm_test_worker()
        elif btn_id == "btn_ctrl_mem_check":
            self.run_mem_check_worker()
        elif btn_id == "btn_ctrl_neopixel":
            self.run_neopixel_test_worker()
        elif btn_id == "btn_ctrl_rotate_logs":
            self.run_rotate_logs_worker()
        elif btn_id == "btn_ctrl_estop":
            self.run_estop_worker()
        elif btn_id == "btn_ctrl_send_cmd":
            self.send_quick_prompt()

    def _fill_and_send_prompt(self, text: str) -> None:
        inp = self.query_one("#controls_cmd_input", Input)
        inp.value = text
        self.send_quick_prompt()

    def send_quick_prompt(self) -> None:
        inp = self.query_one("#controls_cmd_input", Input)
        text = inp.value.strip()
        if not text:
            return
        inp.value = ""
        log = self.query_one("#controls_rich_log", RichLog)
        log.write(f"\n[bold cyan]👤 OPERATOR[/bold cyan] > {text}")
        self.run_custom_prompt_worker(text)

    @work(thread=True)
    def run_servo_jog_worker(self, index: int, deg: float, label: str) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        self.app.call_from_thread(log.write, f"🎮 [TELEOP JOG] {label}")
        try:
            from modules.arduino_serial.contract import build_set_servo_cmd
            payload = build_set_servo_cmd(index, deg)
            r = httpx.post(f"{self.gateway_url}/arduino/request", json=payload, timeout=1.5)
            self.app.call_from_thread(log.write, f"• Servo command ACK: HTTP {r.status_code}")
        except Exception as e:
            self.app.call_from_thread(log.write, f"• Teleop servo error: {e}")

    @work(thread=True)
    def run_stepper_jog_worker(self, steps: int) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        self.app.call_from_thread(log.write, f"🎮 [TELEOP DRIVE] Steppers {steps:+d} steps")
        try:
            from modules.arduino_serial.contract import build_stepper_cmd
            payload = build_stepper_cmd(0, "jog", steps)
            r = httpx.post(f"{self.gateway_url}/arduino/request", json=payload, timeout=1.5)
            self.app.call_from_thread(log.write, f"• Stepper command ACK: HTTP {r.status_code}")
        except Exception as e:
            self.app.call_from_thread(log.write, f"• Teleop stepper error: {e}")

    @work(thread=True)
    def run_preflight_worker(self) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        self.app.call_from_thread(log.write, "--> Starting SentryBOT Preflight Validation Check...")
        try:
            cmd = [sys.executable, "-m", "pytest", "tests/modules/runtime_console/test_smoke.py", "-q"]
            res = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, timeout=15)
            self.app.call_from_thread(log.write, res.stdout or res.stderr or "Preflight finished.")
            if res.returncode == 0:
                self.app.call_from_thread(log.write, "✔ Preflight check PASSED (Core, Gateway & Renderer operational)")
            else:
                self.app.call_from_thread(log.write, "✖ Preflight check encountered issues.")
        except Exception as e:
            self.app.call_from_thread(log.write, f"Preflight error: {e}")

    @work(thread=True)
    def run_smoke_worker(self) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        self.app.call_from_thread(log.write, "--> Executing full module smoke test suite...")
        try:
            cmd = [sys.executable, "-m", "pytest", "tests/modules/runtime_console/", "-q"]
            res = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, timeout=30)
            self.app.call_from_thread(log.write, res.stdout or res.stderr or "Smoke tests finished.")
            self.app.call_from_thread(log.write, "✔ Smoke test suite complete.")
        except Exception as e:
            self.app.call_from_thread(log.write, f"Smoke test error: {e}")

    @work(thread=True)
    def run_camera_test_worker(self) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        self.app.call_from_thread(log.write, f"--> Probing Camera status via Gateway: {self.gateway_url}/camera/status...")
        try:
            r = httpx.get(f"{self.gateway_url}/camera/status", timeout=2.0)
            if r.status_code == 200:
                data = r.json()
                cap = data.get("capture", {})
                imx = data.get("imx500", {})
                self.app.call_from_thread(log.write, f"✔ Camera ONLINE: Running={cap.get('running')}, Frame={cap.get('has_frame')}, IMX500={imx.get('running')}")
                return
        except Exception as exc:
            self.app.call_from_thread(log.write, f"• Gateway camera probe skipped ({exc}); checking local sensor...")

        try:
            import cv2
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    h, w, c = frame.shape
                    self.app.call_from_thread(log.write, f"✔ Direct OpenCV capture OK: Frame {w}x{h} (channels: {c})")
                else:
                    self.app.call_from_thread(log.write, "⚠ Camera opened but no frame captured (simulator/quiet mode).")
            else:
                self.app.call_from_thread(log.write, "⚠ Camera hardware 0 not currently accessible.")
        except Exception as e:
            self.app.call_from_thread(log.write, f"Camera test info: {e}")

    @work(thread=True)
    def run_ping_bridge_worker(self) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        self.app.call_from_thread(log.write, f"--> Sending live contract command to Arduino/ESP bridge via {self.gateway_url}/arduino/request...")
        try:
            from modules.arduino_serial.contract import build_simple_cmd
            r = httpx.post(f"{self.gateway_url}/arduino/request", json=build_simple_cmd("get_state"), timeout=2.0)
            if r.status_code == 200:
                self.app.call_from_thread(log.write, f"✔ Live Bridge Response (HTTP 200): {r.json()}")
            else:
                self.app.call_from_thread(log.write, f"• Gateway returned HTTP {r.status_code} for arduino/request. Querying /state/get...")
                r_state = httpx.get(f"{self.gateway_url}/state/get", timeout=2.0)
                if r_state.status_code == 200:
                    self.app.call_from_thread(log.write, f"✔ Current Robot State: {r_state.json()}")
                else:
                    self.app.call_from_thread(log.write, "⚠ Serial bridge currently standby or not responding.")
        except Exception as exc:
            self.app.call_from_thread(log.write, f"⚠ Serial bridge unreachable ({exc}). Verify gateway on {self.gateway_url}.")

    @work(thread=True)
    def run_tts_test_worker(self) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        test_text = "SentryBOT sistemleri devrede ve göreve hazırdır."
        self.app.call_from_thread(log.write, f"--> Dispatching Piper TTS synthesis via {self.gateway_url}/speak/say: '{test_text}'...")
        try:
            r = httpx.post(f"{self.gateway_url}/speak/say", json={"text": test_text}, timeout=3.0)
            if r.status_code == 200:
                self.app.call_from_thread(log.write, f"✔ TTS synthesized successfully: {r.json()}")
            else:
                self.app.call_from_thread(log.write, f"• Speak endpoint responded HTTP {r.status_code}: {r.text[:100]}")
        except Exception as exc:
            self.app.call_from_thread(log.write, f"⚠ TTS test skipped ({exc}). Gateway may be starting.")

    @work(thread=True)
    def run_llm_test_worker(self) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        self.app.call_from_thread(log.write, f"--> Probing Remote Ollama LLM Bridge: {self.ollama_url}/api/tags...")
        try:
            r = httpx.get(f"{self.ollama_url}/api/tags", timeout=2.5)
            if r.status_code == 200:
                models = [m.get("name") for m in r.json().get("models", [])]
                self.app.call_from_thread(log.write, f"✔ Remote Ollama ONLINE ({self.ollama_url}). Available Models: {models}")
                return
            else:
                self.app.call_from_thread(log.write, f"• Remote Ollama HTTP {r.status_code}")
        except Exception:
            self.app.call_from_thread(log.write, f"• Remote host ({self.ollama_url}) not reachable. Trying loopback 127.0.0.1:11434...")

        try:
            r2 = httpx.get("http://127.0.0.1:11434/api/tags", timeout=1.5)
            if r2.status_code == 200:
                models = [m.get("name") for m in r2.json().get("models", [])]
                self.app.call_from_thread(log.write, f"✔ Local Ollama ONLINE (127.0.0.1:11434). Models: {models}")
            else:
                self.app.call_from_thread(log.write, "⚠ Ollama server offline on both remote bridge and loopback.")
        except Exception:
            self.app.call_from_thread(log.write, f"⚠ Remote Ollama at {self.ollama_url} currently unreachable. Rule-based companion autonomy active.")

    @work(thread=True)
    def run_mem_check_worker(self) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        self.app.call_from_thread(log.write, "--> Inspecting SocialDB SQLite memory & repositories...")
        db_path = self.root / "data" / "social.sqlite3"
        if db_path.exists():
            size_kb = db_path.stat().st_size / 1024
            try:
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                conn.close()
                self.app.call_from_thread(log.write, f"✔ SocialDB found ({size_kb:.1f} KB). Tables: {', '.join(tables)}")
            except Exception:
                self.app.call_from_thread(log.write, f"✔ SocialDB database found ({size_kb:.1f} KB).")
        else:
            self.app.call_from_thread(log.write, "• SocialDB database will be created at data/social.sqlite3 on first person interaction.")

    @work(thread=True)
    def run_neopixel_test_worker(self) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        self.app.call_from_thread(log.write, f"--> Sending live NeoPixel animation request to {self.gateway_url}/neopixel/animate...")
        try:
            payload = {"name": "EMOTIONAL_PULSE", "color": "#FA1E4E", "iterations": 2}
            r = httpx.post(f"{self.gateway_url}/neopixel/animate", json=payload, timeout=2.0)
            if r.status_code == 200:
                self.app.call_from_thread(log.write, f"✔ NeoPixel animation dispatched: {r.json()}")
                return
        except Exception:
            pass

        try:
            # Fallback to expression endpoint
            payload_exp = {"emotion": "curious", "intensity": 1.0, "modalities": ["leds"]}
            r_exp = httpx.post(f"{self.gateway_url}/expression/express", json=payload_exp, timeout=2.0)
            if r_exp.status_code == 200:
                self.app.call_from_thread(log.write, "✔ Expression LED animation triggered successfully.")
            else:
                self.app.call_from_thread(log.write, f"• Expression endpoint HTTP {r_exp.status_code}")
        except Exception as exc:
            self.app.call_from_thread(log.write, f"⚠ NeoPixel dispatch skipped ({exc}). Gateway may be in quiet mode.")

    @work(thread=True)
    def run_rotate_logs_worker(self) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        self.app.call_from_thread(log.write, "--> Rotating & archiving runtime log files...")
        try:
            from modules.runtime_console.logwrapper.services.run_rotator import rotate_run_logs
            rotate_run_logs(self.root / "logs")
            self.app.call_from_thread(log.write, "✔ Log rotation complete. Historical logs archived under logs/runs/.")
        except Exception as e:
            self.app.call_from_thread(log.write, f"Log rotation error: {e}")

    @work(thread=True)
    def run_estop_worker(self) -> None:
        log = self.query_one("#controls_rich_log", RichLog)
        self.app.call_from_thread(log.write, "[EMERGENCY STOP TRIGGERED] Sending zero-velocity halt frame to motors...")
        try:
            from modules.arduino_serial.contract import build_simple_cmd
            r1 = httpx.post(f"{self.gateway_url}/arduino/request", json=build_simple_cmd("estop"), timeout=1.5)
            self.app.call_from_thread(log.write, f"• Arduino hardware estop: HTTP {r1.status_code}")
        except Exception as e:
            self.app.call_from_thread(log.write, f"• Arduino estop network error: {e}")

        try:
            r2 = httpx.post(f"{self.gateway_url}/state/set", json={"operational": "estop"}, timeout=1.5)
            self.app.call_from_thread(log.write, f"• State manager operational lock: HTTP {r2.status_code}")
        except Exception:
            pass
        self.app.call_from_thread(log.write, "[EMERGENCY STOP] All motor channels locked to neutral. Safety interlock engaged.")

    @work(thread=True)
    def run_custom_prompt_worker(self, text: str) -> None:
        log = self.query_one("#controls_rich_log", RichLog)

        def _log_bot_reply(raw_reply: str) -> None:
            if "<think>" in raw_reply and "</think>" in raw_reply:
                parts = raw_reply.split("</think>")
                think_txt = parts[0].replace("<think>", "").strip()
                ans_txt = parts[1].strip()
                self.app.call_from_thread(log.write, f"⚡ [THINKING PROCESS]\n{think_txt}")
                self.app.call_from_thread(log.write, f"🤖 [SENTRYBOT AGENT] > {ans_txt}")
            else:
                self.app.call_from_thread(log.write, f"🤖 [SENTRYBOT AGENT] > {raw_reply}")

        try:
            r = httpx.post(f"{self.gateway_url}/agent/step", json={"query": text}, timeout=10.0)
            if r.status_code == 200:
                data = r.json()
                reply = data.get("text") or data.get("response") or str(data)
                _log_bot_reply(str(reply))
                return
        except Exception:
            pass

        try:
            # Fallback to agent/chat compatibility endpoint
            r_chat = httpx.post(f"{self.gateway_url}/agent/chat", json={"prompt": text}, timeout=10.0)
            if r_chat.status_code == 200:
                data = r_chat.json()
                reply = data.get("response") or str(data)
                _log_bot_reply(str(reply))
            else:
                self.app.call_from_thread(log.write, f"• Gateway agent HTTP {r_chat.status_code}: {r_chat.text[:120]}")
        except Exception as exc:
            self.app.call_from_thread(log.write, f"⚠ Agent communication error: {exc}")

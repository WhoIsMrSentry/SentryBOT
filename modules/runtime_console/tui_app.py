from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from rich.markup import escape
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Label, TabbedContent, TabPane

from .services.async_gateway_probe import AsyncGatewayProbe
from .services.async_log_streamer import AsyncLogStreamer, ParsedLogEntry
from .services.async_robot_manager import AsyncRobotManager
from .services.console_constants import APP, VERSION
from .services.system_info_collector import get_cpu_info, get_memory_info
from .services.system_info_hardware import get_disk_info
from .services.console_helpers import is_pc_test
from .themes import DEFAULT_THEME_NAME, THEMES
from .widgets.modal_sysinfo import SysInfoModal
from .widgets.modal_theme import ThemeSelectorModal
from .widgets.tab_config import TabConfig
from .widgets.tab_controls import TabControls
from .widgets.tab_logs import TabLogs
from .widgets.tab_main import TabMain, _progress_bar
from .widgets.tab_telemetry import TabTelemetry

# Log sources to suppress from the UI (noisy HTTP connection internals)
_SUPPRESSED_LOG_SOURCES = (
    "urllib3.connectionpool",
    "httpcore.connection",
    "httpcore.http11",
    "httpx._client",
    "httpx",
    "asyncio",
)


class SentryBotApp(App[int]):
    """SentryBOT High-Density Control Center - Powered by Textual & Cyber-Crimson Design."""

    CSS_PATH = "sentrybot.tcss"
    TITLE = "SentryBOT Control Center"
    SUB_TITLE = f"v{VERSION}"

    BINDINGS = [
        ("f1", "switch_tab('tab_main')", "Main"),
        ("f2", "switch_tab('tab_logs')", "Logs"),
        ("f3", "switch_tab('tab_telemetry')", "Telemetry"),
        ("f4", "switch_tab('tab_controls')", "Controls"),
        ("f5", "switch_tab('tab_config')", "Config"),
        ("f6", "action_theme_select", "Theme"),
        ("t", "action_theme_select", "Theme"),
        ("ctrl+p", "action_theme_select", "Theme"),
        ("f7", "action_sysinfo", "SysInfo"),
        ("i", "action_sysinfo", "SysInfo"),
        ("ctrl+r", "action_restart_robot", "Restart"),
        ("ctrl+k", "action_stop_robot", "Stop"),
        ("ctrl+l", "action_clear_logs", "Clear Logs"),
        ("slash", "action_focus_search", "Search"),
        ("q", "action_quit", "Quit"),
        ("ctrl+c", "action_quit", "Quit"),
    ]

    def __init__(
        self,
        root: Optional[Path] = None,
        run_robot: bool = True,
        profile: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.root = (root or Path.cwd()).resolve()
        self.run_robot = run_robot
        # Auto-detect: Pi -> "robot", PC -> "pc-test"
        if profile is not None:
            self.profile = profile
        else:
            self.profile = "pc-test" if is_pc_test(self.root) else "robot"

        # Async Services
        self.robot_manager = AsyncRobotManager(self.root, profile=self.profile)
        self.log_streamer = AsyncLogStreamer(self.root)
        self.gateway_probe = AsyncGatewayProbe()

        # Register all themes
        for name, theme_obj in THEMES.items():
            try:
                self.register_theme(theme_obj)
            except Exception:
                pass

        from .themes import get_saved_theme_name
        self.theme = get_saved_theme_name()

    def compose(self) -> ComposeResult:
        profile_label = (self.profile or "ROBOT").upper()
        theme_label = (self.theme or "SENTRY-CRIMSON").upper()

        # High-Tech Header
        with Horizontal(id="app_header"):
            yield Label(f"■ {APP} CONTROL CENTER", id="header_title", markup=False)
            yield Label(f"[ PROFILE: {profile_label} ]", id="header_status_badge", markup=False)
            yield Label(f"{VERSION} | THEME: {theme_label} | Subsystems Active", id="header_info_bar", markup=False)

        # 5 High-Utility Dense Tabs
        with TabbedContent(initial="tab_main", id="app_tabs"):
            with TabPane(" 01: MAIN ", id="tab_main"):
                yield TabMain(id="view_main")
            with TabPane(" 02: LOGS ", id="tab_logs"):
                yield TabLogs(id="view_logs")
            with TabPane(" 03: TELEMETRY ", id="tab_telemetry"):
                yield TabTelemetry(id="view_telemetry")
            with TabPane(" 04: CONTROLS ", id="tab_controls"):
                yield TabControls(self.root, id="view_controls")
            with TabPane(" 05: CONFIG ", id="tab_config"):
                yield TabConfig(self.root, id="view_config")

        # Footer with Hotkeys
        yield Footer()

    async def on_mount(self) -> None:
        # Start background workers
        self.start_log_streaming_worker()

        if self.run_robot:
            await self.robot_manager.start()

        # Immediate telemetry tick then periodic fast poller (every 1.0s)
        await self.periodic_telemetry_tick()
        self.set_interval(1.0, self.periodic_telemetry_tick)

    @work(exclusive=True)
    async def start_log_streaming_worker(self) -> None:
        """Run log tailing as an async task on the main Textual event loop."""
        def handle_entry(entry: ParsedLogEntry, rich_text) -> None:
            self._push_log_to_ui(entry, rich_text)

        try:
            await self.log_streamer.stream_logs(handle_entry)
        except (asyncio.CancelledError, Exception):
            pass

    def _push_log_to_ui(self, entry: ParsedLogEntry, rich_text) -> None:
        # Filter noisy internal HTTP logs
        if any(src in entry.raw for src in _SUPPRESSED_LOG_SOURCES):
            return

        try:
            tab_logs = self.query_one("#view_logs", TabLogs)
            tab_logs.add_log_entry(entry, rich_text)
        except Exception:
            pass

        self._analyze_log_for_service_status(entry)

    def _analyze_log_for_service_status(self, entry: ParsedLogEntry) -> None:
        raw_l = entry.raw.lower()
        try:
            tab_main = self.query_one("#view_main", TabMain)
        except Exception:
            return

        # Core
        if "application startup complete" in raw_l or "uvicorn running" in raw_l:
            tab_main.update_service_card("CORE", "OK", "Runtime and Gateway active")
        elif "shutdown" in raw_l:
            tab_main.update_service_card("CORE", "IDLE", "System stopping")

        # AI
        if "llm provider client ready" in raw_l or "ollama model ready" in raw_l:
            tab_main.update_service_card("AI", "OK", "LLM inference online")
        elif "ollama unavailable" in raw_l or "llm chat failed" in raw_l or "connection refused" in raw_l:
            is_pc = self.profile == "pc-test"
            tab_main.update_service_card("AI", "WARN", "Ollama/LLM endpoint offline", is_pc_expected=is_pc)

        # Vision
        if "vision llm client initialized" in raw_l or "person db loaded" in raw_l:
            tab_main.update_service_card("VISION", "OK", "VLM / Camera engine active")
        elif "opencv not available" in raw_l:
            tab_main.update_service_card("VISION", "WARN", "OpenCV fallback active", is_pc_expected=True)

        # Audio
        if "wakeword listening started" in raw_l or "speecharbiter started" in raw_l:
            tab_main.update_service_card("AUDIO", "OK", "Wakeword & STT listening")
        elif "stt unavailable" in raw_l or "speech/stt unavailable" in raw_l:
            is_pc = self.profile == "pc-test"
            tab_main.update_service_card("AUDIO", "WARN", "Microphone / STT not connected", is_pc_expected=is_pc)

        # TTS
        if "first audio" in raw_l or "piper started" in raw_l:
            tab_main.update_service_card("TTS", "OK", "Piper TTS speaker ready")
        elif "piper unavailable" in raw_l or "piper model missing" in raw_l:
            is_pc = self.profile == "pc-test"
            tab_main.update_service_card("TTS", "WARN", "Piper voice model missing", is_pc_expected=is_pc)

        # Move
        if "esp bridge connected" in raw_l or "arduino ready" in raw_l:
            tab_main.update_service_card("MOVE", "OK", "ESP32 serial bridge connected")
        elif "esp bridge unreachable" in raw_l:
            tab_main.update_service_card("MOVE", "WARN", "ESP bridge unreachable", is_pc_expected=True)

    async def periodic_telemetry_tick(self) -> None:
        """Asynchronous poller for process, hardware, and gateway health."""
        proc_status = self.robot_manager.check_liveness()
        gateway_online = await self.gateway_probe.probe_all()
        latency_ms = self.gateway_probe.last_probe_ms

        # Read system resource metrics
        cpu_name, cpu_cores, cpu_freq, cpu_usage_raw = get_cpu_info()
        mem_used, mem_total = get_memory_info()
        disk_used, disk_total = get_disk_info()

        # Parse CPU percentage
        try:
            clean_pct = str(cpu_usage_raw).replace("%", "").strip()
            cpu_pct = float(clean_pct) if clean_pct != "?" else 0.0
        except Exception:
            cpu_pct = 0.0

        usage_display = cpu_usage_raw if cpu_usage_raw != "?" else "-%"
        freq_disp = f" @ {cpu_freq}" if cpu_freq and cpu_freq != "?" else ""
        cpu_str = f"{usage_display} [{_progress_bar(cpu_pct, 10)}] ({cpu_cores}C{freq_disp})"
        mem_str = f"{mem_used} / {mem_total}"
        disk_str = f"{disk_used} / {disk_total}"
        proc_str = f"{proc_status} | {self.robot_manager.uptime_str} [PID:{self.robot_manager.pid or '-'}]"
        gw_str = f"OK ({latency_ms:.0f}ms)" if gateway_online else "OFFLINE"

        # Calculate RAM usage percentage
        try:
            u_num = float(mem_used.split()[0])
            t_num = float(mem_total.split()[0])
            ram_pct = (u_num / t_num) * 100.0 if t_num > 0 else 0.0
        except Exception:
            ram_pct = 0.0

        # ---- TAB 1: MAIN DASHBOARD ----
        try:
            tab_main = self.query_one("#view_main", TabMain)
            tab_main.update_hero_metrics(
                cpu_str, mem_str, disk_str, proc_str, gw_str,
                cpu_val=cpu_pct, ram_val=ram_pct, gw_latency_ms=latency_ms,
            )

            # Real data from gateway subsystems
            comp_data = self.gateway_probe.companion_data
            cam_data = self.gateway_probe.camera_data
            exp_data = self.gateway_probe.expression_data
            health_data = self.gateway_probe.health_data
            state_data = health_data.get("state", {}) if isinstance(health_data, dict) else {}
            if not isinstance(state_data, dict):
                state_data = {}

            # --- Panel 1: Living Needs & Autonomy (real gateway data) ---
            scores = comp_data.get("scores", {}) if isinstance(comp_data, dict) else {}
            if not isinstance(scores, dict):
                scores = {}
            c_val = float(scores.get("curiosity", 0)) * 100.0 if scores else 0
            b_val = float(scores.get("boredom", 0)) * 100.0 if scores else 0
            s_val = float(scores.get("social", 0)) * 100.0 if scores else 0
            r_val = float(scores.get("rest", 0)) * 100.0 if scores else 0
            sf_val = float(scores.get("safety", 0)) * 100.0 if scores else 0
            goal = comp_data.get("recommended_goal", "-") if comp_data else "-"

            if comp_data:
                comp_text = (
                    f"• Curiosity  : [{_progress_bar(c_val, 10)}] {c_val:.0f}%\n"
                    f"• Boredom    : [{_progress_bar(b_val, 10)}] {b_val:.0f}%\n"
                    f"• Social     : [{_progress_bar(s_val, 10)}] {s_val:.0f}%\n"
                    f"• Rest       : [{_progress_bar(r_val, 10)}] {r_val:.0f}%\n"
                    f"• Safety     : [{_progress_bar(sf_val, 10)}] {sf_val:.0f}%\n"
                    f"• Goal       : {goal}"
                )
            else:
                comp_text = (
                    "• Curiosity  : [░░░░░░░░░░]  -\n"
                    "• Boredom    : [░░░░░░░░░░]  -\n"
                    "• Social     : [░░░░░░░░░░]  -\n"
                    "• Rest       : [░░░░░░░░░░]  -\n"
                    "• Safety     : [░░░░░░░░░░]  -\n"
                    "• Goal       : Waiting for autonomy module..."
                )

            # --- Panel 2: Sensors & Hardware Pose (real state data) ---
            pitch = state_data.get("pitch", 0.0)
            roll = state_data.get("roll", 0.0)
            dist = state_data.get("distance_cm", 0.0)
            dist_status = "Clear Path" if dist > 50 else ("Obstacle!" if dist > 0 else "No Sensor")
            pan = state_data.get("servo_pan", 0.0)
            tilt = state_data.get("servo_tilt", 0.0)
            ear_l = state_data.get("ear_l", 0.0)
            ear_r = state_data.get("ear_r", 0.0)
            emotion = exp_data.get("emotion", "-") if exp_data else "-"
            anim = exp_data.get("current_animation", "-") if exp_data else "-"

            if state_data or exp_data:
                attention_text = (
                    f"• IMU Orientation : Pitch: {pitch:.1f}° | Roll: {roll:.1f}°\n"
                    f"• Distance Sensor : {dist:.0f} cm ({dist_status})\n"
                    f"• Servos (Pan/Tilt): P: {pan:.1f}° | T: {tilt:.1f}°\n"
                    f"• Ears (L/R)      : L: {ear_l:.0f}° | R: {ear_r:.0f}°\n"
                    f"• OLED / NeoPixel : {emotion} | {anim}\n"
                    f"• Lasers / Buzzer : Inactive / Ready"
                )
            else:
                attention_text = (
                    "• IMU Orientation : No data (gateway offline)\n"
                    "• Distance Sensor : No data\n"
                    "• Servos (Pan/Tilt): No data\n"
                    "• Ears (L/R)      : No data\n"
                    "• OLED / NeoPixel : No data\n"
                    "• Lasers / Buzzer : No data"
                )

            # --- Panel 3: Recognition & Gateway Signals (real data) ---
            faces = cam_data.get("faces_detected", 0) if cam_data else 0
            faces_str = f"{faces} (Active)" if faces > 0 else "0 (No tracks)"
            doa = state_data.get("voice_doa", 0.0)
            routers = health_data.get("routers_mounted", 0) if isinstance(health_data, dict) else 0

            status_line = "• All systems nominal."
            if not self.robot_manager.is_running:
                status_line = "• Robot subprocess STOPPED."
            elif not gateway_online:
                status_line = "• Gateway HTTP offline."
            elif self.profile == "pc-test":
                status_line = "• PC-Test mode: Hardware gaps suppressed."

            traffic_text = (
                f"• People Detected : {faces_str}\n"
                f"• DoA Voice Angle : {doa:.0f}° (I2S Stereo VAD)\n"
                f"• Social Memory   : SQLite Database Ready\n"
                f"• REST Endpoints  : {routers} Routers Mounted\n"
                f"{status_line}"
            )

            tab_main.update_telemetry(comp_text, attention_text, traffic_text)
        except Exception:
            pass

        # ---- TAB 3: TELEMETRY DEEP DIVE ----
        try:
            tab_telem = self.query_one("#view_telemetry", TabTelemetry)
            comp_data = self.gateway_probe.companion_data
            cam_data = self.gateway_probe.camera_data
            exp_data = self.gateway_probe.expression_data
            health_data = self.gateway_probe.health_data
            state_data = health_data.get("state", {}) if isinstance(health_data, dict) else {}
            if not isinstance(state_data, dict):
                state_data = {}

            # Quad 1: IMU / Distance / Spatial
            pitch = state_data.get("pitch", 0.0)
            roll = state_data.get("roll", 0.0)
            dist = state_data.get("distance_cm", 0.0)
            dist_label = "Clear Corridor" if dist > 50 else ("Obstacle" if dist > 0 else "N/A")
            pose = state_data.get("current_pose", "unknown")
            doa = state_data.get("voice_doa", 0.0)
            motion = state_data.get("motion_state", "Stationary")
            brake = "Armed" if state_data.get("safety_brake", True) else "Disarmed"

            imu_info = (
                f"• IMU Pitch / Roll : {pitch:.1f}° / {roll:.1f}°\n"
                f"• Ultrasonic Range : {dist:.0f} cm ({dist_label})\n"
                f"• Current Pose     : '{pose}'\n"
                f"• DoA Voice Angle  : {doa:.0f}° (I2S Stereo VAD)\n"
                f"• Motion State     : {motion}\n"
                f"• Safety Brake     : {brake}"
            )

            # Quad 2: ESP32 bridge / servos
            serial_port = state_data.get("serial_port", "/dev/ttyUSB0")
            protocol = state_data.get("protocol", "strict_json_contract_v2")
            pan = state_data.get("servo_pan", 0.0)
            tilt_val = state_data.get("servo_tilt", 0.0)
            ear_l = state_data.get("ear_l", 0.0)
            ear_r = state_data.get("ear_r", 0.0)
            stepper_speed = state_data.get("stepper_speed", 0)
            laser = "ON" if state_data.get("laser_on", False) else "OFF"
            buzzer = "Active" if state_data.get("buzzer_active", False) else "Ready"

            bridge_info = (
                f"• Serial Port      : {serial_port} (115200)\n"
                f"• Protocol Schema  : {protocol}\n"
                f"• Pan / Tilt Servos: Pan: {pan:.1f}° | Tilt: {tilt_val:.1f}°\n"
                f"• Ear Servos (L/R) : L: {ear_l:.0f}° | R: {ear_r:.0f}°\n"
                f"• Steppers (L/R)   : PID Speed: {stepper_speed} steps/s\n"
                f"• Lasers / Buzzer  : Laser: {laser} | Buzzer: {buzzer}"
            )

            # Quad 3: Vision pipeline
            cam_driver = cam_data.get("driver", "N/A") if cam_data else "N/A"
            cam_enabled = cam_data.get("enabled", False) if cam_data else False
            proc_mode = cam_data.get("processing_mode", "N/A") if cam_data else "N/A"
            faces = cam_data.get("faces_detected", 0) if cam_data else 0
            vlm_status = "Connected" if cam_data.get("vlm_connected", False) else "Standby"

            vision_info = (
                f"• Device Driver    : {cam_driver}\n"
                f"• Camera Enabled   : {'YES' if cam_enabled else 'NO'}\n"
                f"• Processing Mode  : {proc_mode}\n"
                f"• Active Tracks    : {faces} Human Trackers\n"
                f"• Visual Memory    : Dynamic Frame Buffer\n"
                f"• VLM Multimodal   : {vlm_status}"
            )

            # Quad 4: Voice / AI / Needs
            scores = comp_data.get("scores", {}) if isinstance(comp_data, dict) else {}
            if not isinstance(scores, dict):
                scores = {}
            c_val = float(scores.get("curiosity", 0)) * 100.0
            b_val = float(scores.get("boredom", 0)) * 100.0
            s_val = float(scores.get("social", 0)) * 100.0
            r_val = float(scores.get("rest", 0)) * 100.0
            wakeword = state_data.get("wakeword_engine", "openWakeWord")
            stt = state_data.get("stt_backend", "N/A")
            tts = state_data.get("tts_backend", "N/A")

            ai_info = (
                f"• I2S Mic Array    : Stereo 16kHz PCM (Energy VAD)\n"
                f"• Wakeword Engine  : {wakeword}\n"
                f"• STT / TTS Voice  : {stt} & {tts}\n"
                f"• Living Needs     : Curiosity: {c_val:.0f}% | Boredom: {b_val:.0f}%\n"
                f"• Social / Rest    : Social: {s_val:.0f}% | Rest: {r_val:.0f}%\n"
                f"• Social Memory    : SQLite (data/social.sqlite3)"
            )

            curiosity_pct = c_val if c_val > 0 else 0.0
            tab_telem.update_telemetry_data(
                imu_info=imu_info,
                bridge_info=bridge_info,
                vision_info=vision_info,
                ai_info=ai_info,
                curiosity_val=curiosity_pct,
                ping_val=latency_ms if gateway_online else 0.0,
            )
        except Exception:
            pass

        # ---- HEADER INFO BAR ----
        try:
            bar = self.query_one("#header_info_bar", Label)
            gw_txt = f"GW: OK ({latency_ms:.0f}ms)" if gateway_online else "GW: OFF"
            theme_label = (self.theme or "SENTRY-CRIMSON").upper()
            profile_txt = self.profile.upper().replace("-", " ")
            bar.update(f"{VERSION} | {profile_txt} | THEME: {theme_label} | {gw_txt} | PID: {self.robot_manager.pid or '-'} | Up: {self.robot_manager.uptime_str}")
        except Exception:
            pass

    # Action Handlers
    def action_switch_tab(self, tab_id: str) -> None:
        try:
            tabbed = self.query_one("#app_tabs", TabbedContent)
            tabbed.active = tab_id
        except Exception:
            pass

    def action_theme_select(self) -> None:
        self.push_screen(ThemeSelectorModal())

    def action_sysinfo(self) -> None:
        self.push_screen(SysInfoModal(self.root))

    async def action_restart_robot(self) -> None:
        await self.robot_manager.restart()
        await self.periodic_telemetry_tick()

    async def action_stop_robot(self) -> None:
        await self.robot_manager.stop()
        await self.periodic_telemetry_tick()

    def action_clear_logs(self) -> None:
        try:
            tab_logs = self.query_one("#view_logs", TabLogs)
            tab_logs.clear_logs()
        except Exception:
            pass

    def action_focus_search(self) -> None:
        try:
            self.action_switch_tab("tab_logs")
            inp = self.query_one("#log_search_input")
            inp.focus()
        except Exception:
            pass

    # Button bindings
    async def on_button_pressed(self, event) -> None:
        btn_id = event.button.id
        if btn_id == "btn_start_robot":
            await self.robot_manager.start()
            await self.periodic_telemetry_tick()
        elif btn_id == "btn_stop_robot":
            await self.robot_manager.stop()
            await self.periodic_telemetry_tick()
        elif btn_id == "btn_restart_robot":
            await self.robot_manager.restart()
            await self.periodic_telemetry_tick()
        elif btn_id == "btn_theme":
            self.action_theme_select()
        elif btn_id == "btn_sysinfo":
            self.action_sysinfo()

    def action_quit(self) -> None:
        self.log_streamer.stop()
        if self.robot_manager.is_running:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.robot_manager.stop())
            except Exception:
                pass
        self.exit(0)

    async def on_unmount(self) -> None:
        self.log_streamer.stop()
        if self.robot_manager.is_running:
            await self.robot_manager.stop()


def run_textual_tui(root: Optional[Path] = None, run_robot: bool = True, profile: Optional[str] = None) -> int:
    """Launch the modern SentryBOT Control Center."""
    app = SentryBotApp(root=root, run_robot=run_robot, profile=profile)
    try:
        res = app.run()
        return res if isinstance(res, int) else 0
    except (KeyboardInterrupt, SystemExit):
        return 0
    except Exception:
        return 0

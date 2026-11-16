from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Label, TabbedContent, TabPane

from .services.async_gateway_probe import AsyncGatewayProbe
from .services.async_log_streamer import AsyncLogStreamer, ParsedLogEntry
from .services.async_robot_manager import AsyncRobotManager
from .services.console_constants import APP, VERSION
from .services.console_helpers import is_pc_test
from .services.system_info_collector import get_cpu_info, get_memory_info
from .services.system_info_hardware import get_disk_info
from .themes import THEMES
from .widgets.modal_memory import MemoryExplorerModal
from .widgets.modal_sysinfo import SysInfoModal
from .widgets.modal_theme import ThemeSelectorModal
from .widgets.tab_config import TabConfig
from .widgets.tab_controls import TabControls
from .widgets.tab_logs import TabLogs
from .widgets.tab_main import TabMain, _progress_bar
from .widgets.tab_telemetry import (
    TabTelemetry,
    format_ascii_viewfinder,
    format_doa_radar,
    format_range_radar,
    format_servo_bar,
    format_vu_meter,
)

logger = logging.getLogger("runtime_console.tui_app")

# Log sources to suppress from the UI (noisy HTTP connection internals)
_SUPPRESSED_LOG_SOURCES = (
    "urllib3.connectionpool",
    "httpcore.connection",
    "httpcore.http11",
    "httpx._client",
    "httpx",
    "asyncio",
)


def _opt_float(mapping: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            try:
                return float(mapping[key])
            except (TypeError, ValueError):
                continue
    return None


def _opt_pct(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if 0.0 < f <= 1.0:
        return f * 100.0
    return max(0.0, min(100.0, f))


def _collect_hw_snapshot() -> tuple[tuple[str, str, str, str], tuple[str, str], tuple[str, str]]:
    """Run blocking hardware queries safely in a background thread."""
    return get_cpu_info(), get_memory_info(), get_disk_info()


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
        ("f8", "action_memory", "Memory"),
        ("m", "action_memory", "Memory"),
        ("ctrl+r", "action_restart_robot", "Restart"),
        ("ctrl+k", "action_stop_robot", "Stop"),
        ("ctrl+l", "action_clear_logs", "Clear Logs"),
        ("ctrl+s", "action_export_logs", "Export Logs"),
        ("slash", "action_focus_search", "Search"),
        ("q", "action_quit", "Quit"),
        ("ctrl+c", "action_quit", "Quit"),
    ]

    def __init__(
        self,
        root: Optional[Path] = None,
        run_robot: bool = True,
        profile: Optional[str] = None,
        colors: bool = True,
        ascii_mode: bool = False,
        no_alt: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(ansi_color=bool(colors), **kwargs)
        self.root = (root or Path.cwd()).resolve()
        self.run_robot = run_robot
        self.use_colors = bool(colors)
        self.ascii_mode = bool(ascii_mode)
        self.no_alt = bool(no_alt)
        # Auto-detect: Pi -> "robot", PC -> "pc-test"
        if profile is not None:
            self.profile = profile
        else:
            env_profile = os.environ.get("SENTRYBOT_PROFILE", "").strip().lower()
            if env_profile in {"pc", "pc-test", "robot"}:
                self.profile = "pc-test" if env_profile == "pc" else env_profile
            else:
                self.profile = "pc-test" if is_pc_test(self.root) else "robot"

        # Async Services
        self.robot_manager = AsyncRobotManager(self.root, profile=self.profile)
        self.log_streamer = AsyncLogStreamer(self.root)
        self.gateway_probe = AsyncGatewayProbe()

        # Register all themes
        for _name, theme_obj in THEMES.items():
            try:
                self.register_theme(theme_obj)
            except Exception:
                pass

        from .themes import get_saved_theme_name

        self.theme = get_saved_theme_name()

    def compose(self) -> ComposeResult:
        profile_label = (self.profile or "ROBOT").upper()
        theme_label = (self.theme or "SENTRY-CRIMSON").upper()
        status_badge = f"[ PROFILE: {profile_label} ]" if self.run_robot else f"[ MODE: NO-RUN | {profile_label} ]"
        title_prefix = "*" if self.ascii_mode else "■"

        # High-Tech Header
        with Horizontal(id="app_header"):
            yield Label(f"{title_prefix} {APP} CONTROL CENTER", id="header_title", markup=False)
            yield Label(status_badge, id="header_status_badge", markup=False)
            yield Label(f"{VERSION} | THEME: {theme_label} | Subsystems Active", id="header_info_bar", markup=False)

        # Global System Alert / Emergency HUD
        yield Label("", id="app_alert_banner", classes="alert_hidden", markup=False)

        # 5 High-Utility Dense Tabs
        with TabbedContent(initial="tab_main", id="app_tabs"):
            with TabPane(" 01: MAIN ", id="tab_main"):
                yield TabMain(id="view_main")
            with TabPane(" 02: LOGS ", id="tab_logs"):
                yield TabLogs(root=self.root, id="view_logs")
            with TabPane(" 03: TELEMETRY ", id="tab_telemetry"):
                yield TabTelemetry(id="view_telemetry")
            with TabPane(" 04: CONTROLS ", id="tab_controls"):
                yield TabControls(self.root, gateway_probe=self.gateway_probe, id="view_controls")
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
        gateway_online, hw_snapshot = await asyncio.gather(
            self.gateway_probe.probe_all(),
            asyncio.to_thread(_collect_hw_snapshot),
        )
        latency_ms = self.gateway_probe.last_probe_ms

        (cpu_name, cpu_cores, cpu_freq, cpu_usage_raw), (mem_used, mem_total), (disk_used, disk_total) = hw_snapshot

        # Parse CPU percentage
        try:
            clean_pct = str(cpu_usage_raw).replace("%", "").strip()
            cpu_pct = float(clean_pct) if clean_pct != "?" else 0.0
        except Exception:
            cpu_pct = 0.0

        usage_display = cpu_usage_raw if cpu_usage_raw != "?" else "-%"
        freq_disp = f" @ {cpu_freq}" if cpu_freq and cpu_freq != "?" else ""
        cpu_str = f"{usage_display} [{_progress_bar(cpu_pct, 10, ascii_mode=self.ascii_mode)}] ({cpu_cores}C{freq_disp})"
        mem_str = f"{mem_used} / {mem_total}"
        disk_str = f"{disk_used} / {disk_total}"
        restarts = int(getattr(self.robot_manager, "restart_count", 0))
        proc_str = f"{proc_status} | {self.robot_manager.uptime_str} | R:{restarts} [PID:{self.robot_manager.pid or '-'}]"
        gw_str = f"ONLINE ({latency_ms:.0f}ms)" if gateway_online else "OFFLINE"

        # Calculate RAM usage percentage
        try:
            u_num = float(mem_used.split()[0])
            t_num = float(mem_total.split()[0])
            ram_pct = (u_num / t_num) * 100.0 if t_num > 0 else 0.0
        except Exception:
            ram_pct = 0.0

        # Subsystem data from real gateway payloads
        state_data = self.gateway_probe.state_data or {}
        comp_data = self.gateway_probe.companion_data or {}
        cam_data = self.gateway_probe.camera_data or {}
        exp_data = self.gateway_probe.expression_data or {}
        status_data = self.gateway_probe.status_data or {}
        traces_list = self.gateway_probe.decision_traces or []
        started_modules = set(status_data.get("started", []))
        is_pc = self.profile == "pc-test"

        # Extract real telemetry keys (no fake defaults)
        pan = _opt_float(state_data, "pan", "servo_pan")
        tilt = _opt_float(state_data, "tilt", "servo_tilt")
        ear_l = _opt_float(state_data, "ear_l", "servo_ear_l")
        ear_r = _opt_float(state_data, "ear_r", "servo_ear_r")
        pitch = _opt_float(state_data, "pitch", "imu_pitch")
        roll = _opt_float(state_data, "roll", "imu_roll")
        dist = _opt_float(state_data, "distance_cm", "ultrasonic_cm")
        doa = _opt_float(state_data, "voice_doa", "doa_angle")
        mic_energy = _opt_float(state_data, "mic_energy", "audio_level")
        batt_val = _opt_float(state_data, "battery", "battery_pct")
        temp_val = _opt_float(state_data, "temp_c", "cpu_temp_c")

        raw_faces = cam_data.get("faces_detected")
        if raw_faces is None:
            raw_faces = comp_data.get("people_count")
        if raw_faces is None and isinstance(cam_data.get("onsensor"), dict):
            raw_faces = cam_data["onsensor"].get("people_count")
        faces_cnt: Optional[int] = int(raw_faces) if raw_faces is not None else None

        scores = comp_data.get("scores", {}) if isinstance(comp_data, dict) else {}
        if not isinstance(scores, dict):
            scores = {}
        c_val = _opt_pct(scores.get("curiosity", comp_data.get("curiosity")))
        b_val = _opt_pct(scores.get("boredom", comp_data.get("boredom")))
        s_val = _opt_pct(scores.get("social", comp_data.get("social")))
        r_val = _opt_pct(scores.get("rest", comp_data.get("rest")))
        sf_val = _opt_pct(scores.get("safety", comp_data.get("safety")))

        def _fmt_need(label: str, pct_val: Optional[float], tag: str) -> str:
            if pct_val is None:
                bar = _progress_bar(0.0, 10, ascii_mode=self.ascii_mode)
                return f"• {label:<11}: [{bar}]  N/A  ({tag})"
            bar = _progress_bar(pct_val, 10, ascii_mode=self.ascii_mode)
            return f"• {label:<11}: [{bar}] {pct_val:3.0f}%  ({tag})"

        # ---- TAB 1: MAIN DASHBOARD ----
        safety_brake_val = state_data.get("safety_brake")
        if safety_brake_val is False:
            brake_stat = "Disarmed"
        elif safety_brake_val is True:
            brake_stat = "Armed"
        else:
            brake_stat = "N/A"

        try:
            tab_main = self.query_one("#view_main", TabMain)
            tab_main.update_hero_metrics(
                cpu_str,
                mem_str,
                disk_str,
                proc_str,
                gw_str,
                cpu_val=cpu_pct,
                ram_val=ram_pct,
                gw_latency_ms=latency_ms if gateway_online else 0.0,
            )

            # Update Subsystem Matrix directly from Gateway live status
            failed_modules = set(status_data.get("failed", []))

            if gateway_online and started_modules:
                tab_main.update_service_card("CORE", "OK", f"Gateway active ({len(started_modules)} services mounted)")

                # AI
                if "agent_core" in failed_modules or "ollama" in failed_modules:
                    tab_main.update_service_card("AI", "ERR", "LLM inference failure reported")
                elif "ollama" in started_modules or "agent_core" in started_modules:
                    tab_main.update_service_card("AI", "OK", "LLM reasoning loop ready")
                else:
                    tab_main.update_service_card("AI", "STANDBY", "Rule-based companion autonomy", is_pc_expected=is_pc)

                # VISION
                cam_cap = cam_data.get("capture", {}) if isinstance(cam_data.get("capture"), dict) else {}
                cam_ok = cam_cap.get("running") or cam_data.get("ok")
                faces_txt = f"{faces_cnt} face{'s' if faces_cnt != 1 else ''}" if faces_cnt is not None else "no count"
                if "camera" in failed_modules:
                    tab_main.update_service_card("VISION", "ERR", "Camera pipeline failure", is_pc_expected=is_pc)
                elif cam_ok:
                    tab_main.update_service_card("VISION", "OK", f"Camera active ({faces_txt})")
                elif "camera" in started_modules:
                    tab_main.update_service_card(
                        "VISION",
                        "OK" if not is_pc else "PC-SIM",
                        "Camera module mounted",
                        is_pc_expected=is_pc,
                    )

                # AUDIO
                if "speech" in failed_modules or "wakeword" in failed_modules:
                    tab_main.update_service_card("AUDIO", "WARN", "Audio hardware degraded")
                elif "wakeword" in started_modules or "speech" in started_modules:
                    tab_main.update_service_card("AUDIO", "OK", "Stereo I2S & WakeWord active")
                else:
                    tab_main.update_service_card("AUDIO", "STANDBY", "Microphone pipeline ready", is_pc_expected=is_pc)

                # TTS
                if "speak" in failed_modules:
                    tab_main.update_service_card("TTS", "WARN", "TTS speech synthesizer degraded")
                elif "speak" in started_modules:
                    tab_main.update_service_card("TTS", "OK", "Piper TTS speech synthesis online")
                else:
                    tab_main.update_service_card("TTS", "STANDBY", "TTS voice ready", is_pc_expected=is_pc)

                # MOVE
                pan_lbl = f"{pan:.0f}°" if pan is not None else "N/A"
                ear_lbl = f"{ear_l:.0f}°" if ear_l is not None else "N/A"
                if "arduino" in failed_modules or "piservo" in failed_modules:
                    tab_main.update_service_card("MOVE", "ERR", "Motion bridge disconnected", is_pc_expected=is_pc)
                elif "arduino" in started_modules or "piservo" in started_modules:
                    tab_main.update_service_card("MOVE", "OK", f"Head {pan_lbl} | Ears {ear_lbl}")
                else:
                    tab_main.update_service_card("MOVE", "STANDBY", "Motion arbiter standby", is_pc_expected=is_pc)
            elif not gateway_online:
                if not self.robot_manager.is_running and not self.run_robot:
                    tab_main.update_service_card("CORE", "STANDBY", "Standalone Monitor Mode (--no-run)")
                elif not self.robot_manager.is_running:
                    tab_main.update_service_card("CORE", "STOPPED", "Robot process stopped")
                else:
                    tab_main.update_service_card("CORE", "WAITING", "Connecting to Gateway...")

            # --- Panel 1: Living Needs & Autonomy (real gateway data, N/A when missing) ---
            goal = comp_data.get("recommended_goal") or comp_data.get("active_intent") or comp_data.get("goal") or "N/A"
            dom_need = str(comp_data.get("dominant_need") or "N/A").capitalize()

            if gateway_online or comp_data:
                comp_text = "\n".join(
                    [
                        _fmt_need("Curiosity", c_val, "Drive"),
                        _fmt_need("Boredom", b_val, "Arousal"),
                        _fmt_need("Social", s_val, "Affiliation"),
                        _fmt_need("Rest/Energy", r_val, "Homeostasis"),
                        _fmt_need("Safety", sf_val, "Defense"),
                        f"• Active Goal: {goal} [{dom_need}]",
                    ]
                )
            else:
                empty_bar = _progress_bar(0.0, 10, ascii_mode=self.ascii_mode)
                comp_text = (
                    f"• Curiosity  : [{empty_bar}]  N/A  (Offline)\n"
                    f"• Boredom    : [{empty_bar}]  N/A  (Offline)\n"
                    f"• Social     : [{empty_bar}]  N/A  (Offline)\n"
                    f"• Rest/Energy: [{empty_bar}]  N/A  (Offline)\n"
                    f"• Safety     : [{empty_bar}]  N/A  (Offline)\n"
                    "• Active Goal: Offline"
                )

            # --- Panel 2: Sensors & Hardware Pose (real state data, N/A fallback) ---
            if dist is None:
                dist_badge = "N/A"
            elif dist > 60:
                dist_badge = f"{dist:.0f} cm [CLEAR]"
            elif dist > 25:
                dist_badge = f"{dist:.0f} cm [CAUTION]"
            elif dist > 0:
                dist_badge = f"{dist:.0f} cm [OBSTACLE!]"
            else:
                dist_badge = "0 cm [ECHO]"

            pitch_lbl = f"{pitch:+5.1f}°" if pitch is not None else "N/A"
            roll_lbl = f"{roll:+5.1f}°" if roll is not None else "N/A"
            pan_disp = f"{pan:4.1f}°" if pan is not None else "N/A"
            tilt_disp = f"{tilt:4.1f}°" if tilt is not None else "N/A"
            ear_l_disp = f"{ear_l:3.0f}°" if ear_l is not None else "N/A"
            ear_r_disp = f"{ear_r:3.0f}°" if ear_r is not None else "N/A"
            raw_emotions = state_data.get("emotions")
            fallback_emotion = raw_emotions[0] if isinstance(raw_emotions, list) and raw_emotions else None
            emotion_raw = exp_data.get("emotion") or fallback_emotion
            emotion = str(emotion_raw).capitalize() if emotion_raw else "N/A"
            anim_raw = exp_data.get("current_animation")
            anim = str(anim_raw).replace("_", " ").title() if anim_raw else "N/A"
            laser_stat = "Active" if state_data.get("laser_on") is True else ("Standby" if "laser_on" in state_data else "N/A")

            if gateway_online or state_data:
                attention_text = (
                    f"• IMU Orientation : Pitch: {pitch_lbl} | Roll: {roll_lbl}\n"
                    f"• Obstacle Sensor : {dist_badge}\n"
                    f"• Pan/Tilt Servos : Pan: {pan_disp} | Tilt: {tilt_disp}\n"
                    f"• Ear Servos (L/R): L: {ear_l_disp} | R: {ear_r_disp}\n"
                    f"• OLED / NeoPixel : {emotion} | {anim}\n"
                    f"• Laser / Brake   : Laser: {laser_stat} | Safety Brake: {brake_stat}"
                )
            else:
                attention_text = (
                    "• IMU Orientation : Standby (Gateway connecting)\n"
                    "• Obstacle Sensor : Standby\n"
                    "• Pan/Tilt Servos : Standby\n"
                    "• Ear Servos (L/R): Standby\n"
                    "• OLED / NeoPixel : Standby\n"
                    "• Laser / Brake   : Standby"
                )

            # --- Panel 3: Recognition, Restarts & Gateway Signals ---
            faces_str = (
                f"{faces_cnt} Tracker(s) Active"
                if (faces_cnt is not None and faces_cnt > 0)
                else ("0 (No human in FOV)" if faces_cnt == 0 else "N/A")
            )
            doa_lbl = f"{doa:3.0f}° (I2S Stereo VAD)" if doa is not None else "N/A"
            started_cnt = len(started_modules)
            db_path = self.root / "data" / "social.sqlite3"
            db_stat = "Online (social.sqlite3)" if db_path.exists() else "Ready (New Session)"

            if not self.robot_manager.is_running and not self.run_robot:
                status_line = f"• System Status   : Standalone Monitor Mode (--no-run) | Restarts: {restarts}"
            elif not self.robot_manager.is_running:
                status_line = f"• System Status   : Robot process STOPPED | Restarts: {restarts}"
            elif not gateway_online:
                status_line = f"• System Status   : Connecting to Gateway ({self.gateway_probe.base_url}) | Restarts: {restarts}"
            elif is_pc:
                status_line = f"• Runtime Profile : PC-Test Simulation | Restarts: {restarts}"
            else:
                status_line = f"• Runtime Profile : Production Raspberry Pi 5 | Restarts: {restarts}"

            traffic_text = (
                f"• People / Faces  : {faces_str}\n"
                f"• Voice DoA Angle : {doa_lbl}\n"
                f"• Social Memory   : {db_stat}\n"
                f"• REST Subsystems : {started_cnt} Services Mounted\n"
                f"{status_line}"
            )

            # --- Autonomy Goal & DecisionTrace Live Feed ---
            if traces_list:
                latest = traces_list[-1]
                decision = str(latest.get("decision") or latest.get("action") or "N/A")
                outcome = str(latest.get("outcome") or "N/A")
                tool = str(latest.get("tool") or "-")
                reason = str(latest.get("reason") or "").strip()[:85]
                trace_lines = [
                    f"• Active Goal : {goal} [Need: {dom_need}]",
                    f"• Latest Trace: [{outcome.upper()}] {decision} (tool={tool}) — {reason or 'no reason'}",
                ]
                if len(traces_list) > 1:
                    prev = traces_list[-2]
                    trace_lines.append(
                        f"• Prior Trace : [{str(prev.get('outcome') or '?').upper()}] "
                        f"{prev.get('decision') or 'N/A'} (tool={prev.get('tool') or '-'})"
                    )
                trace_text = "\n".join(trace_lines)
            elif gateway_online:
                trace_text = (
                    f"• Active Goal : {goal} [Need: {dom_need}]\n"
                    "• Latest Trace: Waiting for AgentCore DecisionTrace events..."
                )
            else:
                trace_text = (
                    "• Active Goal : Gateway offline\n"
                    "• Latest Trace: Unavailable while disconnected"
                )

            tab_main.update_telemetry(
                comp_text,
                attention_text,
                traffic_text,
                decision_trace_text=trace_text,
            )
        except Exception:
            pass

        # ---- TAB 3: TELEMETRY DEEP DIVE ----
        try:
            tab_telem = self.query_one("#view_telemetry", TabTelemetry)

            # Quad 1: IMU / Distance / Spatial Pose & Range Radar
            pose = str(state_data.get("current_pose") or "N/A")
            motion = str(state_data.get("motion_state") or "N/A")
            radar_range = format_range_radar(dist or 0.0) if dist is not None else "[N/A / NO READING]"

            imu_info = (
                f"• IMU Pitch / Roll : {pitch_lbl} / {roll_lbl}\n"
                f"• Ultrasonic Range : {dist_badge}\n"
                f"• Obstacle Radar   : {radar_range}\n"
                f"• Current Pose     : '{pose}'\n"
                f"• Motion State     : {motion} | Safety Brake: {brake_stat}"
            )

            # Quad 2: ESP32 bridge / servos & deflection bars
            serial_port = str(state_data.get("serial_port") or "N/A")
            protocol = str(state_data.get("protocol") or "strict_ndjson_contract_v2")
            stepper_speed = state_data.get("stepper_speed")
            stepper_lbl = f"{int(stepper_speed)} steps/s" if stepper_speed is not None else "N/A"
            pan_bar = format_servo_bar(pan) if pan is not None else "[   N/A    ]"
            tilt_bar = format_servo_bar(tilt) if tilt is not None else "[   N/A    ]"

            bridge_info = (
                f"• Serial Device    : {serial_port}\n"
                f"• Protocol Schema  : {protocol}\n"
                f"• Pan / Tilt Servos: Pan: {pan_disp} {pan_bar} | Tilt: {tilt_disp} {tilt_bar}\n"
                f"• Ear Servos (L/R) : L: {ear_l_disp} | R: {ear_r_disp}\n"
                f"• Stepper Motors   : PID Speed: {stepper_lbl}\n"
                f"• Lasers / Buzzer  : Laser: {laser_stat}"
            )

            # Quad 3: Vision pipeline with ASCII Viewfinder
            cam_cap = cam_data.get("capture", {}) if isinstance(cam_data.get("capture"), dict) else {}
            cam_driver = str(cam_data.get("driver") or cam_cap.get("backend") or "N/A")
            cam_enabled = bool(cam_cap.get("running") or cam_data.get("enabled"))
            proc_mode = str(cam_data.get("processing_mode") or "N/A")
            vlm_status = "Online" if ("vlm_bridge" in started_modules) else ("Online (Gateway)" if gateway_online else "Standby")
            ascii_canvas = format_ascii_viewfinder(faces_cnt or 0, driver=cam_driver, has_frame=cam_enabled)

            vision_info = (
                f"• Device Driver    : {cam_driver}\n"
                f"• Camera Stream    : {'RUNNING [LIVE]' if cam_enabled else 'STANDBY'} ({proc_mode})\n"
                f"• Active Tracks    : {faces_cnt if faces_cnt is not None else 'N/A'} Human Target(s)\n"
                "• Viewport Canvas  :\n"
                f"{ascii_canvas}\n"
                f"• VLM Remote Bridge: {vlm_status}"
            )

            # Quad 4: Voice Audio Level (VU-Meter), DoA Radar & Living Needs
            batt_lbl = f"{batt_val:.0f}%" if batt_val is not None else "N/A"
            temp_lbl = f"{temp_val:.0f}°C" if temp_val is not None else "N/A"
            vad_speaking = bool(state_data.get("vad_speaking", False))
            vu_bar = format_vu_meter(mic_energy, vad_active=vad_speaking) if mic_energy is not None else "[N/A         ]   N/A"
            doa_compass = format_doa_radar(doa) if doa is not None else "  DoA Radar: N/A"

            ai_info = (
                f"• I2S Mic Level    : {vu_bar}\n"
                "• Direction of Arrival (DoA Radar):\n"
                f"{doa_compass}\n"
                f"• Living Needs     : Curiosity: {f'{c_val:.0f}%' if c_val is not None else 'N/A'} | "
                f"Boredom: {f'{b_val:.0f}%' if b_val is not None else 'N/A'}\n"
                f"• Homeostasis      : Batt: {batt_lbl} | Core Temp: {temp_lbl}"
            )

            tab_telem.update_telemetry_data(
                imu_info=imu_info,
                bridge_info=bridge_info,
                vision_info=vision_info,
                ai_info=ai_info,
                curiosity_val=c_val or 0.0,
                ping_val=latency_ms if gateway_online else 0.0,
            )
        except Exception:
            pass

        # ---- GLOBAL ALERT BANNER CHECK ----
        try:
            banner = self.query_one("#app_alert_banner", Label)
            is_estop = state_data.get("operational") == "estop" or safety_brake_val is False
            if is_estop:
                banner.update("🛑 [EMERGENCY STOP ACTIVE] HARDWARE INTERLOCK ENGAGED — MOTOR CHANNELS HALTED")
                banner.remove_class("alert_hidden")
                banner.add_class("alert_visible")
            else:
                banner.update("")
                banner.remove_class("alert_visible")
                banner.add_class("alert_hidden")
        except Exception:
            pass

        # ---- HEADER INFO BAR ----
        try:
            bar = self.query_one("#header_info_bar", Label)
            gw_txt = f"GW: OK ({latency_ms:.0f}ms)" if gateway_online else "GW: OFF"
            theme_label = (self.theme or "SENTRY-CRIMSON").upper()
            profile_txt = self.profile.upper().replace("-", " ")
            bar.update(
                f"{VERSION} | {profile_txt} | THEME: {theme_label} | {gw_txt} | "
                f"PID: {self.robot_manager.pid or '-'} | Up: {self.robot_manager.uptime_str} | R:{restarts}"
            )
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

    def action_memory(self) -> None:
        self.push_screen(MemoryExplorerModal(self.root))

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

    def action_export_logs(self) -> None:
        try:
            tab_logs = self.query_one("#view_logs", TabLogs)
            tab_logs.action_export_logs()
        except Exception:
            pass

    def action_focus_search(self) -> None:
        try:
            self.action_switch_tab("tab_logs")
            inp = self.query_one("#log_search_input")
            inp.focus()
        except Exception:
            pass

    def _update_header_badge(self) -> None:
        try:
            badge = self.query_one("#header_status_badge", Label)
            profile_label = (self.profile or "ROBOT").upper()
            status_badge = f"[ PROFILE: {profile_label} ]" if self.run_robot else f"[ MODE: NO-RUN | {profile_label} ]"
            badge.update(status_badge)
        except Exception:
            pass

    # Button bindings
    async def on_button_pressed(self, event) -> None:
        btn_id = event.button.id
        if btn_id == "btn_start_robot":
            self.run_robot = True
            self._update_header_badge()
            await self.robot_manager.start()
            await self.periodic_telemetry_tick()
        elif btn_id == "btn_stop_robot":
            await self.robot_manager.stop()
            await self.periodic_telemetry_tick()
        elif btn_id == "btn_restart_robot":
            self.run_robot = True
            self._update_header_badge()
            await self.robot_manager.restart()
            await self.periodic_telemetry_tick()
        elif btn_id == "btn_theme":
            self.action_theme_select()
        elif btn_id == "btn_sysinfo":
            self.action_sysinfo()

    def action_quit(self) -> None:
        self.log_streamer.stop()
        self.exit(0)

    async def on_unmount(self) -> None:
        self.log_streamer.stop()
        try:
            tab_controls = self.query_one("#view_controls", TabControls)
            await tab_controls.aclose()
        except Exception:
            pass
        try:
            await self.gateway_probe.aclose()
        except Exception:
            pass
        if self.robot_manager.is_running:
            await self.robot_manager.stop()


def run_textual_tui(
    root: Optional[Path] = None,
    run_robot: bool = True,
    profile: Optional[str] = None,
    colors: bool = True,
    ascii_mode: bool = False,
    no_alt: bool = False,
) -> int:
    """Launch the modern SentryBOT Control Center."""
    app = SentryBotApp(
        root=root,
        run_robot=run_robot,
        profile=profile,
        colors=colors,
        ascii_mode=ascii_mode,
        no_alt=no_alt,
    )
    try:
        res = app.run(inline=no_alt)
        return res if isinstance(res, int) else 0
    except (KeyboardInterrupt, SystemExit):
        return 0
    except Exception:
        logger.exception("TUI application crashed during startup or execution")
        return 1

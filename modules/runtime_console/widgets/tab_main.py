from __future__ import annotations

from typing import Any, Dict, List, Optional
from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Label, Sparkline, Static


def _progress_bar(pct: float, width: int = 10) -> str:
    """ASCII resource meter bar."""
    pct = max(0.0, min(100.0, pct))
    filled = int(round((pct / 100.0) * width))
    return "█" * filled + "░" * (width - filled)


class ServiceCard(Widget):
    """Dense card displaying single subsystem status in the matrix."""

    def __init__(self, service_name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.service_name = service_name
        self.status = "IDLE"
        self.message = "Awaiting telemetry..."
        self.is_pc_expected = False

    def compose(self) -> ComposeResult:
        with Horizontal(classes="service_card_header"):
            yield Label(f"■ {self.service_name}", id=f"svc_name_{self.service_name}", classes="service_name", markup=False)
            yield Label(f" {self.status} ", id=f"svc_badge_{self.service_name}", classes="service_badge", markup=False)
        yield Label(self.message, id=f"svc_msg_{self.service_name}", classes="service_msg", markup=False)

    def update_status(self, status: str, message: str, is_pc_expected: bool = False) -> None:
        self.status = status
        self.message = message
        self.is_pc_expected = is_pc_expected
        
        try:
            badge = self.query_one(f"#svc_badge_{self.service_name}", Label)
            msg = self.query_one(f"#svc_msg_{self.service_name}", Label)
            
            display_status = "PC-SIM" if is_pc_expected and status in ("WARN", "ERR", "OFFLINE") else status
            badge.update(f" {display_status} ")
            msg.update(message[:65])
            
            badge.remove_class("badge_ok", "badge_warn", "badge_err", "badge_pc")
            if display_status == "OK":
                badge.add_class("badge_ok")
            elif display_status in ("WARN", "DEGRADED"):
                badge.add_class("badge_warn")
            elif display_status in ("ERR", "ERROR", "FAIL"):
                badge.add_class("badge_err")
            elif "PC" in display_status:
                badge.add_class("badge_pc")
        except Exception:
            pass


class TabMain(Widget):
    """High-Density Main Control Center Dashboard with Real SentryBOT Hardware & Autonomy Telemetry."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.cpu_history: List[float] = [10.0] * 30
        self.ram_history: List[float] = [20.0] * 30
        self.gw_history: List[float] = [1.0] * 30

    def compose(self) -> ComposeResult:
        with Vertical(id="main_container"):
            # Top Resource Gauge Strip (5 Real System Metrics)
            with Horizontal(id="main_hero_bar"):
                with Vertical(classes="hero_metric"):
                    yield Label("CPU LOAD", classes="hero_label", markup=False)
                    yield Label("0% [░░░░░░░░░░] (0C)", id="metric_cpu", classes="hero_value", markup=False)
                with Vertical(classes="hero_metric"):
                    yield Label("MEMORY RAM", classes="hero_label", markup=False)
                    yield Label("0.0 / 0.0 GiB (0%)", id="metric_ram", classes="hero_value", markup=False)
                with Vertical(classes="hero_metric"):
                    yield Label("DISK STORAGE", classes="hero_label", markup=False)
                    yield Label("0 / 0 GiB (0%)", id="metric_disk", classes="hero_value", markup=False)
                with Vertical(classes="hero_metric"):
                    yield Label("PROCESS / UPTIME", classes="hero_label", markup=False)
                    yield Label("IDLE | 00:00:00", id="metric_process", classes="hero_value", markup=False)
                with Vertical(classes="hero_metric_last"):
                    yield Label("GATEWAY / IP", classes="hero_label", markup=False)
                    yield Label("OFFLINE", id="metric_gateway", classes="hero_value", markup=False)

            # Live Dynamic Historical Resource Waveforms (Sparklines)
            with Horizontal(id="main_sparkline_strip"):
                with Vertical(classes="sparkline_box"):
                    yield Label("CPU LOAD HISTORY (30s)", classes="sparkline_title", markup=False)
                    yield Sparkline(self.cpu_history, id="spark_cpu", summary_function=max)
                with Vertical(classes="sparkline_box"):
                    yield Label("RAM ALLOCATION HISTORY (30s)", classes="sparkline_title", markup=False)
                    yield Sparkline(self.ram_history, id="spark_ram", summary_function=max)
                with Vertical(classes="sparkline_box_last"):
                    yield Label("GATEWAY LATENCY (ms)", classes="sparkline_title", markup=False)
                    yield Sparkline(self.gw_history, id="spark_gw", summary_function=max)

            # Subsystem Health Matrix (6 Real Modules)
            yield Label("SUBSYSTEM HEALTH MATRIX", id="services_grid_title", markup=False)
            with Grid(id="services_grid"):
                yield ServiceCard("CORE", id="card_core", classes="service_card")
                yield ServiceCard("AI", id="card_ai", classes="service_card")
                yield ServiceCard("VISION", id="card_vision", classes="service_card")
                yield ServiceCard("AUDIO", id="card_audio", classes="service_card")
                yield ServiceCard("TTS", id="card_tts", classes="service_card")
                yield ServiceCard("MOVE", id="card_move", classes="service_card")

            # 3-Way Split: Real Living Needs + Sensors/Actuators + Alerts
            with Horizontal(id="main_middle_split"):
                # Panel 1: Real Living Needs Model
                with Vertical(id="companion_panel"):
                    yield Label("LIVING NEEDS & AUTONOMY", classes="panel_title", markup=False)
                    yield Static(
                        "• Curiosity  : [████████░░] 80%\n"
                        "• Boredom    : [██░░░░░░░░] 20%\n"
                        "• Social     : [████░░░░░░] 40%\n"
                        "• Rest       : [█░░░░░░░░░] 10%\n"
                        "• Safety     : [█████████░] 95%\n"
                        "• Goal       : observe_environment",
                        id="companion_content",
                    )

                # Panel 2: Real Actuators & Sensors
                with Vertical(id="attention_panel"):
                    yield Label("SENSORS & HARDWARE POSE", classes="panel_title", markup=False)
                    yield Static(
                        "• IMU Orientation : Pitch: 0.0° | Roll: 0.0°\n"
                        "• Distance Sensor : 120 cm (Clear Path)\n"
                        "• Servos (Pan/Tilt): P: 0.0° | T: 0.0°\n"
                        "• Ears (L/R)      : L: 90° | R: 90°\n"
                        "• OLED / NeoPixel : Happy Eyes | Idle Breathe\n"
                        "• Lasers / Buzzer : Inactive / Ready",
                        id="attention_content",
                    )

                # Panel 3: Recognition & Signal Traffic
                with Vertical(id="traffic_panel"):
                    yield Label("RECOGNITION & GATEWAY SIGNALS", classes="panel_title", markup=False)
                    yield Static(
                        "• People Detected : 0 (No active tracks)\n"
                        "• DoA Voice Angle : 0° (I2S Stereo VAD)\n"
                        "• Social Memory   : SQLite Database Ready\n"
                        "• REST Endpoints  : 14 Routers Mounted\n"
                        "• Protocol Schema : strict_json_contract_v2",
                        id="traffic_content",
                    )

            # Bottom Action Bar
            with Horizontal(id="main_action_bar"):
                yield Button("Start Robot", id="btn_start_robot", variant="success", classes="action_button")
                yield Button("Stop Robot", id="btn_stop_robot", variant="error", classes="action_button")
                yield Button("Restart", id="btn_restart_robot", variant="warning", classes="action_button")
                yield Button("Theme (F6)", id="btn_theme", variant="default", classes="action_button")
                yield Button("SysSpecs (F7)", id="btn_sysinfo", variant="default", classes="action_button")

    def update_hero_metrics(
        self,
        cpu_text: str,
        ram_text: str,
        disk_text: str,
        proc_text: str,
        gw_text: str,
        cpu_val: Optional[float] = None,
        ram_val: Optional[float] = None,
        gw_latency_ms: Optional[float] = None,
    ) -> None:
        try:
            self.query_one("#metric_cpu", Label).update(cpu_text)
            self.query_one("#metric_ram", Label).update(ram_text)
            self.query_one("#metric_disk", Label).update(disk_text)
            self.query_one("#metric_process", Label).update(proc_text)
            self.query_one("#metric_gateway", Label).update(gw_text)

            # Update sparklines if values provided
            if cpu_val is not None:
                self.cpu_history.append(float(cpu_val))
                self.cpu_history = self.cpu_history[-30:]
                self.query_one("#spark_cpu", Sparkline).data = self.cpu_history

            if ram_val is not None:
                self.ram_history.append(float(ram_val))
                self.ram_history = self.ram_history[-30:]
                self.query_one("#spark_ram", Sparkline).data = self.ram_history

            if gw_latency_ms is not None:
                self.gw_history.append(float(gw_latency_ms))
                self.gw_history = self.gw_history[-30:]
                self.query_one("#spark_gw", Sparkline).data = self.gw_history
        except Exception:
            pass

    def update_telemetry(self, companion_text: str, attention_text: str, traffic_text: str = "") -> None:
        try:
            if companion_text:
                self.query_one("#companion_content", Static).update(companion_text)
            if attention_text:
                self.query_one("#attention_content", Static).update(attention_text)
            if traffic_text:
                self.query_one("#traffic_content", Static).update(traffic_text)
        except Exception:
            pass

    def update_service_card(self, service: str, status: str, message: str, is_pc_expected: bool = False) -> None:
        try:
            card = self.query_one(f"#card_{service.lower()}", ServiceCard)
            card.update_status(status, message, is_pc_expected)
        except Exception:
            pass

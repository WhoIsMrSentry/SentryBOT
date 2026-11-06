from __future__ import annotations

from typing import Any, List, Optional
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Label, Sparkline, Static


def format_servo_bar(deg: float, min_deg: float = 0.0, max_deg: float = 180.0, width: int = 10) -> str:
    """ASCII bar showing servo deflection from neutral."""
    deg_clamped = max(min_deg, min(max_deg, float(deg)))
    ratio = (deg_clamped - min_deg) / (max_deg - min_deg) if max_deg > min_deg else 0.5
    pos = int(round(ratio * (width - 1)))
    chars = ["─"] * width
    chars[pos] = "█"
    return f"[{''.join(chars)}]"


def format_vu_meter(level_pct: float, width: int = 12, vad_active: bool = False) -> str:
    """ASCII Audio VU-Meter showing input loudness & VAD speech flag."""
    clamped = max(0.0, min(100.0, float(level_pct)))
    filled = int(round((clamped / 100.0) * width))
    bar = "█" * filled + "░" * (width - filled)
    vad_tag = "[VAD: VOICE]" if vad_active else "[VAD: SILENCE]"
    db_est = -60.0 + (clamped / 100.0) * 60.0
    return f"[{bar}] {db_est:4.0f} dBFS {vad_tag}"


def format_doa_radar(angle_deg: float) -> str:
    """Direction of Arrival 180-degree radar compass pointing to audio origin."""
    angle = max(0.0, min(180.0, float(angle_deg)))
    # Map 0..180 onto 20 characters
    pos = int(round((angle / 180.0) * 19))
    arrow_line = [" "] * 20
    arrow_line[pos] = "▲"
    arrow_str = "".join(arrow_line)
    return (
        f"  0° ── 45° ── 90° ── 135° ── 180° ({angle:.0f}°)\n"
        f"  {arrow_str}"
    )


def format_range_radar(dist_cm: float, width: int = 14) -> str:
    """Visual obstacle range meter bar."""
    if dist_cm <= 0:
        return "[STANDBY / ECHO]"
    if dist_cm > 200:
        return "[██████████████] >200cm [CLEAR]"
    clamped = max(0.0, min(200.0, dist_cm))
    filled = int(round((clamped / 200.0) * width))
    bar = "█" * filled + "░" * (width - filled)
    stat = "OBSTACLE!" if dist_cm < 25 else ("CAUTION" if dist_cm < 60 else "CLEAR")
    return f"[{bar}] {dist_cm:.0f}cm [{stat}]"


def format_ascii_viewfinder(faces: int, driver: str = "PiCamera2", has_frame: bool = True) -> str:
    """ASCII viewfinder canvas simulating camera FOV with active object/human trackers."""
    if not has_frame:
        return (
            "  ┌───────────────── VIEWPORT ─────────────────┐\n"
            "  │                                            │\n"
            "  │          [ CAMERA STREAM STANDBY ]         │\n"
            "  │          Sensor waiting for frame...       │\n"
            "  │                                            │\n"
            "  └────────────────────────────────────────────┘"
        )
    if faces > 0:
        count_str = f"PERSON ({faces} TRACKED)"
        return (
            "  ┌───────────────── VIEWPORT ─────────────────┐\n"
            f"  │  [{count_str:<22}]              │\n"
            "  │       (o o)                                │\n"
            "  │       / | \\              [TARGET LOCK]     │\n"
            "  │        / \\                    [OK]         │\n"
            "  └────────────────────────────────────────────┘"
        )
    return (
        "  ┌───────────────── VIEWPORT ─────────────────┐\n"
        "  │                                            │\n"
        "  │             [ NO TARGET IN FOV ]           │\n"
        "  │             Tracking mode: PATROL          │\n"
        "  │                                            │\n"
        "  └────────────────────────────────────────────┘"
    )


class TabTelemetry(Widget):
    """Deep SentryBOT Subsystem, Hardware Sensors, Actuators & Contract Telemetry Tab."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.curiosity_history: List[float] = [0.0] * 30
        self.ping_history: List[float] = [0.0] * 30

    def compose(self) -> ComposeResult:
        with Vertical(id="telemetry_container"):
            # Header title
            yield Label("SENTRYBOT HARDWARE SENSORS & CONTRACT TELEMETRY", id="telemetry_title", markup=False)

            # Top Live Real Waveform Strip (Curiosity Drive & Serial Ping Latency)
            with Horizontal(id="telemetry_spark_strip"):
                with Vertical(classes="telem_spark_box"):
                    yield Label("AUTONOMY CURIOSITY DRIVE LEVEL (%)", classes="telem_spark_title", markup=False)
                    yield Sparkline(self.curiosity_history, id="spark_curiosity", summary_function=max)
                with Vertical(classes="telem_spark_box_last"):
                    yield Label("GATEWAY PROBE LATENCY (ms)", classes="telem_spark_title", markup=False)
                    yield Sparkline(self.ping_history, id="spark_ping", summary_function=max)

            # 4 Quadrant Grid for Deep Real System Diagnostic Telemetry
            with Grid(id="telemetry_grid"):
                # Quad 1: IMU, Distance & Spatial Orientation
                with Vertical(classes="telemetry_card"):
                    yield Label("■ IMU, DISTANCE & SPATIAL POSE", classes="telemetry_card_title", markup=False)
                    yield Static(
                        "• IMU Pitch / Roll : Pitch:  +0.0° / Roll:  +0.0° (Standby)\n"
                        "• Ultrasonic Range : Path Clear (Echo OK)\n"
                        "• Current Pose     : 'Normal Standby'\n"
                        "• DoA Voice Angle  : 0° (I2S Stereo GCC-PHAT)\n"
                        "• Motion State     : Stationary\n"
                        "• Safety Brake     : Armed",
                        id="telem_imu_content",
                    )

                # Quad 2: ESP32 Motor & 4-Servo Contract
                with Vertical(classes="telemetry_card"):
                    yield Label("■ ARDUINO MEGA & 4-SERVO CONTRACT", classes="telemetry_card_title", markup=False)
                    yield Static(
                        "• Serial Device    : /dev/ttyUSB0 (115200 baud)\n"
                        "• Protocol Schema  : strict_ndjson_contract_v2\n"
                        "• Pan / Tilt Servos: Pan: 90.0° | Tilt: 90.0° (Arduino Mega)\n"
                        "• Ear Servos (L/R) : L:  90° | R:  90° (Pi GPIO 12/13)\n"
                        "• Stepper Motors   : PID Speed: 0 steps/s\n"
                        "• Lasers / Buzzer  : Laser: Standby | Buzzer: Ready",
                        id="telem_bridge_content",
                    )

                # Quad 3: Camera, IMX500 & Face Recognition Viewport
                with Vertical(classes="telemetry_card"):
                    yield Label("■ VISION & IMX500 SENSOR PIPELINE", classes="telemetry_card_title", markup=False)
                    yield Static(
                        "• Device Driver    : PiCamera2 / IMX500\n"
                        "• Camera Stream    : RUNNING (15 FPS)\n"
                        "• Viewport Canvas  :\n"
                        + format_ascii_viewfinder(0, has_frame=True)
                        + "\n• Processing Mode  : Hybrid Edge / Remote VLM",
                        id="telem_vision_content",
                    )

                # Quad 4: Voice Audio & Living Needs
                with Vertical(classes="telemetry_card"):
                    yield Label("■ VOICE I2S, AUDITORY RADAR & LIVING NEEDS", classes="telemetry_card_title", markup=False)
                    yield Static(
                        "• I2S Mic Level    : " + format_vu_meter(0.0) + "\n"
                        "• Voice DoA Radar  :\n"
                        + format_doa_radar(90.0) + "\n"
                        "• Wakeword Engine  : openWakeWord (\"hey sentry\")\n"
                        "• STT / TTS Voice  : Google Multi-Lingual & Piper Neural\n"
                        "• Living Needs     : Curiosity: 65% | Boredom: 20%",
                        id="telem_ai_content",
                    )

    def update_telemetry_data(
        self,
        imu_info: str = "",
        bridge_info: str = "",
        vision_info: str = "",
        ai_info: str = "",
        curiosity_val: Optional[float] = None,
        ping_val: Optional[float] = None,
    ) -> None:
        # Always update internal sparkline history buffers
        if curiosity_val is not None:
            self.curiosity_history.append(float(curiosity_val))
            self.curiosity_history = self.curiosity_history[-30:]

        if ping_val is not None:
            self.ping_history.append(float(ping_val))
            self.ping_history = self.ping_history[-30:]

        # Update DOM widgets if mounted
        try:
            if imu_info:
                self.query_one("#telem_imu_content", Static).update(imu_info)
            if bridge_info:
                self.query_one("#telem_bridge_content", Static).update(bridge_info)
            if vision_info:
                self.query_one("#telem_vision_content", Static).update(vision_info)
            if ai_info:
                self.query_one("#telem_ai_content", Static).update(ai_info)

            if curiosity_val is not None:
                self.query_one("#spark_curiosity", Sparkline).data = self.curiosity_history
            if ping_val is not None:
                self.query_one("#spark_ping", Sparkline).data = self.ping_history
        except Exception:
            pass

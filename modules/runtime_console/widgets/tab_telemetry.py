from __future__ import annotations

from typing import Any, Dict, List, Optional
from textual.app import ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Label, Sparkline, Static


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
                        "• IMU Pitch / Roll : Waiting for data...\n"
                        "• Ultrasonic Range : Waiting for data...\n"
                        "• Current Pose     : Waiting for data...\n"
                        "• DoA Voice Angle  : Waiting for data...\n"
                        "• Motion State     : Waiting for data...\n"
                        "• Safety Brake     : Waiting for data...",
                        id="telem_imu_content",
                    )

                # Quad 2: ESP32 Motor & 4-Servo Contract
                with Vertical(classes="telemetry_card"):
                    yield Label("■ ESP32 MOTOR & 4-SERVO CONTRACT", classes="telemetry_card_title", markup=False)
                    yield Static(
                        "• Serial Port      : Waiting for data...\n"
                        "• Protocol Schema  : Waiting for data...\n"
                        "• Pan / Tilt Servos: Waiting for data...\n"
                        "• Ear Servos (L/R) : Waiting for data...\n"
                        "• Steppers (L/R)   : Waiting for data...\n"
                        "• Lasers / Buzzer  : Waiting for data...",
                        id="telem_bridge_content",
                    )

                # Quad 3: Camera, IMX500 & Face Recognition
                with Vertical(classes="telemetry_card"):
                    yield Label("■ VISION & IMX500 SENSOR PIPELINE", classes="telemetry_card_title", markup=False)
                    yield Static(
                        "• Device Driver    : Waiting for data...\n"
                        "• Camera Enabled   : Waiting for data...\n"
                        "• Processing Mode  : Waiting for data...\n"
                        "• Active Tracks    : Waiting for data...\n"
                        "• Visual Memory    : Waiting for data...\n"
                        "• VLM Multimodal   : Waiting for data...",
                        id="telem_vision_content",
                    )

                # Quad 4: Voice Audio & Living Needs
                with Vertical(classes="telemetry_card"):
                    yield Label("■ VOICE I2S & LIVING NEEDS MODEL", classes="telemetry_card_title", markup=False)
                    yield Static(
                        "• I2S Mic Array    : Waiting for data...\n"
                        "• Wakeword Engine  : Waiting for data...\n"
                        "• STT / TTS Voice  : Waiting for data...\n"
                        "• Living Needs     : Waiting for data...\n"
                        "• Social / Rest    : Waiting for data...\n"
                        "• Social Memory    : Waiting for data...",
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
                self.curiosity_history.append(float(curiosity_val))
                self.curiosity_history = self.curiosity_history[-30:]
                self.query_one("#spark_curiosity", Sparkline).data = self.curiosity_history

            if ping_val is not None:
                self.ping_history.append(float(ping_val))
                self.ping_history = self.ping_history[-30:]
                self.query_one("#spark_ping", Sparkline).data = self.ping_history
        except Exception:
            pass

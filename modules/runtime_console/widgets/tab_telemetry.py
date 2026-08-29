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
        self.curiosity_history: List[float] = [80.0, 75.0, 80.0, 85.0, 80.0, 82.0] * 5
        self.ping_history: List[float] = [1.2, 1.0, 1.5, 1.1, 1.2, 1.3] * 5

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
                    yield Label("ESP32 MOTOR BRIDGE LATENCY (ms)", classes="telem_spark_title", markup=False)
                    yield Sparkline(self.ping_history, id="spark_ping", summary_function=max)

            # 4 Quadrant Grid for Deep Real System Diagnostic Telemetry
            with Grid(id="telemetry_grid"):
                # Quad 1: IMU, Distance & Spatial Orientation
                with Vertical(classes="telemetry_card"):
                    yield Label("■ IMU, DISTANCE & SPATIAL POSE", classes="telemetry_card_title", markup=False)
                    yield Static(
                        "• IMU Pitch / Roll : 0.0° / 0.0° (Level)\n"
                        "• Ultrasonic Range : 120 cm (Clear Corridor)\n"
                        "• Current Pose     : 'stand' / upright\n"
                        "• DoA Voice Angle  : 0° (I2S Stereo VAD)\n"
                        "• Motion State     : Neutral Stationary\n"
                        "• Safety Brake     : Armed (Auto-avoid: ON)",
                        id="telem_imu_content",
                    )

                # Quad 2: ESP32 Motor & 4-Servo Contract
                with Vertical(classes="telemetry_card"):
                    yield Label("■ ESP32 MOTOR & 4-SERVO CONTRACT", classes="telemetry_card_title", markup=False)
                    yield Static(
                        "• Serial Port      : COM3 / /dev/ttyUSB0 (115200)\n"
                        "• Protocol Schema  : strict_json_contract_v2\n"
                        "• Pan / Tilt Servos: Pan: 0.0° | Tilt: 0.0°\n"
                        "• Ear Servos (L/R) : L: 90.0° | R: 90.0°\n"
                        "• Steppers (L/R)   : PID Speed: 0 steps/s\n"
                        "• Lasers / Buzzer  : Laser: OFF | Buzzer: Ready",
                        id="telem_bridge_content",
                    )

                # Quad 3: Camera, IMX500 & Face Recognition
                with Vertical(classes="telemetry_card"):
                    yield Label("■ VISION & IMX500 SENSOR PIPELINE", classes="telemetry_card_title", markup=False)
                    yield Static(
                        "• Device Driver    : PiCamera2 / IMX500 / OpenCV\n"
                        "• Processing Mode  : local (Haar & DNN Detector)\n"
                        "• Face Embeddings  : 128D/512D Vector Matcher\n"
                        "• Active Tracks    : 0 Human Trackers\n"
                        "• Visual Memory    : Dynamic Frame Buffer\n"
                        "• VLM Multimodal   : Standby / Connected",
                        id="telem_vision_content",
                    )

                # Quad 4: Voice Audio & Living Needs
                with Vertical(classes="telemetry_card"):
                    yield Label("■ VOICE I2S & LIVING NEEDS MODEL", classes="telemetry_card_title", markup=False)
                    yield Static(
                        "• I2S Mic Array    : Stereo 16kHz PCM (Energy VAD)\n"
                        "• Wakeword Engine  : openWakeWord ('hey sentry')\n"
                        "• STT / TTS Voice  : Vosk/Whisper & Piper TR-dfki\n"
                        "• Living Needs     : Curiosity: 80% | Boredom: 20%\n"
                        "• Social / Rest    : Social: 40% | Rest: 10%\n"
                        "• Social Memory    : SQLite (data/social.sqlite3)",
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

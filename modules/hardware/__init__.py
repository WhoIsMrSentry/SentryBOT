# Hardware Abstraction Layer (HAL)
# All services accept a ServiceClient and delegate to existing microservices via HTTP.
from .services.servo_service import ServoService
from .services.lights_service import LightsService
from .services.motor_service import MotorService
from .services.audio_service import AudioService

__all__ = ["ServoService", "LightsService", "MotorService", "AudioService"]

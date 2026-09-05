"""Camera Device Manager for SentryBOT.

Provides centralized management of PiCamera2/IMX500 device access:
- Device lock with reference counting
- Mode switching (local/remote/onsensor/hybrid)
- Exclusive access enforcement
- Resource cleanup and recovery
"""

from __future__ import annotations

import logging
import threading
import time
import weakref
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("camera.device_manager")


try:
    from .devices.device_lock import CameraMode, CameraConfig, DeviceState, DeviceRef, DeviceHandle
except Exception:
    from modules.camera.devices.device_lock import CameraMode, CameraConfig, DeviceState, DeviceRef, DeviceHandle  # type: ignore


class CameraDeviceManager:
    """Singleton camera device manager with reference counting and mode management.
    
    Features:
    - Single physical device, multiple logical consumers
    - Reference counting for shared access
    - Mode switching with proper transitions
    - Exclusive access for streaming
    - Automatic recovery on errors
    - Weak reference tracking for leak detection
    """
    
    _instance: Optional["CameraDeviceManager"] = None
    # RLock (not Lock): get_instance() holds this lock while constructing
    # CameraDeviceManager(), whose __new__ re-acquires it on the SAME thread.
    # A plain Lock deadlocks here on first call (R61).
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._config = CameraConfig()
        self._state = DeviceState.CLOSED
        self._picam2 = None
        self._imx500_runner = None
        
        # Reference tracking
        self._refs: Dict[str, DeviceRef] = {}
        self._weak_refs: Set[weakref.ref] = set()
        
        # Locks
        self._state_lock = threading.RLock()
        self._refs_lock = threading.RLock()
        self._picam2_lock = threading.RLock()
        
        # State
        self._current_mode = CameraMode.LOCAL
        self._streaming = False
        self._last_error: Optional[Exception] = None
        self._recovery_attempts = 0
        self._max_recovery_attempts = 3
        
        # Callbacks
        self._mode_change_callbacks: List[Callable[[CameraMode, CameraMode], None]] = []
        self._error_callbacks: List[Callable[[Exception], None]] = []
        
        # Streaming
        self._frame_publisher = None
        self._stream_thread: Optional[threading.Thread] = None
        self._stop_stream = threading.Event()
        
        # Metrics
        self._open_count = 0
        self._close_count = 0
        self._mode_changes = 0
        self._errors = 0
        
        self._initialized = True
        logger.info("CameraDeviceManager initialized")
    
    @classmethod
    def get_instance(cls) -> "CameraDeviceManager":
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = CameraDeviceManager()
        return cls._instance
    
    # =========================================================================
    # Configuration
    # =========================================================================
    
    def configure(self, config: CameraConfig) -> None:
        """Update camera configuration."""
        with self._state_lock:
            old_mode = self._config.mode
            self._config = config
            
            if old_mode != config.mode:
                logger.info("Camera config updated: mode %s -> %s", old_mode.value, config.mode.value)
    
    def get_config(self) -> CameraConfig:
        """Get current configuration."""
        return self._config
    
    # =========================================================================
    # Reference Management
    # =========================================================================
    
    def acquire(self, owner: str, mode: Optional[CameraMode] = None) -> "DeviceHandle":
        """Acquire a reference to the camera device.
        
        Args:
            owner: Identifier of the consumer (e.g., "vlm_bridge", "camera_capture")
            mode: Desired mode (defaults to current config mode)
            
        Returns:
            DeviceHandle for the acquired reference
            
        Raises:
            RuntimeError: If device cannot be acquired
        """
        with self._refs_lock:
            mode = mode or self._config.mode
            
            if owner in self._refs:
                ref = self._refs[owner]
                if ref.mode != mode:
                    raise RuntimeError(
                        f"Owner {owner} already has device in mode {ref.mode.value}, "
                        f"cannot switch to {mode.value} without releasing first"
                    )
                ref.ref_count += 1
                logger.debug("Owner %s acquired additional reference (count=%d)", owner, ref.ref_count)
            else:
                # First reference - need to open device if not open
                if self._state == DeviceState.CLOSED:
                    self._open_device(mode)
                elif mode != self._current_mode:
                    self._switch_mode(mode)
                
                ref = DeviceRef(owner=owner, mode=mode, opened_at=time.time())
                self._refs[owner] = ref
                logger.info("Owner %s acquired device reference (mode=%s)", owner, mode.value)
            
            return DeviceHandle(self, owner)
    
    def release(self, owner: str) -> bool:
        """Release a reference to the camera device.
        
        Args:
            owner: Identifier of the consumer
            
        Returns:
            True if reference was released, False if not found
        """
        with self._refs_lock:
            if owner not in self._refs:
                logger.warning("Owner %s tried to release non-existent reference", owner)
                return False
            
            ref = self._refs[owner]
            ref.ref_count -= 1
            
            if ref.ref_count <= 0:
                del self._refs[owner]
                logger.info("Owner %s released device reference", owner)
                
                # If no more references, close device
                if not self._refs:
                    self._close_device()
            
            return True
    
    def get_references(self) -> Dict[str, DeviceRef]:
        """Get current references (copy)."""
        with self._refs_lock:
            return dict(self._refs)
    
    def has_reference(self, owner: str) -> bool:
        """Check if owner has a reference."""
        with self._refs_lock:
            return owner in self._refs
    
    # =========================================================================
    # Device Operations
    # =========================================================================
    
    def _open_device(self, mode: CameraMode) -> None:
        """Register device ownership without opening hardware (R12).

        libcamera allows a single owner; the physical open belongs to the one
        acquisition point (CameraCapture's in-process instance or its bridge
        subprocess). This manager only arbitrates references and mode, so a
        competing second Picamera2 is never created here.
        """
        if self._state != DeviceState.CLOSED:
            logger.warning("Device already open (state=%s)", self._state.value)
            return

        target_mode = mode or self._config.mode
        self._state = DeviceState.OPEN
        self._current_mode = target_mode
        self._open_count += 1
        logger.info(
            "Camera ownership registered (mode=%s, hardware owned by capture pipeline)",
            target_mode.value,
        )
    
    def _configure_standard(self) -> None:
        """Configure for standard OpenCV/OpenCV mode."""
        config = self._picam2.create_video_configuration(
            main={"size": (self._config.width, self._config.height), "format": self._config.format},
            controls={"FrameRate": self._config.fps},
        )
        self._picam2.configure(config)
    
    def _configure_onsensor(self) -> None:
        """Configure for IMX500 on-sensor inference."""
        # IMX500 requires specific configuration
        config = self._picam2.create_video_configuration(
            main={"size": (self._config.width, self._config.height), "format": "RGB888"},
            controls={"FrameRate": self._config.fps},
        )
        self._picam2.configure(config)
        # IMX500 runner would be initialized separately
    
    def _configure_hybrid(self) -> None:
        """Configure for hybrid mode (local capture + remote processing)."""
        self._configure_standard()
    
    def _close_device(self) -> None:
        """Release ownership (hardware lifecycle belongs to capture)."""
        if self._state == DeviceState.CLOSED:
            return

        logger.info("Releasing camera ownership")

        try:
            self.stop_streaming()
        except Exception as e:
            logger.debug("stop_streaming during release failed: %s", e)

        with self._picam2_lock:
            self._picam2 = None

        self._state = DeviceState.CLOSED
        self._close_count += 1
        logger.info("Camera ownership released")
    
    # =========================================================================
    # Mode Switching
    # =========================================================================
    
    def switch_mode(self, mode: CameraMode, force: bool = False) -> bool:
        """Switch camera processing mode.
        
        Args:
            mode: Target mode
            force: Force switch even if references exist
            
        Returns:
            True if mode switched successfully
        """
        with self._state_lock:
            if mode == self._current_mode:
                logger.debug("Already in mode %s", mode.value)
                return True
            
            if self._refs and not force:
                owners = list(self._refs.keys())
                raise RuntimeError(
                    f"Cannot switch mode while references exist: {list(self._refs.keys())}. "
                    f"Use force=True to force switch (will notify owners)."
                )
            
            old_mode = self._current_mode
            
            try:
                # Close current device
                self._close_device()
                
                # Update config
                self._config.mode = mode
                
                # Open in new mode
                self._open_device(mode)
                
                self._mode_changes += 1
                
                # Notify callbacks
                for cb in self._mode_change_callbacks:
                    try:
                        cb(old_mode, mode)
                    except Exception as e:
                        logger.error("Mode change callback error: %s", e)
                
                logger.info("Camera mode switched: %s -> %s", old_mode.value, mode.value)
                return True
                
            except Exception as e:
                self._state = DeviceState.ERROR
                self._last_error = e
                logger.exception("Mode switch failed: %s", e)
                raise RuntimeError(f"Mode switch failed: {e}") from e
    
    def get_mode(self) -> CameraMode:
        """Get current processing mode."""
        return self._current_mode
    
    # =========================================================================
    # Streaming
    # =========================================================================
    
    def start_streaming(self, frame_callback: Callable[[Any], None]) -> bool:
        """Start continuous frame streaming.
        
        Args:
            frame_callback: Function to call with each frame
            
        Returns:
            True if streaming started
        """
        with self._state_lock:
            if self._streaming:
                logger.warning("Streaming already active")
                return False
            
            if self._state != DeviceState.OPEN:
                raise RuntimeError(f"Device not open (state={self._state.value})")
            
            self._stop_stream.clear()
            self._frame_publisher = frame_callback
            self._streaming = True
            self._state = DeviceState.STREAMING
            
            self._stream_thread = threading.Thread(
                target=self._stream_loop,
                name="camera-stream",
                daemon=True,
            )
            self._stream_thread.start()
            
            logger.info("Camera streaming started")
            return True
    
    def stop_streaming(self) -> bool:
        """Stop frame streaming."""
        with self._state_lock:
            if not self._streaming:
                return False
            
            self._stop_stream.set()
            self._streaming = False
            
            if self._stream_thread and self._stream_thread.is_alive():
                self._stream_thread.join(timeout=2.0)
            
            self._state = DeviceState.OPEN
            logger.info("Camera streaming stopped")
            return True
    
    def _stream_loop(self) -> None:
        """Background streaming loop."""
        while not self._stop_stream.is_set():
            try:
                if self._picam2 and hasattr(self._picam2, 'capture_array'):
                    frame = self._picam2.capture_array()
                    if self._frame_publisher:
                        self._frame_publisher(frame)
                time.sleep(1.0 / self._config.fps)
            except Exception as e:
                logger.error("Stream loop error: %s", e)
                if self._errors < self._max_recovery_attempts:
                    self._errors += 1
                    time.sleep(0.5)
                else:
                    logger.error("Too many stream errors, stopping")
                    break
    
    def capture_frame(self) -> Optional[Any]:
        """Capture a single frame."""
        with self._picam2_lock:
            if self._picam2:
                try:
                    return self._picam2.capture_array()
                except Exception as e:
                    logger.error("Frame capture failed: %s", e)
        return None
    
    # =========================================================================
    # IMX500 Integration
    # =========================================================================
    
    def set_imx500_runner(self, runner: Any) -> None:
        """Set IMX500 runner for on-sensor inference."""
        with self._state_lock:
            self._imx500_runner = runner
            logger.info("IMX500 runner attached")
    
    def get_imx500_runner(self) -> Optional[Any]:
        """Get IMX500 runner."""
        return self._imx500_runner
    
    # =========================================================================
    # Callbacks
    # =========================================================================
    
    def on_mode_change(self, callback: Callable[[CameraMode, CameraMode], None]) -> Callable[[], None]:
        """Register mode change callback. Returns unregister function."""
        self._mode_change_callbacks.append(callback)
        def unregister():
            if callback in self._mode_change_callbacks:
                self._mode_change_callbacks.remove(callback)
        return unregister
    
    def on_error(self, callback: Callable[[Exception], None]) -> Callable[[], None]:
        """Register error callback."""
        self._error_callbacks.append(callback)
        def unregister():
            if callback in self._error_callbacks:
                self._error_callbacks.remove(callback)
        return unregister
    
    # =========================================================================
    # Status & Metrics
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get device status."""
        with self._state_lock:
            return {
                "state": self._state.value,
                "mode": self._current_mode.value,
                "refs": {k: {"mode": v.mode.value, "count": v.ref_count, "age": time.time() - v.opened_at} 
                         for k, v in self._refs.items()},
                "streaming": self._streaming,
                "open_count": self._open_count,
                "close_count": self._close_count,
                "mode_changes": self._mode_changes,
                "errors": self._errors,
                "last_error": str(self._last_error) if self._last_error else None,
            }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get device metrics."""
        with self._state_lock:
            return {
                "open_count": self._open_count,
                "close_count": self._close_count,
                "mode_changes": self._mode_changes,
                "errors": self._errors,
                "refs_active": len(self._refs),
                "streaming": self._streaming,
            }
    
    def is_healthy(self) -> bool:
        """Check if device is healthy."""
        with self._state_lock:
            return self._state in (DeviceState.OPEN, DeviceState.STREAMING)
    
    # =========================================================================
    # Context Manager
    # =========================================================================
    
    @contextmanager
    def reference(self, owner: str, mode: Optional[CameraMode] = None):
        """Context manager for acquiring a reference."""
        handle = self.acquire(owner, mode)
        try:
            yield handle
        finally:
            handle.release()
    
    def shutdown(self) -> None:
        """Shutdown device manager completely."""
        logger.info("Shutting down CameraDeviceManager")
        
        # Force release all references
        with self._refs_lock:
            for owner in list(self._refs.keys()):
                self.release(owner)
        
        # Close device
        with self._state_lock:
            self._close_device()
        
        logger.info("CameraDeviceManager shutdown complete")





# Convenience functions
def get_camera_manager() -> CameraDeviceManager:
    """Get global camera device manager."""
    return CameraDeviceManager.get_instance()


def acquire_camera(owner: str, mode: Optional[CameraMode] = None) -> DeviceHandle:
    """Acquire camera reference."""
    return get_camera_manager().acquire(owner, mode)


def release_camera(owner: str) -> bool:
    """Release camera reference."""
    return get_camera_manager().release(owner)


@contextmanager
def camera_reference(owner: str, mode: Optional[CameraMode] = None):
    """Context manager for camera reference."""
    manager = get_camera_manager()
    handle = manager.acquire(owner, mode)
    try:
        yield handle
    finally:
        handle.release()


__all__ = [
    "CameraDeviceManager",
    "CameraConfig",
    "CameraMode",
    "DeviceState",
    "DeviceRef",
    "DeviceHandle",
    "get_camera_manager",
    "acquire_camera",
    "release_camera",
    "camera_reference",
]
"""LLM çıktı etiketlerini fiziksel aksiyonlara çeviren mixin."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

try:  # pragma: no cover - opsiyonel bağımlılık
	from modules.ollama.services.tags import extract_llm_tags  # type: ignore
except Exception:  # pragma: no cover
	extract_llm_tags = None  # type: ignore

logger = logging.getLogger("autonomy.response_tags")


class ResponseTagMixin:
	"""Sentry persona etiketlerini çözümleyip donanıma yönlendirir."""

	_DEFAULT_PALETTES: Dict[str, tuple[int, int, int]] = {
		"calm_violet": (120, 80, 255),
		"sunset_gold": (255, 170, 60),
		"alert_red": (255, 45, 45),
		"ocean_teal": (30, 180, 255),
		"arctic_white": (255, 255, 255),
		"forest_green": (60, 200, 90),
		"ember_orange": (255, 110, 40),
		"polar_blue": (90, 150, 255),
	}

	def _handle_llm_actions(
		self,
		text: str,
		action_bundle: Dict[str, Any] | None,
		raw_text: str | None = None,
	) -> str:
		cleaned = text or ""
		commands: List[str] = []
		blocks: List[Dict[str, Any]] = []

		bundle = action_bundle or {}
		if bundle.get("commands") or bundle.get("blocks"):
			commands = [str(cmd).strip().lower() for cmd in bundle.get("commands", []) if str(cmd).strip()]
			blocks = [blk for blk in bundle.get("blocks", []) if isinstance(blk, dict)]
		elif extract_llm_tags is not None:
			source = raw_text or cleaned
			cleaned, parsed = extract_llm_tags(source)
			commands = [str(cmd).strip().lower() for cmd in parsed.get("commands", []) if str(cmd).strip()]
			blocks = [blk for blk in parsed.get("blocks", []) if isinstance(blk, dict)]

		if commands:
			self._dispatch_llm_commands(commands)
		if blocks:
			self._dispatch_llm_blocks(blocks)
		return cleaned.strip()

	# ------------------------------------------------------------------
	def _dispatch_llm_commands(self, commands: List[str]) -> None:
		for cmd in commands:
			if cmd in {"head_nod", "head_nod_abs"}:
				self._servo_nod(strength=1.0 if cmd.endswith("abs") else 0.5)
			elif cmd in {"head_shake", "head_shake_abs"}:
				self._servo_shake(strength=1.0 if cmd.endswith("abs") else 0.5)
			elif cmd == "head_left":
				self._servo_pan_relative(-18)
			elif cmd == "head_right":
				self._servo_pan_relative(18)
			elif cmd == "look_down":
				self._servo_tilt_absolute(125)
			elif cmd == "look_up":
				self._servo_tilt_absolute(70)
			elif cmd == "scan":
				if not self._trigger_animation("look_around"):
					self._head_scan_fallback()
			else:
				if not self._trigger_animation(cmd):
					logger.debug("Unhandled LLM command tag: %s", cmd)

	def _dispatch_llm_blocks(self, blocks: List[Dict[str, Any]]) -> None:
		for blk in blocks:
			kind = str(blk.get("type", "")).lower()
			attrs = blk.get("attrs") or {}
			if not kind:
				continue
			if kind == "lights":
				self._handle_lights_block(attrs)
			elif kind == "servo":
				self._handle_servo_block(attrs)
			elif kind == "anim":
				self._handle_anim_block(attrs)
			elif kind == "event":
				self._handle_event_block(attrs)
			elif kind == "mode":
				self._handle_mode_block(attrs)
			else:
				logger.debug("Unknown structured tag '%s'", kind)

	# --- Komut yardımcıları -------------------------------------------
	def _servo_nod(self, strength: float = 0.5) -> None:
		tilt = self.state.get("current_tilt", 90)
		delta = max(5, min(25, int(20 * strength)))
		positions = [tilt - delta, tilt + delta, tilt]
		for target in positions:
			clamped = max(60, min(130, target))
			self.state["current_tilt"] = clamped
			self.client.move_head(self.state.get("current_pan", 90), clamped)
			time.sleep(0.08)

	def _servo_shake(self, strength: float = 0.5) -> None:
		pan = self.state.get("current_pan", 90)
		delta = max(6, min(28, int(25 * strength)))
		positions = [pan - delta, pan + delta, pan]
		for target in positions:
			clamped = max(45, min(135, target))
			self.state["current_pan"] = clamped
			self.client.move_head(clamped, self.state.get("current_tilt", 90))
			time.sleep(0.08)

	def _servo_pan_relative(self, delta: int) -> None:
		current = self.state.get("current_pan", 90)
		target = max(30, min(150, current + delta))
		self.state["current_pan"] = target
		self.client.move_head(target, self.state.get("current_tilt", 90))

	def _servo_tilt_absolute(self, target: int) -> None:
		clamped = max(60, min(130, target))
		self.state["current_tilt"] = clamped
		self.client.move_head(self.state.get("current_pan", 90), clamped)

	# --- Yapılandırılmış etiketler ------------------------------------
	def _handle_lights_block(self, attrs: Dict[str, Any]) -> None:
		palette_key = str(attrs.get("palette", "")).lower() or None
		rgb = self._resolve_palette_rgb(palette_key)
		intensity = float(attrs.get("intensity", 1.0) or 1.0)
		if rgb:
			scaled = tuple(max(0, min(255, int(channel * max(0.1, min(1.0, intensity))))) for channel in rgb)
			self.client.fill_neopixel_color(*scaled)
		mode = attrs.get("mode") or self._default_light_mode()
		if isinstance(mode, str) and mode:
			self.client.set_neopixel(mode.lower())
		data = dict(attrs)
		data["palette"] = palette_key
		self.client.push_interaction_event("persona.lights", data)

	def _handle_servo_block(self, attrs: Dict[str, Any]) -> None:
		pan = attrs.get("pan")
		tilt = attrs.get("tilt")
		if pan is not None:
			pan = max(0, min(180, int(float(pan))))
			self.state["current_pan"] = pan
		else:
			pan = self.state.get("current_pan", 90)
		if tilt is not None:
			tilt = max(0, min(180, int(float(tilt))))
			self.state["current_tilt"] = tilt
		else:
			tilt = self.state.get("current_tilt", 90)
		self.client.move_head(pan, tilt)

	def _handle_anim_block(self, attrs: Dict[str, Any]) -> None:
		name = attrs.get("name")
		if not isinstance(name, str) or not name:
			return
		speed = float(attrs.get("speed", 1.0) or 1.0)
		loop = bool(attrs.get("loop", False))
		if not self._trigger_animation(name, speed=speed, loop=loop):
			logger.debug("Animation '%s' tag failed to start", name)

	def _handle_event_block(self, attrs: Dict[str, Any]) -> None:
		evt_type = attrs.get("type")
		if not isinstance(evt_type, str) or not evt_type:
			return
		payload = dict(attrs)
		self.client.push_interaction_event(evt_type, payload)

	def _handle_mode_block(self, attrs: Dict[str, Any]) -> None:
		mode_name = attrs.get("name")
		if isinstance(mode_name, str):
			self.state["persona_mode"] = mode_name
		self.client.push_interaction_event("persona.mode", attrs)

	# --- Yardımcılar ---------------------------------------------------
	def _resolve_palette_rgb(self, name: str | None) -> tuple[int, int, int] | None:
		if not name:
			return None
		cfg = getattr(self, "config", {}) or {}
		palettes = {}
		lights_cfg = cfg.get("lights") if isinstance(cfg, dict) else None
		if isinstance(lights_cfg, dict):
			palettes = lights_cfg.get("palettes") or {}
		entry = palettes.get(name) if palettes else None
		if entry is None:
			entry = self._DEFAULT_PALETTES.get(name)
		if isinstance(entry, dict):
			entry = entry.get("rgb")
		if isinstance(entry, (list, tuple)) and len(entry) == 3:
			try:
				return tuple(int(x) for x in entry)
			except (TypeError, ValueError):
				return None
		return None

	def _default_light_mode(self) -> str | None:
		cfg = getattr(self, "config", {}) or {}
		lights_cfg = cfg.get("lights") if isinstance(cfg, dict) else None
		if isinstance(lights_cfg, dict):
			mode = lights_cfg.get("default_mode")
			if isinstance(mode, str) and mode:
				return mode
		return None

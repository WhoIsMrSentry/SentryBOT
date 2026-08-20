"""Runtime configuration registry.

Modules register hot-applyable keys (with bounds and an apply callback) at
startup. Consumers update values through :meth:`RuntimeConfigRegistry.set` and
the registry dispatches the callback while recording an audit entry in
``social_db.interaction_events`` (kind ``config.audit``) when available.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("config_center.runtime")

ApplyFn = Callable[[Any], Optional[Dict[str, Any]]]


@dataclass
class RuntimeKey:
    """Descriptor for a single hot-applyable configuration key."""

    name: str
    module: str
    type: str = "string"  # one of: string, int, float, bool, choice, list
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    choices: Optional[Tuple[Any, ...]] = None
    description: str = ""
    sensitive: bool = False
    apply_fn: Optional[ApplyFn] = None
    value: Any = None
    updated_at: float = field(default_factory=time.time)
    updated_by: str = "system"

    def to_dict(self, *, redact: bool = True) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "name": self.name,
            "module": self.module,
            "type": self.type,
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "choices": list(self.choices) if self.choices is not None else None,
            "description": self.description,
            "sensitive": self.sensitive,
            "value": self.value,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }
        if self.sensitive and redact:
            out["value"] = "***"
            out["default"] = "***"
        return out


class RuntimeConfigRegistry:
    """Thread-safe registry mapping ``module.key`` -> :class:`RuntimeKey`."""

    def __init__(self, social_db: Optional[Any] = None) -> None:
        if social_db is None:
            try:
                from modules.cognitive_memory import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db
        self._lock = threading.RLock()
        self._keys: Dict[str, RuntimeKey] = {}

    # ── Registration ──────────────────────────────────────────────────
    def register(
        self,
        module: str,
        name: str,
        *,
        type: str = "string",
        default: Any = None,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
        choices: Optional[Iterable[Any]] = None,
        description: str = "",
        sensitive: bool = False,
        apply_fn: Optional[ApplyFn] = None,
    ) -> RuntimeKey:
        key = self._compose(module, name)
        with self._lock:
            existing = self._keys.get(key)
            value = default if existing is None else existing.value
            entry = RuntimeKey(
                name=name,
                module=module,
                type=type,
                default=default,
                minimum=minimum,
                maximum=maximum,
                choices=tuple(choices) if choices is not None else None,
                description=description,
                sensitive=bool(sensitive),
                apply_fn=apply_fn,
                value=value,
                updated_at=time.time() if existing is None else existing.updated_at,
                updated_by="system" if existing is None else existing.updated_by,
            )
            self._keys[key] = entry
            return entry

    def unregister(self, module: str, name: str) -> None:
        with self._lock:
            self._keys.pop(self._compose(module, name), None)

    # ── Access ────────────────────────────────────────────────────────
    def list_keys(self, *, module: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            keys = list(self._keys.values())
        if module:
            keys = [k for k in keys if k.module == module]
        keys.sort(key=lambda k: (k.module, k.name))
        return [k.to_dict() for k in keys]

    def get(self, module: str, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._keys.get(self._compose(module, name))
            return entry.to_dict() if entry else None

    def get_value(self, module: str, name: str, default: Any = None) -> Any:
        with self._lock:
            entry = self._keys.get(self._compose(module, name))
            return entry.value if entry is not None else default

    # ── Mutation ──────────────────────────────────────────────────────
    def set(
        self,
        module: str,
        name: str,
        value: Any,
        *,
        actor: str = "admin",
        source: str = "api",
    ) -> Dict[str, Any]:
        composed = self._compose(module, name)
        with self._lock:
            entry = self._keys.get(composed)
        if entry is None:
            return {"ok": False, "error": "unknown_key", "key": composed}

        coerced, err = self._coerce(entry, value)
        if err:
            return {"ok": False, "error": err, "key": composed}

        applied_payload: Optional[Dict[str, Any]] = None
        if entry.apply_fn is not None:
            try:
                applied_payload = entry.apply_fn(coerced)
            except Exception as exc:
                logger.warning("apply_fn for %s raised: %s", composed, exc)
                return {"ok": False, "error": "apply_failed", "exception": str(exc)}

        prev_value = entry.value
        entry.value = coerced
        entry.updated_at = time.time()
        entry.updated_by = str(actor or "admin")

        self._audit(
            entry,
            previous=prev_value,
            new_value=coerced,
            actor=str(actor or "admin"),
            source=str(source or "api"),
            applied=applied_payload,
        )
        return {
            "ok": True,
            "key": composed,
            "value": coerced if not entry.sensitive else "***",
            "applied": applied_payload or {},
        }

    def bulk_set(self, items: Dict[str, Any], *, actor: str = "admin", source: str = "api") -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for composed, value in (items or {}).items():
            try:
                module, name = self._split(composed)
            except ValueError as exc:
                results.append({"ok": False, "error": str(exc), "key": composed})
                continue
            results.append(self.set(module, name, value, actor=actor, source=source))
        return results

    # ── Audit ────────────────────────────────────────────────────────
    def audit_log(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        if self._social_db is None:
            return []
        try:
            return self._social_db.interaction_events.recent(limit=limit, kind="config.audit")
        except Exception as exc:
            logger.debug("audit fetch failed: %s", exc)
            return []

    # ── Internal ──────────────────────────────────────────────────────
    @staticmethod
    def _compose(module: str, name: str) -> str:
        return f"{str(module).strip()}.{str(name).strip()}"

    @staticmethod
    def _split(composed: str) -> Tuple[str, str]:
        parts = str(composed).split(".", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"invalid runtime key: {composed!r}")
        return parts[0], parts[1]

    @staticmethod
    def _coerce_int(value: Any) -> Any:
        return int(value)

    @staticmethod
    def _coerce_float(value: Any) -> Any:
        return float(value)

    @staticmethod
    def _coerce_bool(value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _coerce_choice(self, key: RuntimeKey, value: Any) -> Tuple[Any, Optional[str]]:
        if key.choices is not None and value not in key.choices:
            return None, f"invalid_choice (allowed={list(key.choices)})"
        return value, None

    @staticmethod
    def _coerce_list(value: Any) -> Tuple[Any, Optional[str]]:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()], None
        if isinstance(value, (list, tuple)):
            return list(value), None
        return None, "invalid_list"

    @staticmethod
    def _coerce_string(value: Any) -> Any:
        return str(value) if value is not None else ""

    _COERCE_MAP = {
        "int": (_coerce_int, False),
        "float": (_coerce_float, False),
        "bool": (_coerce_bool, False),
        "choice": (None, True),
        "list": (None, True),
    }

    def _coerce(self, key: RuntimeKey, value: Any) -> Tuple[Any, Optional[str]]:
        t = (key.type or "string").lower()
        try:
            if t == "choice":
                return self._coerce_choice(key, value)
            if t == "list":
                return self._coerce_list(value)
            fn = self._COERCE_MAP.get(t, (self._coerce_string, False))[0]
            coerced = fn(value) if fn else self._coerce_string(value)
        except (TypeError, ValueError) as exc:
            return None, f"coerce_failed:{exc}"

        if isinstance(coerced, (int, float)):
            if key.minimum is not None and coerced < key.minimum:
                return None, f"below_minimum ({key.minimum})"
            if key.maximum is not None and coerced > key.maximum:
                return None, f"above_maximum ({key.maximum})"
        return coerced, None

    def _audit(
        self,
        key: RuntimeKey,
        *,
        previous: Any,
        new_value: Any,
        actor: str,
        source: str,
        applied: Optional[Dict[str, Any]],
    ) -> None:
        if self._social_db is None:
            return
        payload = {
            "key": self._compose(key.module, key.name),
            "module": key.module,
            "name": key.name,
            "previous": "***" if key.sensitive else previous,
            "new": "***" if key.sensitive else new_value,
            "actor": actor,
            "source": source,
            "applied": applied or {},
        }
        try:
            self._social_db.interaction_events.log("config.audit", payload=payload)
        except Exception as exc:
            logger.debug("audit log failed: %s", exc)


# ── Process-wide default ──────────────────────────────────────────────
_DEFAULT_LOCK = threading.Lock()
_DEFAULT: Optional[RuntimeConfigRegistry] = None


def get_default_registry() -> Optional[RuntimeConfigRegistry]:
    with _DEFAULT_LOCK:
        return _DEFAULT


def set_default_registry(registry: RuntimeConfigRegistry) -> None:
    global _DEFAULT
    with _DEFAULT_LOCK:
        _DEFAULT = registry

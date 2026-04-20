from __future__ import annotations

def create_app(*args, **kwargs):
	# Lazy import to avoid package import-time failures during gateway bootstrap.
	from .xVlmBridgeService import create_app as _create_app  # type: ignore
	return _create_app(*args, **kwargs)


__all__ = ["create_app"]

"""Resolve gateway base URL for loopback HTTP calls between modules.

Re-exports canonical helpers from modules.common.url_utils for backward compatibility.
"""
from __future__ import annotations

from modules.common.url_utils import (
    gateway_base_from_agent_cfg,
    gateway_url,
    patch_service_endpoints,
    resolve_config_url,
    resolve_gateway_base_url,
    rewrite_loopback_urls,
)

__all__ = [
    "gateway_base_from_agent_cfg",
    "gateway_url",
    "patch_service_endpoints",
    "resolve_config_url",
    "resolve_gateway_base_url",
    "rewrite_loopback_urls",
]

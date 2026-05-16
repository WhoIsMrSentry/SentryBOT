"""Helpers for restricting Admin UI access to LAN clients.

A request is accepted when its remote address (or ``X-Forwarded-For`` head)
falls inside one of the configured CIDR networks. Loopback addresses and link
local ranges are always permitted so local maintenance keeps working.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Iterable, Optional, Sequence

logger = logging.getLogger("admin_ui.lan_filter")


_DEFAULT_NETS = (
    "127.0.0.0/8",
    "::1/128",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "fc00::/7",
    "fe80::/10",
)


def parse_networks(networks: Optional[Sequence[str]]) -> list:
    nets = []
    for raw in (networks or _DEFAULT_NETS):
        if not raw:
            continue
        try:
            nets.append(ipaddress.ip_network(str(raw), strict=False))
        except ValueError as exc:  # pragma: no cover - config issue
            logger.warning("ignoring invalid admin_ui network %r: %s", raw, exc)
    return nets


def _candidate_ips(remote: str, xff: Optional[str]) -> Iterable[str]:
    if xff:
        for token in xff.split(","):
            token = token.strip()
            if token:
                yield token
    if remote:
        yield remote


def is_allowed_client(
    remote_addr: str,
    xff_header: Optional[str],
    networks: Sequence[str],
    enforce: bool,
) -> bool:
    if not enforce:
        return True
    parsed_nets = parse_networks(networks)
    if not parsed_nets:
        return True
    for raw in _candidate_ips(remote_addr or "", xff_header):
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        for net in parsed_nets:
            try:
                if ip in net:
                    return True
            except TypeError:
                continue
    return False

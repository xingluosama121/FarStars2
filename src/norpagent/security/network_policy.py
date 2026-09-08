# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Plugin network policy / SSRF protection (zero third-party dependencies).

Migrated from the existing application's plugin_system.network_policy; four policy
granularities:

- ``deny``: plugins may not access any network (default, safest)
- ``audited_public``: only "audited public" access: must match URL / domain allowlists
- ``public_only``: all public networks allowed; internal / loopback / link-local blocked
- ``allow_all``: all networks allowed (only recommended for trusted plugins)

Whatever the granularity, unless allow_all, private / reserved / loopback /
link-local / cloud-metadata addresses are always rejected (SSRF protection).
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

POLICY_DENY = "deny"
POLICY_AUDITED_PUBLIC = "audited_public"
POLICY_PUBLIC_ONLY = "public_only"
POLICY_ALLOW_ALL = "allow_all"

VALID_POLICIES = (POLICY_DENY, POLICY_AUDITED_PUBLIC, POLICY_PUBLIC_ONLY, POLICY_ALLOW_ALL)

# cloud metadata service addresses (high-value SSRF targets, always blocked)
_METADATA_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata",
}


@dataclass
class NetworkDecision:
    """The verdict for one network access."""

    allowed: bool
    reason: str = ""


def _parse_host(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url if "://" in url else f"http://{url}")
        return parsed.hostname
    except Exception:
        return None


def _resolve(host: str) -> List[str]:
    try:
        infos = socket.getaddrinfo(host, None)
        ips: List[str] = []
        for info in infos:
            addr = info[4][0]
            if addr not in ips:
                ips.append(addr)
        return ips
    except Exception:
        return []


def _is_internal_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unresolvable is treated as internal / untrusted
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_internal_host(host: str) -> bool:
    """Decide whether a host points at an internal / loopback / metadata address.

    Prefers text-level checks (no DNS triggered, avoiding the common rebinding
    path), then checks every resolved IP.
    """
    if not host:
        return True
    host_l = host.strip().lower()
    if host_l in _METADATA_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host_l)
        return _is_internal_ip(host_l)
    except ValueError:
        pass
    if host_l in ("localhost", "localhost.localdomain") or host_l.endswith(".localhost"):
        return True
    if host_l.endswith(".local") or host_l.endswith(".internal") or host_l.endswith(".lan"):
        return True
    for ip_str in _resolve(host):
        if _is_internal_ip(ip_str):
            return True
    return False


class NetworkPolicy:
    """Plugin network policy engine."""

    def __init__(self, config: Optional[dict] = None) -> None:
        config = config or {}
        self.policy = config.get("plugin_network_policy", POLICY_DENY)
        if self.policy not in VALID_POLICIES:
            self.policy = POLICY_DENY
        self.url_allowlist = self._norm_list(config.get("plugin_network_url_allowlist"))
        self.domain_allowlist = self._norm_list(config.get("plugin_network_domain_allowlist"))

    @staticmethod
    def _norm_list(v) -> List[str]:
        if not isinstance(v, (list, tuple)):
            return []
        return [str(item).strip() for item in v if isinstance(item, str) and item.strip()]

    def check_url(self, url: str) -> NetworkDecision:
        """Decide whether a URL is allowed to be accessed."""
        if not url or not isinstance(url, str):
            return NetworkDecision(False, "empty URL")
        host = _parse_host(url)
        if not host:
            return NetworkDecision(False, f"cannot resolve URL host: {url}")
        if self.policy == POLICY_DENY:
            return NetworkDecision(False, "network policy is deny; plugins may not access the network")
        if self.policy != POLICY_ALLOW_ALL:
            if is_internal_host(host):
                return NetworkDecision(
                    False, f"SSRF blocked: access to internal/loopback/metadata addresses is forbidden ({host})"
                )
        if self.policy == POLICY_AUDITED_PUBLIC:
            if not self._in_allowlist(url, host):
                return NetworkDecision(False, f"URL not in allowlist ({host})")
        return NetworkDecision(True, "ok")

    def _in_allowlist(self, url: str, host: str) -> bool:
        for allowed in self.url_allowlist:
            if url == allowed or url.startswith(allowed):
                return True
        for allowed_domain in self.domain_allowlist:
            if host == allowed_domain or host.endswith("." + allowed_domain):
                return True
        return False

    def get_config(self) -> dict:
        return {
            "policy": self.policy,
            "url_allowlist": list(self.url_allowlist),
            "domain_allowlist": list(self.domain_allowlist),
        }

"""Network helpers shared across the application.

Provides proxy-aware client IP extraction. Lives in
``core/`` so any module — including other ``core/``
modules such as rate limiting — can use it without
creating a dependency on the ``users`` package.
"""

import ipaddress
import re
import socket
import threading
import time

from fastapi import Request

import core.config as core_config
import core.logger as core_logger

_TRUSTED_PROXY_HOSTNAME_REFRESH_SECONDS = 60.0
_trusted_proxy_hostname_refresh_lock = threading.Lock()
_trusted_proxy_hostname_last_refresh = float("-inf")

# RFC 1123 hostname syntax: labels of 1-63 alphanumeric/hyphen
# characters, separated by dots. Hyphens may not start or end
# a label. Total length is capped at 253 characters.
_HOSTNAME_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?)"  # first label
    r"(?:\.(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?))*$",  # more
    re.IGNORECASE,
)


def _looks_like_ip(value: str) -> bool:
    """Best-effort check that ``value`` is an IP literal.

    Used by startup/config validation helpers to decide
    whether an entry is an IP literal or a hostname.

    Args:
        value: Candidate IP literal or hostname.

    Returns:
        True when ``value`` is an IPv4/IPv6 literal.
    """
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _is_valid_hostname(value: str) -> bool:
    """Return True when value is a syntactically valid hostname.

    Validates RFC 1123 hostname syntax. Rejects values that
    contain URL schemes, ports, or other non-hostname characters
    (e.g., ``caddy:8080`` or ``http://caddy``).

    Args:
        value: Candidate hostname to validate.

    Returns:
        True when value conforms to RFC 1123 hostname syntax.
    """
    return len(value) <= 253 and _HOSTNAME_RE.match(value) is not None


def _resolve_hostname(hostname: str) -> list[str]:
    """Resolve a hostname to a list of IP addresses.

    Called when refreshing TRUSTED_PROXIES hostnames to their
    IP addresses. Uses socket.getaddrinfo() to resolve both
    IPv4 and IPv6 addresses.

    Args:
        hostname: The hostname to resolve (e.g., 'proxy.internal').

    Returns:
        List of resolved IP addresses (e.g., ['10.0.0.5', '10.0.0.6']).
        Returns an empty list if resolution fails (a warning is logged).
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
        ips = [str(info[4][0]) for info in infos]
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_ips = []
        for ip in ips:
            if ip not in seen:
                seen.add(ip)
                unique_ips.append(ip)
        return unique_ips
    except socket.gaierror as err:
        core_logger.print_to_log_and_console(
            f"Failed to resolve TRUSTED_PROXIES hostname '{hostname}': {err}",
            "warning",
        )
        return []


def _trusted_proxy_hostname_entries() -> list[str]:
    """Return configured TRUSTED_PROXIES hostnames.

    Returns:
        Hostname entries that need DNS resolution.
    """
    hostnames: list[str] = []
    for configured_entry in core_config.settings.TRUSTED_PROXIES:
        entry = configured_entry.strip()
        if not entry:
            continue
        if entry == "*" or "/" in entry or _looks_like_ip(entry):
            continue
        hostnames.append(entry)
    return hostnames


def _trusted_proxy_hostname_cache_is_fresh(now: float) -> bool:
    """Check whether trusted proxy hostname cache is fresh.

    Args:
        now: Current monotonic timestamp.

    Returns:
        True when the refresh throttle window has not elapsed.
    """
    cache_age = now - _trusted_proxy_hostname_last_refresh
    return cache_age < _TRUSTED_PROXY_HOSTNAME_REFRESH_SECONDS


def refresh_trusted_proxy_hostnames(
    *,
    force: bool = False,
    log_success: bool = False,
) -> dict[str, list[str]]:
    """Refresh TRUSTED_PROXIES hostname resolutions.

    Args:
        force: Refresh even when the cache is still fresh.
        log_success: Log successful hostname resolutions.

    Returns:
        Mapping of hostnames to resolved IP addresses.
    """
    global _trusted_proxy_hostname_last_refresh

    hostnames = _trusted_proxy_hostname_entries()
    if not hostnames:
        core_config.settings._resolved_trusted_proxy_ips = set()
        return {}

    now = time.monotonic()
    if not force and _trusted_proxy_hostname_cache_is_fresh(now):
        return {}

    with _trusted_proxy_hostname_refresh_lock:
        now = time.monotonic()
        if not force and _trusted_proxy_hostname_cache_is_fresh(now):
            return {}

        resolved_map: dict[str, list[str]] = {}
        all_resolved_ips: set[str] = set()
        for hostname in hostnames:
            ips = _resolve_hostname(hostname)
            if not ips:
                continue

            resolved_map[hostname] = ips
            all_resolved_ips.update(ips)
            if log_success:
                core_logger.print_to_log_and_console(
                    f"Resolved TRUSTED_PROXIES hostname '{hostname}' to {ips}",
                    "info",
                )

        core_config.settings._resolved_trusted_proxy_ips = all_resolved_ips
        _trusted_proxy_hostname_last_refresh = now

    return resolved_map


def _is_trusted_peer(peer_ip: str) -> bool:
    """Check whether ``peer_ip`` is in the TRUSTED_PROXIES allow-list.

    Supports exact IPs and CIDR notation. The special value ``"*"``
    (the default) trusts every peer. Also supports resolved hostnames
    (cached from startup resolution).

    Args:
        peer_ip: The direct TCP-connection IP of the caller.

    Returns:
        True if the peer is trusted, False otherwise.
    """
    trusted = core_config.settings.TRUSTED_PROXIES
    if trusted == ["*"]:
        return True
    try:
        addr = ipaddress.ip_address(peer_ip)
        for entry in trusted:
            entry = entry.strip()
            if not entry:
                continue
            try:
                network = ipaddress.ip_network(entry, strict=False)
                if addr in network:
                    return True
            except ValueError:
                # Entry is not a valid network — compare as plain string
                if peer_ip == entry:
                    return True
    except ValueError:
        pass

    hostnames = _trusted_proxy_hostname_entries()
    if not hostnames:
        return False

    resolved_ips = core_config.settings._resolved_trusted_proxy_ips
    return peer_ip in resolved_ips


def get_ip_address(request: Request) -> str:
    """
    Extract client IP address from request, respecting TRUSTED_PROXIES.

    Proxy headers (``X-Forwarded-For``, ``X-Real-IP``) are only trusted
    when the direct TCP peer matches an entry in ``TRUSTED_PROXIES``.
    This prevents attackers from spoofing their IP by injecting those
    headers on direct connections.

    When ``TRUSTED_PROXIES`` is ``["*"]`` (the default) all peers are
    trusted.

    Args:
        request: Request object with headers and client info.

    Returns:
        Client IP address or "unknown" if indeterminate.
    """
    peer_ip = request.client.host if request.client else None

    if peer_ip and _is_trusted_peer(peer_ip):
        # Peer is a trusted proxy — honour the forwarded headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the leftmost IP: the original client
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

    # Untrusted peer or no peer info — use the raw socket IP
    return peer_ip or "unknown"

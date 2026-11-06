"""Tests for core.network module."""

import socket
from unittest.mock import MagicMock, patch

from fastapi import Request

import core.network as core_network


class TestIsValidHostname:
    """Tests for _is_valid_hostname function."""

    def test_simple_hostname(self):
        assert core_network._is_valid_hostname("caddy") is True

    def test_dotted_hostname(self):
        assert core_network._is_valid_hostname("proxy.internal") is True

    def test_hyphenated_label(self):
        assert core_network._is_valid_hostname("reverse-proxy") is True

    def test_multi_label(self):
        assert core_network._is_valid_hostname("my.proxy.internal") is True

    def test_numeric_label(self):
        # Labels that look like numbers are valid hostnames.
        assert core_network._is_valid_hostname("proxy1") is True

    def test_url_scheme_rejected(self):
        assert core_network._is_valid_hostname("http://caddy") is False

    def test_port_suffix_rejected(self):
        assert core_network._is_valid_hostname("caddy:8080") is False

    def test_leading_hyphen_rejected(self):
        assert core_network._is_valid_hostname("-proxy") is False

    def test_trailing_hyphen_rejected(self):
        assert core_network._is_valid_hostname("proxy-") is False

    def test_empty_string_rejected(self):
        assert core_network._is_valid_hostname("") is False

    def test_too_long_rejected(self):
        long_host = "a" * 254
        assert core_network._is_valid_hostname(long_host) is False


class TestRefreshTrustedProxyHostnames:
    """Tests for refresh_trusted_proxy_hostnames function."""

    def test_returns_empty_when_no_hostnames(self):
        with patch.object(
            core_network.core_config.settings,
            "TRUSTED_PROXIES",
            ["10.0.0.0/8"],
        ):
            result = core_network.refresh_trusted_proxy_hostnames()
            assert result == {}

    def test_skips_refresh_when_cache_fresh(self):
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network,
                "_trusted_proxy_hostname_last_refresh",
                100.0,
            ),
            patch("core.network.time.monotonic", return_value=110.0),
            patch("core.network._resolve_hostname") as mock_resolve,
        ):
            result = core_network.refresh_trusted_proxy_hostnames()
            assert result == {}
            mock_resolve.assert_not_called()

    def test_force_bypasses_ttl(self):
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network,
                "_trusted_proxy_hostname_last_refresh",
                100.0,
            ),
            patch("core.network.time.monotonic", return_value=110.0),
            patch(
                "core.network._resolve_hostname",
                return_value=["10.0.0.6"],
            ) as mock_resolve,
        ):
            result = core_network.refresh_trusted_proxy_hostnames(force=True)
            assert result == {"proxy.internal": ["10.0.0.6"]}
            mock_resolve.assert_called_once_with("proxy.internal")

    def test_replaces_old_ips_after_refresh(self):
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network.core_config.settings,
                "_resolved_trusted_proxy_ips",
                {"10.0.0.5"},
            ),
            patch.object(
                core_network,
                "_trusted_proxy_hostname_last_refresh",
                1.0,
            ),
            patch("core.network.time.monotonic", return_value=100.0),
            patch(
                "core.network._resolve_hostname",
                return_value=["10.0.0.6"],
            ),
        ):
            core_network.refresh_trusted_proxy_hostnames()
            settings = core_network.core_config.settings
            assert settings._resolved_trusted_proxy_ips == {"10.0.0.6"}


class TestResolveHostname:
    """Tests for _resolve_hostname function."""

    def test_resolve_hostname_single_ip(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # Simulate getaddrinfo return format: (family, type, proto, canonname, sockaddr)
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
            ]
            result = core_network._resolve_hostname("proxy.internal")
            assert result == ["10.0.0.5"]
            mock_getaddrinfo.assert_called_once_with("proxy.internal", None)

    def test_resolve_hostname_multiple_ips(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.6", 0)),
            ]
            result = core_network._resolve_hostname("proxy.internal")
            assert set(result) == {"10.0.0.5", "10.0.0.6"}

    def test_resolve_hostname_deduplicates(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
                (socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("10.0.0.5", 0)),
            ]
            result = core_network._resolve_hostname("proxy.internal")
            assert result == ["10.0.0.5"]

    def test_resolve_hostname_dns_failure(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = socket.gaierror("Name resolution failed")
            result = core_network._resolve_hostname("nonexistent.hostname")
            assert result == []

    def test_resolve_hostname_ipv6(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 0, 0, 0)),
            ]
            result = core_network._resolve_hostname("ipv6proxy.internal")
            assert result == ["2001:db8::1"]

    def test_resolve_hostname_mixed_ipv4_ipv6(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 0, 0, 0)),
            ]
            result = core_network._resolve_hostname("proxy.internal")
            assert set(result) == {"10.0.0.5", "2001:db8::1"}


class TestIsTrustedPeer:
    """Tests for _is_trusted_peer function."""

    def test_wildcard_trusts_all(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["*"]):
            assert core_network._is_trusted_peer("192.168.1.1") is True
            assert core_network._is_trusted_peer("10.0.0.1") is True

    def test_exact_ip_match(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["192.168.1.1"]):
            assert core_network._is_trusted_peer("192.168.1.1") is True

    def test_exact_ip_no_match(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.1"]):
            assert core_network._is_trusted_peer("192.168.1.1") is False

    def test_cidr_match(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            assert core_network._is_trusted_peer("10.0.0.1") is True
            assert core_network._is_trusted_peer("10.255.255.255") is True

    def test_cidr_no_match(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            assert core_network._is_trusted_peer("192.168.1.1") is False

    def test_empty_trusted_proxies(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", []):
            assert core_network._is_trusted_peer("10.0.0.1") is False

    def test_invalid_peer_ip(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            assert core_network._is_trusted_peer("not-an-ip") is False

    def test_resolved_hostname_ip_match(self):
        """Test that _is_trusted_peer checks resolved hostname IPs."""
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network.core_config.settings,
                "_resolved_trusted_proxy_ips",
                {"10.0.0.5"},
            ),
        ):
            assert core_network._is_trusted_peer("10.0.0.5") is True

    def test_resolved_hostname_ip_no_match(self):
        """Test that unresolved IPs don't match."""
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network.core_config.settings,
                "_resolved_trusted_proxy_ips",
                {"10.0.0.5"},
            ),
        ):
            assert core_network._is_trusted_peer("10.0.0.6") is False

    def test_resolved_hostname_multiple_ips(self):
        """Test that multiple resolved IPs are all trusted."""
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network.core_config.settings,
                "_resolved_trusted_proxy_ips",
                {"10.0.0.5", "10.0.0.6", "2001:db8::1"},
            ),
        ):
            assert core_network._is_trusted_peer("10.0.0.5") is True
            assert core_network._is_trusted_peer("10.0.0.6") is True
            assert core_network._is_trusted_peer("2001:db8::1") is True


class TestGetIpAddress:
    """Tests for get_ip_address function."""

    def test_no_client_returns_unknown(self):
        request = MagicMock(spec=Request)
        request.client = None
        result = core_network.get_ip_address(request)
        assert result == "unknown"

    def test_untrusted_peer_uses_direct_ip(self):
        request = MagicMock(spec=Request)
        request.client.host = "203.0.113.5"
        request.headers = {"X-Forwarded-For": "1.2.3.4"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "203.0.113.5"

    def test_trusted_proxy_x_forwarded_for(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "1.2.3.4"

    def test_trusted_proxy_x_real_ip(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.1"
        request.headers = {"X-Real-IP": "5.6.7.8"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "5.6.7.8"

    def test_trusted_proxy_prefers_x_forwarded_for(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["*"]):
            result = core_network.get_ip_address(request)
            assert result == "1.2.3.4"

    def test_trusted_proxy_no_headers_returns_direct_ip(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.1"
        request.headers = {}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "10.0.0.1"

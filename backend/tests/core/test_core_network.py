"""Tests for uncovered lines in core.network module."""

from unittest.mock import patch

import core.network as core_network


class TestIsTrustedPeerEdgeCases:
    """Edge cases for _is_trusted_peer."""

    def test_empty_entry_skipped(self):
        """Empty entry in trusted_proxies is skipped (line 39)."""
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["", "10.0.0.0/8"]):
            assert core_network._is_trusted_peer("10.0.0.1") is True

    def test_non_parseable_entry_as_plain_string(self):
        """Non-CIDR entry compared as plain string (lines 44-47)."""
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["not-a-cidr"]):
            assert core_network._is_trusted_peer("10.0.0.1") is False

#!/usr/bin/env python3
"""Tests unitaires pour causal_validator (RLM-GRAPH).

Utilise uniquement la stdlib (unittest, unittest.mock).
Simule les réponses du serveur ROOTX : succès, échec HTTP, timeout, connexion refusée.
"""

from __future__ import annotations

import json
import urllib.error
import unittest
from unittest.mock import MagicMock, patch

from causal_validator import CausalValidator, CausalValidatorConfig, build_causal_validator


class _MockResponse:
    """Mock d'une réponse urllib.request.urlopen."""

    def __init__(self, status: int, body: dict) -> None:
        self.status = status
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_MockResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


class TestCausalValidator(unittest.TestCase):
    """Suite de tests pour CausalValidator."""

    def setUp(self) -> None:
        self.config = CausalValidatorConfig(
            rootx_endpoint="http://localhost:8030",
            timeout_seconds=5,
        )
        self.validator = CausalValidator(config=self.config)

    # ------------------------------------------------------------------
    # health()
    # ------------------------------------------------------------------

    @patch("causal_validator.urllib.request.urlopen")
    def test_health_ok(self, mock_urlopen: MagicMock) -> None:
        """health() retourne status ok quand ROOTX repond 200."""
        mock_urlopen.return_value = _MockResponse(200, {"status": "ok", "service": "ROOTX"})
        result = self.validator.health()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["service"], "rlm-graph")
        self.assertEqual(result["rootx"]["status"], "ok")
        mock_urlopen.assert_called_once()

    @patch("causal_validator.urllib.request.urlopen")
    def test_health_connection_refused(self, mock_urlopen: MagicMock) -> None:
        """health() retourne status degraded quand la connexion est refusee."""
        mock_urlopen.side_effect = ConnectionRefusedError("connexion refusee")
        result = self.validator.health()

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["service"], "rlm-graph")
        self.assertIn("rootx_error", result)
        self.assertIn("connexion refusee", result["rootx_error"])

    # ------------------------------------------------------------------
    # validate_causal()
    # ------------------------------------------------------------------

    @patch("causal_validator.urllib.request.urlopen")
    def test_validate_causal_success(self, mock_urlopen: MagicMock) -> None:
        """validate_causal retourne valid=True quand ROOTX accepte."""
        mock_urlopen.return_value = _MockResponse(
            200, {"valid": True, "confidence": 0.95, "errors": []}
        )
        result = self.validator.validate_causal("test-service")

        self.assertTrue(result["valid"])
        self.assertEqual(result["confidence"], 0.95)
        self.assertEqual(result["errors"], [])

        # Verification du payload envoye
        call_args = mock_urlopen.call_args
        self.assertIsNotNone(call_args)
        req = call_args[0][0]
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.header_items()[0][1], "application/json")

    @patch("causal_validator.urllib.request.urlopen")
    def test_validate_causal_http_error(self, mock_urlopen: MagicMock) -> None:
        """validate_causal retourne valid=False sur erreur HTTP 500."""
        http_error = urllib.error.HTTPError(
            url="http://localhost:8030/validate",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None,
        )
        mock_urlopen.side_effect = http_error
        result = self.validator.validate_causal("failing-service")

        self.assertFalse(result["valid"])
        self.assertEqual(result["confidence"], 0.0)
        self.assertIn("HTTP 500", result["errors"][0])

    @patch("causal_validator.urllib.request.urlopen")
    def test_validate_causal_timeout(self, mock_urlopen: MagicMock) -> None:
        """validate_causal retourne valid=False sur timeout."""
        import socket

        mock_urlopen.side_effect = TimeoutError("timed out")
        result = self.validator.validate_causal("slow-service")

        self.assertFalse(result["valid"])
        self.assertEqual(result["confidence"], 0.0)
        self.assertIn("timed out", result["errors"][0])

    @patch("causal_validator.urllib.request.urlopen")
    def test_validate_causal_generic_exception(self, mock_urlopen: MagicMock) -> None:
        """validate_causal retourne valid=False sur exception generique."""
        mock_urlopen.side_effect = OSError("network unreachable")
        result = self.validator.validate_causal("unreachable-service")

        self.assertFalse(result["valid"])
        self.assertEqual(result["confidence"], 0.0)
        self.assertIn("network unreachable", result["errors"][0])

    # ------------------------------------------------------------------
    # build_causal_validator (factory)
    # ------------------------------------------------------------------

    def test_build_causal_validator_default(self) -> None:
        """La factory retourne une instance de CausalValidator."""
        v = build_causal_validator()
        self.assertIsInstance(v, CausalValidator)
        self.assertEqual(v.config.rootx_endpoint, "http://localhost:8030")

    def test_build_causal_validator_custom_config(self) -> None:
        """La factory utilise la config fournie."""
        cfg = CausalValidatorConfig(rootx_endpoint="http://localhost:9999", timeout_seconds=2)
        v = build_causal_validator(config=cfg)
        self.assertEqual(v.config.rootx_endpoint, "http://localhost:9999")
        self.assertEqual(v.config.timeout_seconds, 2)


if __name__ == "__main__":
    unittest.main()

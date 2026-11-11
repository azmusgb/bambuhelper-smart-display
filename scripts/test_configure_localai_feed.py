#!/usr/bin/env python3
"""Tests for scripts/configure_localai_feed.py: the CA it sends must be the chosen service's (31 Oct 2026)."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("configure_localai_feed", ROOT / "scripts/configure_localai_feed.py")
if spec is None or spec.loader is None:
    raise ImportError("cannot load scripts/configure_localai_feed.py")
configure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)

PEM = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"


def run(*argv: str) -> None:
    with mock.patch.object(sys, "argv", ["configure_localai_feed.py", *argv]):
        configure.main()


class CaTests(unittest.TestCase):
    def test_pihub_without_ca_refuses_before_contacting_the_display(self) -> None:
        with mock.patch.object(configure, "Client", side_effect=AssertionError("contacted the display")):
            with self.assertRaises(SystemExit) as caught:
                run("--backend", "pihub")
        self.assertNotEqual(caught.exception.code, 0)
        self.assertIn("For Pi Hub, pass --ca with Pi Hub's CA (http://10.0.0.80/home-ca.crt), or pair from the display or the portal.",
                      str(caught.exception.code))

    def test_localai_default_ca_is_unchanged(self) -> None:
        self.assertEqual(configure.CA_PATH, Path.home() / ".claude" / "localai-chat" / "localai-ca.crt")
        self.assertEqual(configure.default_ca("localai"), configure.CA_PATH)
        self.assertIsNone(configure.default_ca("pihub"))

    def test_ca_must_be_a_pem_certificate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            good, bad = Path(td) / "ca.crt", Path(td) / "not.crt"
            good.write_text(PEM, encoding="ascii")
            bad.write_text("hello\n", encoding="ascii")
            self.assertEqual(configure.read_ca(good), PEM)
            with self.assertRaises(SystemExit):
                configure.read_ca(bad)
            with self.assertRaises(SystemExit):
                configure.read_ca(Path(td) / "missing.crt")
            # pihub with a bad --ca also stops before the display is contacted.
            with mock.patch.object(configure, "Client", side_effect=AssertionError("contacted the display")):
                with self.assertRaises(SystemExit):
                    run("--backend", "pihub", "--ca", str(bad))

    def test_missing_key_refuses_before_contacting_the_display(self) -> None:
        # 31 Oct 2026: the Keychain key is read before the display is contacted, like the CA.
        with tempfile.TemporaryDirectory() as td:
            ca = Path(td) / "home-ca.crt"
            ca.write_text(PEM, encoding="ascii")
            with mock.patch.object(configure, "Client", side_effect=AssertionError("contacted the display")), \
                 mock.patch.object(configure, "keychain_secret", lambda a, s: ""):
                with self.assertRaises(SystemExit) as caught:
                    run("--backend", "pihub", "--ca", str(ca))
            self.assertIn("no pihub display key in the Keychain (service pihub-display-key)", str(caught.exception.code))

    def test_pihub_with_ca_sends_it_and_the_backend(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ca = Path(td) / "home-ca.crt"
            ca.write_text(PEM, encoding="ascii")
            sent = {}

            class Reply:
                def __init__(self, status: int, body: str) -> None:
                    self.status, self.body = status, body

            class FakeClient:
                def __init__(self, base_url: str) -> None:
                    pass

                def request(self, path: str, method: str = "GET", form=None, headers=None):
                    if path == "/os12/localai/config":
                        sent.update(form or {})
                        return Reply(202, "{}")
                    return Reply(200, '{"lastSuccessAgoS": 1, "cards": []}')

            with mock.patch.object(configure, "Client", FakeClient), \
                 mock.patch.object(configure, "establish_portal_session", lambda c: None), \
                 mock.patch.object(configure, "keychain_secret", lambda a, s: "hubd_" + "a" * 32), \
                 mock.patch.object(configure.time, "sleep", lambda s: None):
                with mock.patch.object(sys, "argv", ["configure_localai_feed.py", "--backend", "pihub", "--ca", str(ca)]):
                    self.assertEqual(configure.main(), 0)
            self.assertEqual((sent["address"], sent["name"], sent["backend"], sent["ca"]), ("10.0.0.80", "home.home.arpa", "pihub", PEM))


if __name__ == "__main__":
    unittest.main()

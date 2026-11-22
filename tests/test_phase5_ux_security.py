"""Testes da Fase 5: gerenciador de API keys, revisao pre-render e seguranca do Web Studio."""

from __future__ import annotations

import http.client
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from core import config as core_config
from core.exceptions import PipelineCancelledError
from core.options import ProcessingOptions
from gui.review_dialog import format_clip_share_text


def _load_server_module():
    server_path = Path(__file__).resolve().parent.parent / "site" / "server.py"
    spec = importlib.util.spec_from_file_location("autocortes_site_server", server_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class TestPhase5ApiKeys(unittest.TestCase):
    def test_mask_api_key_hides_middle(self):
        masked = core_config.mask_api_key("AIzaSyABCDEF1234567890")
        self.assertIn("Google AI Studio", masked)
        self.assertIn("AIza", masked)
        self.assertIn("7890", masked)
        self.assertNotIn("ABCDEF", masked)

    def test_save_and_reload_api_keys_preserves_other_env_vars(self):
        orig_keys = list(core_config.API_KEYS)
        orig_env = os.environ.get("API_KEYS")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env_file = Path(tmp) / ".env"
                env_file.write_text("WHISPER_MODEL=turbo\nAPI_KEYS=old_key\n", encoding="utf-8")

                loaded = core_config.save_api_keys(["gsk_test1234567890"], dotenv_path=env_file)
                self.assertIn("gsk_test1234567890", loaded)
                self.assertIn("gsk_test1234567890", core_config.API_KEYS)

                content = env_file.read_text(encoding="utf-8")
                self.assertIn("WHISPER_MODEL=turbo", content)
                self.assertIn("API_KEYS=gsk_test1234567890", content)
                self.assertNotIn("old_key", content)
        finally:
            if orig_env is None:
                os.environ.pop("API_KEYS", None)
            else:
                os.environ["API_KEYS"] = orig_env
            core_config.API_KEYS[:] = orig_keys
            core_config.API_KEY = orig_keys[0] if orig_keys else ""


class TestPhase5ReviewAndShare(unittest.TestCase):
    def test_format_clip_share_text(self):
        text = format_clip_share_text(
            {"title": "Gol incrível", "description": "Veja o lance completo #shorts"}
        )
        self.assertEqual(text, "Gol incrível\n\nVeja o lance completo #shorts")

    def test_review_before_render_option_roundtrip(self):
        opts = ProcessingOptions(review_before_render=True)
        restored = ProcessingOptions.from_json(opts.to_json())
        self.assertTrue(restored.review_before_render)
        self.assertFalse(ProcessingOptions.from_dict({}).review_before_render)


class TestPhase5WebStudioSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv_mod = _load_server_module()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), cls.srv_mod.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _post(self, path: str, body: dict, headers: dict[str, str] | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        req_headers = {"Content-Type": "application/json", **(headers or {})}
        conn.request("POST", path, body=json.dumps(body).encode("utf-8"), headers=req_headers)
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return resp.status, data

    def test_cross_origin_post_is_blocked_with_403(self):
        status, _data = self._post(
            "/api/cancel",
            {},
            headers={"Origin": "http://evil.example"},
        )
        self.assertEqual(status, 403)

    def test_cross_site_sec_fetch_is_blocked_with_403(self):
        status, _data = self._post(
            "/api/cancel",
            {},
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        self.assertEqual(status, 403)

    def test_same_origin_cancel_returns_200(self):
        status, data = self._post(
            "/api/cancel",
            {},
            headers={"Origin": f"http://127.0.0.1:{self.port}"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(data, {"ok": False, "cancelling": False})

    def test_is_within_blocks_paths_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "allowed"
            root.mkdir()
            inside = root / "video.mp4"
            outside = Path(tmp) / "secret.txt"
            self.assertTrue(self.srv_mod._is_within(inside, (root,)))
            self.assertFalse(self.srv_mod._is_within(outside, (root,)))


if __name__ == "__main__":
    unittest.main()

import re
import subprocess
import sys
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from core.exceptions import NO_WINDOW_FLAGS, run_cmd, run_interruptible_cmd


class TestPhase1Base(unittest.TestCase):
    def test_requirements_declares_pillow(self):
        req_path = Path(__file__).resolve().parent.parent / "requirements.txt"
        lines = [
            line.strip().lower()
            for line in req_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        packages = [re.split(r"[<>=!~;\[\s]", line, maxsplit=1)[0] for line in lines]
        self.assertIn("pillow", packages)

    def test_run_cmd_passes_utf8_and_no_window_flags(self):
        fake = subprocess.CompletedProcess(args=["echo"], returncode=0, stdout="", stderr="")
        with patch("core.exceptions.subprocess.run", return_value=fake) as mock_run:
            result = run_cmd(["echo", "ok"], cwd=".", timeout=15)
        self.assertIs(result, fake)
        kwargs = mock_run.call_args.kwargs
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "replace")
        self.assertEqual(kwargs["timeout"], 15)
        self.assertEqual(kwargs["creationflags"], NO_WINDOW_FLAGS)

    def test_run_interruptible_cmd_passes_utf8_and_no_window_with_cancel_event(self):
        script = (
            "import sys; "
            "print('Vídeo ação ✓'); "
            "print('alerta çãõ', file=sys.stderr)"
        )
        cmd = [sys.executable, "-X", "utf8", "-c", script]

        res_sync = run_interruptible_cmd(cmd, cancel_event=None)
        self.assertEqual(res_sync.returncode, 0)
        self.assertIn("Vídeo ação ✓", res_sync.stdout)
        self.assertIn("alerta çãõ", res_sync.stderr)

        with patch("core.exceptions.subprocess.Popen", wraps=subprocess.Popen) as spy_popen:
            res_ev = run_interruptible_cmd(cmd, cancel_event=Event())
        self.assertEqual(res_ev.returncode, 0)
        self.assertIn("Vídeo ação ✓", res_ev.stdout)
        self.assertIn("alerta çãõ", res_ev.stderr)
        kwargs = spy_popen.call_args.kwargs
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "replace")
        self.assertEqual(kwargs["creationflags"], NO_WINDOW_FLAGS)


if __name__ == "__main__":
    unittest.main()

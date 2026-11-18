import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core import framing, video_ops
from core.captions.models import CaptionWord
from core.options import ProcessingOptions
from gui.settings_dialog import SettingsDialog
from utils.report import load_report, save_report


class TestPhase2Cuts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_follow_dynamic_transcribes_words_once_and_passes_to_framing(self):
        words = [
            CaptionWord(start=0.2, end=0.8, text="teste"),
            CaptionWord(start=0.9, end=2.8, text="dinamico"),
        ]
        captured = {}

        def fake_analyze(
            video_path,
            start,
            end,
            *,
            words=None,
            want_cam=False,
            cache_path=None,
            cache_key=None,
            dynamic=False,
        ):
            captured["words"] = words
            captured["dynamic"] = dynamic
            captured["cache_key"] = cache_key
            return framing.FramingPlan(src_width=1920, src_height=1080)

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "src.mp4"
            video.write_bytes(b"fake-video-content")
            out_mp4 = Path(tmp) / "out.mp4"
            clip = {"start": "00:00:05", "end": "00:00:35", "title": "Teste"}

            # 1) Legenda desligada + follow_dynamic: ainda extrai palavras para os beats
            opts_no_cap = ProcessingOptions(
                layout_id="follow_dynamic",
                captions_enabled=False,
                caption_transcribe_mode="clip",
            )
            with (
                patch("core.video_ops._transcribe_clip_words", return_value=words) as m_trans,
                patch("core.framing.analyze_clip", side_effect=fake_analyze),
                patch("core.render.render_clip", return_value=str(out_mp4)) as m_render,
            ):
                res = video_ops._process_vertical(
                    str(video), clip, 60.0, str(out_mp4), opts_no_cap, None, 1
                )
            self.assertEqual(res, str(out_mp4))
            m_trans.assert_called_once()
            self.assertEqual(captured["words"], words)
            self.assertTrue(captured["dynamic"])
            self.assertTrue(captured["cache_key"]["has_words"])
            self.assertIsNone(m_render.call_args.kwargs.get("ass_path"))

            # 2) Legenda ligada + follow_dynamic: reutiliza as mesmas palavras sem duplicar
            opts_with_cap = ProcessingOptions(
                layout_id="follow_dynamic",
                captions_enabled=True,
                caption_transcribe_mode="clip",
            )
            with (
                patch("core.video_ops._transcribe_clip_words", return_value=words) as m_trans2,
                patch("core.framing.analyze_clip", side_effect=fake_analyze),
                patch("core.render.render_clip", return_value=str(out_mp4)) as m_render2,
            ):
                video_ops._process_vertical(
                    str(video), clip, 60.0, str(out_mp4), opts_with_cap, None, 1
                )
            m_trans2.assert_called_once()
            self.assertIsNotNone(m_render2.call_args.kwargs.get("ass_path"))

    def test_framing_cache_invalidates_when_has_words_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "framing_001.json"
            stale_payload = {
                "key": {
                    "algo": framing.ALGO_VERSION,
                    "want_cam": False,
                    "dynamic": True,
                    "has_words": False,
                },
                "plan": framing.FramingPlan(src_width=640, src_height=360).to_dict(),
            }
            cache_file.write_text(json.dumps(stale_payload), encoding="utf-8")

            with (
                patch("core.framing.probe_size", return_value=(1920, 1080)),
                patch("core.framing.read_frames", return_value=([], 320, 180)),
            ):
                plan = framing.analyze_clip(
                    "nao_existe.mp4",
                    0.0,
                    10.0,
                    words=[CaptionWord(0.1, 0.5, "oi")],
                    dynamic=True,
                    cache_path=cache_file,
                )

            # Nao usou o cache antigo (640x360), recalculou com probe_size (1920x1080)
            self.assertEqual((plan.src_width, plan.src_height), (1920, 1080))
            updated = json.loads(cache_file.read_text(encoding="utf-8"))
            self.assertTrue(updated["key"]["has_words"])

    def test_cut_all_records_effective_cut_window_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "proj"
            video = Path(tmp) / "vid.mp4"
            video.write_bytes(b"0000")
            clips = [
                {
                    "start": "00:00:10",
                    "end": "00:00:40",
                    "hook": "00:00:12",
                    "viral_score": 9,
                    "title": "Corte Janela",
                }
            ]
            opts = ProcessingOptions(vertical_enabled=False, padding_s=2.0)

            with patch(
                "core.video_ops._process_copy",
                side_effect=lambda _v, _c, _d, out, *_a: out,
            ):
                paths = video_ops.cut_all(
                    str(video),
                    clips,
                    total_duration=100.0,
                    output_dir=str(out_dir),
                    vertical=False,
                    options=opts,
                )

            self.assertEqual(clips[0]["cut_start"], "00:00:08")
            self.assertEqual(clips[0]["cut_end"], "00:00:42")
            self.assertAlmostEqual(clips[0]["cut_duration_s"], 34.0)

            rep_path = save_report(clips, out_dir, paths)
            loaded = load_report(rep_path)
            self.assertEqual(loaded[0]["cut_start"], "00:00:08")
            self.assertEqual(loaded[0]["cut_end"], "00:00:42")
            csv_text = (out_dir / "relatorio.csv").read_text(encoding="utf-8")
            self.assertIn("cut_start", csv_text)
            self.assertIn("00:00:08", csv_text)

    def test_settings_dialog_toggles_margin_hint_for_multislot_layouts(self):
        dialog = SettingsDialog(ProcessingOptions(layout_id="center"), embedded=True)
        self.assertTrue(dialog.caption_margin_bottom.isEnabled())
        self.assertEqual(dialog.caption_margin_hint.text(), "px")

        dialog._on_layout_selected("title_middle")
        self.assertFalse(dialog.caption_margin_bottom.isEnabled())
        self.assertEqual(dialog.caption_margin_hint.text(), "Fixo pelo formato")

        dialog._on_layout_selected("follow_dynamic")
        self.assertTrue(dialog.caption_margin_bottom.isEnabled())
        self.assertEqual(dialog.caption_margin_hint.text(), "px")


if __name__ == "__main__":
    unittest.main()

"""Testes de integracao ponta a ponta do pipeline (com mocks leves de midia/IA)."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core import pipeline
from core.exceptions import PipelineCancelledError
from core.options import ProcessingOptions


class TestPipelineIntegration(unittest.TestCase):
    def _run_mocked_pipeline(
        self,
        tmp_dir: Path,
        *,
        options: ProcessingOptions | None = None,
        review_callback=None,
        cancel_event: threading.Event | None = None,
        force: bool = False,
    ):
        video = tmp_dir / "podcast.mp4"
        if not video.exists():
            video.write_bytes(b"fake-mp4-data")
        out_root = tmp_dir / "output"

        fake_segments = [
            SimpleNamespace(start=0.0, end=15.0, text="Introdução forte do episódio.", words=[]),
            SimpleNamespace(start=16.0, end=42.0, text="História viral completa com clímax.", words=[]),
            SimpleNamespace(start=44.0, end=75.0, text="Segunda história marcante.", words=[]),
        ]
        fake_clips = [
            {
                "title": "Corte 1",
                "start": "00:00:00",
                "end": "00:00:42",
                "viral_score": 9,
                "reason": "Gancho forte",
                "description": "Descrição 1",
            },
            {
                "title": "Corte 2",
                "start": "00:00:44",
                "end": "00:01:15",
                "viral_score": 8,
                "reason": "Bom fechamento",
                "description": "Descrição 2",
            },
        ]

        def fake_cut_all(_vp, clips, _total_duration, out_dir, *_args, **_kwargs):
            paths = []
            for idx, _c in enumerate(clips, 1):
                p = Path(out_dir) / f"corte_{idx:02d}.mp4"
                p.write_bytes(b"fake-cut")
                paths.append(str(p))
            return paths

        with (
            mock.patch.object(pipeline.audio, "extract_audio", return_value=str(tmp_dir / "a.wav")),
            mock.patch.object(pipeline.transcriber, "transcribe", return_value=fake_segments),
            mock.patch.object(pipeline.ai_analyzer, "analyze", return_value=fake_clips) as analyze_mock,
            mock.patch.object(pipeline.video_ops, "get_duration", return_value=120.0),
            mock.patch.object(pipeline.video_ops, "cut_all", side_effect=fake_cut_all) as cut_mock,
        ):
            result = pipeline.run(
                video_path=str(video),
                output_dir=str(out_root),
                options=options or ProcessingOptions(min_clip_duration=20, max_clip_duration=60),
                review_callback=review_callback,
                cancel_event=cancel_event,
                force=force,
            )
        return result, analyze_mock, cut_mock, out_root

    def test_full_pipeline_creates_clips_report_and_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, analyze_mock, cut_mock, out_root = self._run_mocked_pipeline(Path(tmp))
            self.assertEqual(analyze_mock.call_count, 1)
            self.assertEqual(cut_mock.call_count, 1)
            self.assertEqual(len(result["clip_paths"]), 2)
            report_file = Path(result["report_path"])
            self.assertTrue(report_file.is_file())
            report_data = json.loads(report_file.read_text(encoding="utf-8"))
            self.assertEqual(len(report_data), 2)

            # Segunda execucao reaproveita cache de analise de IA (0 novas chamadas)
            result2, analyze_mock2, _cut2, _out2 = self._run_mocked_pipeline(Path(tmp))
            self.assertEqual(analyze_mock2.call_count, 0)
            self.assertEqual(len(result2["clip_paths"]), 2)

    def test_pipeline_review_callback_filters_and_adjusts_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            def approve_only_first(clips):
                first = dict(clips[0])
                first["start"] = "00:00:02"
                first["end"] = "00:00:38"
                return [first]

            opts = ProcessingOptions(
                min_clip_duration=20,
                max_clip_duration=60,
                review_before_render=True,
            )
            result, _analyze, cut_mock, _out = self._run_mocked_pipeline(
                Path(tmp),
                options=opts,
                review_callback=approve_only_first,
            )
            self.assertEqual(len(result["clips"]), 1)
            self.assertEqual(result["clips"][0]["start"], "00:00:02")
            self.assertEqual(result["clips"][0]["end"], "00:00:38")
            self.assertEqual(len(cut_mock.call_args.args[1]), 1)

    def test_pipeline_review_callback_empty_raises_cancelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            opts = ProcessingOptions(review_before_render=True)
            with self.assertRaises(PipelineCancelledError):
                self._run_mocked_pipeline(
                    Path(tmp),
                    options=opts,
                    review_callback=lambda _clips: [],
                )

    def test_pipeline_respects_cancel_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = threading.Event()
            ev.set()
            with self.assertRaises(PipelineCancelledError):
                self._run_mocked_pipeline(Path(tmp), cancel_event=ev)


if __name__ == "__main__":
    unittest.main()

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core import config, framing, layouts, render, transcriber, video_ops
from core.captions.models import CaptionWord
from core.dynamic_zoom import ZoomBeat
from core.options import ProcessingOptions


class TestPhase3PerfAndRender(unittest.TestCase):
    def test_default_whisper_model_picks_cuda_or_turbo(self):
        with patch.dict(os.environ, {"WHISPER_MODEL": ""}, clear=False):
            fake_ct2_gpu = SimpleNamespace(get_cuda_device_count=lambda: 1)
            with patch.dict(sys.modules, {"ctranslate2": fake_ct2_gpu}):
                self.assertEqual(config.default_whisper_model(), "large")

            fake_ct2_cpu = SimpleNamespace(get_cuda_device_count=lambda: 0)
            with patch.dict(sys.modules, {"ctranslate2": fake_ct2_cpu}):
                self.assertEqual(config.default_whisper_model(), "turbo")

        with patch.dict(os.environ, {"WHISPER_MODEL": "medium"}, clear=False):
            self.assertEqual(config.default_whisper_model(), "medium")

    def test_transcribe_enables_vad_and_emits_granular_progress(self):
        fake_segs = [
            SimpleNamespace(start=0.0, end=2.5, text="um", words=[]),
            SimpleNamespace(start=2.5, end=5.0, text="dois", words=[]),
            SimpleNamespace(start=5.0, end=10.0, text="tres", words=[]),
        ]
        fake_info = SimpleNamespace(duration=10.0)
        fake_model = MagicMock()
        fake_model.transcribe.return_value = (iter(fake_segs), fake_info)

        fractions = []
        with patch("core.transcriber.get_model", return_value=fake_model):
            out = transcriber.transcribe(
                "audio.wav",
                progress_callback=fractions.append,
            )

        self.assertEqual(len(out), 3)
        kwargs = fake_model.transcribe.call_args.kwargs
        self.assertTrue(kwargs["vad_filter"])
        self.assertEqual(
            kwargs["vad_parameters"],
            {"min_silence_duration_ms": 500, "speech_pad_ms": 200},
        )
        self.assertEqual(fractions, [0.25, 0.5, 1.0])

    def test_probe_video_info_parses_fractional_fps(self):
        payload = json.dumps(
            {
                "streams": [
                    {
                        "width": 1920,
                        "height": 1080,
                        "avg_frame_rate": "60000/1001",
                        "r_frame_rate": "60/1",
                    }
                ]
            }
        )
        fake_proc = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout=payload, stderr=""
        )
        with (
            patch("core.framing.shutil.which", return_value="ffprobe"),
            patch("core.framing.subprocess.run", return_value=fake_proc),
        ):
            w, h, fps = framing.probe_video_info("clip.mp4")

        self.assertEqual((w, h), (1920, 1080))
        self.assertAlmostEqual(fps, 60000 / 1001, places=3)

    def test_build_layout_filter_propagates_src_fps_to_slots_and_sendcmd(self):
        lay = layouts.get_layout("title_middle")
        heights = layouts.slot_heights(lay, 1920)
        flt = render.build_layout_filter(
            lay,
            heights,
            width=1080,
            options=ProcessingOptions(),
            src_size=(1920, 1080),
            src_fps=60.0,
        )
        self.assertIn("r=60", flt)

        plan = framing.FramingPlan(
            src_width=1920,
            src_height=1080,
            src_fps=60.0,
            shots=[framing.FocusShot(0.0, 4.0, 0.5, 0.4, 0.2)],
            beats=[ZoomBeat(0.5, 2.5, 3.5, 1.2, (0.5, 0.4, 0.15, 0.2), [])],
        )
        with tempfile.TemporaryDirectory() as tmp:
            lay_dyn = layouts.get_layout("follow_dynamic")
            render.build_layout_filter(
                lay_dyn,
                layouts.slot_heights(lay_dyn, 1920),
                width=1080,
                options=ProcessingOptions(),
                plan=plan,
                src_size=(1920, 1080),
                work_dir=tmp,
                src_fps=60.0,
            )
            cmd_lines = (Path(tmp) / "zoom_s0.cmd").read_text(encoding="utf-8").splitlines()
            # 60 fps -> passo ~0.0167s entre linhas de sendcmd
            times = [float(line.split()[0]) for line in cmd_lines]
            self.assertTrue(len(times) > 10)
            deltas = [b - a for a, b in zip(times, times[1:]) if 0.55 <= a <= 2.4]
            self.assertTrue(deltas)
            self.assertLess(min(deltas), 0.025)

    def test_loudnorm_filter_and_audio_normalize_option(self):
        self.assertIn(
            render.LOUDNORM_FILTER,
            render.build_music_filter(1, 0.2, True, normalize=True),
        )
        self.assertNotIn(
            render.LOUDNORM_FILTER,
            render.build_music_filter(1, 0.2, True, normalize=False),
        )

        captured_cmds = []

        def fake_run(cmd, **_kwargs):
            captured_cmds.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "in.mp4"
            video.write_bytes(b"00")
            out = Path(tmp) / "out.mp4"
            with (
                patch("core.render._require_ffmpeg", return_value="ffmpeg"),
                patch("core.render.detect_encoder", return_value="libx264"),
                patch("core.render._probe_has_audio", return_value=True),
                patch("core.render._probe_video_info", return_value=(1920, 1080, 30.0)),
                patch("core.render.run_interruptible_cmd", side_effect=fake_run),
            ):
                render.render_clip(
                    str(video),
                    0.0,
                    5.0,
                    str(out),
                    options=ProcessingOptions(audio_normalize=True),
                )
                render.render_clip(
                    str(video),
                    0.0,
                    5.0,
                    str(out),
                    options=ProcessingOptions(audio_normalize=False),
                )

        flt_on = captured_cmds[0][captured_cmds[0].index("-filter_complex") + 1]
        flt_off = captured_cmds[1][captured_cmds[1].index("-filter_complex") + 1]
        self.assertIn(render.LOUDNORM_FILTER, flt_on)
        self.assertNotIn(render.LOUDNORM_FILTER, flt_off)

    def test_caption_assets_do_not_copy_all_bundled_fonts(self):
        with tempfile.TemporaryDirectory() as tmp_ass, tempfile.TemporaryDirectory() as tmp_work:
            opts = ProcessingOptions(
                captions_enabled=True, caption_font="Poppins", caption_italic=False
            )
            ass_path = video_ops._write_clip_captions(
                [CaptionWord(0.0, 0.5, "ola")], opts, tmp_ass
            )
            # _write_clip_captions nao copia todas as fontes para tmp_ass
            self.assertEqual(os.listdir(tmp_ass), ["captions.ass"])

            render._copy_caption_assets(ass_path, opts, tmp_work)
            copied_fonts = [
                f for f in os.listdir(tmp_work) if f.lower().endswith((".ttf", ".otf"))
            ]
            self.assertEqual(len(copied_fonts), 1)
            self.assertIn("Poppins", copied_fonts[0])

    def test_auto_encoder_falls_back_to_libx264_on_failure(self):
        cmds = []
        warnings = []

        def fake_run(cmd, **_kwargs):
            cmds.append(cmd)
            if "h264_nvenc" in cmd:
                return subprocess.CompletedProcess(cmd, 1, "", "NVENC session limit")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "in.mp4"
            video.write_bytes(b"00")
            out = Path(tmp) / "out.mp4"
            with (
                patch("core.render._require_ffmpeg", return_value="ffmpeg"),
                patch("core.render.detect_encoder", return_value="h264_nvenc"),
                patch("core.render._probe_has_audio", return_value=False),
                patch("core.render._probe_video_info", return_value=(1920, 1080, 30.0)),
                patch("core.render.run_interruptible_cmd", side_effect=fake_run),
            ):
                render.render_clip(
                    str(video),
                    0.0,
                    5.0,
                    str(out),
                    options=ProcessingOptions(encoder=""),
                    warn_callback=warnings.append,
                )

            self.assertEqual(len(cmds), 2)
            self.assertIn("h264_nvenc", cmds[0])
            self.assertIn("libx264", cmds[1])
            self.assertEqual(len(warnings), 1)
            self.assertIn("libx264", warnings[0])

            # Se o usuario forcou o encoder manualmente, nao faz fallback silencioso
            cmds.clear()
            with (
                patch("core.render._require_ffmpeg", return_value="ffmpeg"),
                patch("core.render.detect_encoder", return_value="h264_nvenc"),
                patch("core.render._probe_has_audio", return_value=False),
                patch("core.render._probe_video_info", return_value=(1920, 1080, 30.0)),
                patch("core.render.run_interruptible_cmd", side_effect=fake_run),
            ):
                with self.assertRaises(RuntimeError):
                    render.render_clip(
                        str(video),
                        0.0,
                        5.0,
                        str(out),
                        options=ProcessingOptions(encoder="h264_nvenc"),
                    )
            self.assertEqual(len(cmds), 1)


if __name__ == "__main__":
    unittest.main()

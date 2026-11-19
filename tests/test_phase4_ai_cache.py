import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import ai_analyzer, cache, config, downloader
from core.providers import factory
from core.transcriber import Segment


class TestPhase4AICatalogChunkingCache(unittest.TestCase):
    def test_google_catalog_has_real_active_models(self):
        models = config.PROVIDERS_CATALOG["google"]["models"]
        self.assertEqual(models[0], "gemini-2.5-flash")
        for bad in ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.7-flash"):
            self.assertNotIn(bad, models)

    def test_resolve_targets_filters_models_with_session_cache(self):
        factory.reset_live_models_cache()
        calls = []

        def fake_fetch(self, api_key, base_url=None, client=None):
            calls.append((self.provider_id, base_url))
            return ("gemini-2.5-flash-lite",)

        with patch.object(factory.GeminiProvider, "fetch_models", fake_fetch):
            t1 = factory.resolve_targets(
                ["AIzaSyKeyOne"], models_override=[], base_url_override=""
            )
            t2 = factory.resolve_targets(
                ["AIzaSyKeyTwo"], models_override=[], base_url_override=""
            )

        self.assertEqual(t1[0].models, ("gemini-2.5-flash-lite",))
        self.assertEqual(t2[0].models, ("gemini-2.5-flash-lite",))
        self.assertEqual(len(calls), 1)
        factory.reset_live_models_cache()

    def test_split_segments_into_chunks_handles_short_and_long_videos(self):
        short_segs = [
            Segment(start=i * 10.0, end=(i + 1) * 10.0, text=f"fala {i}")
            for i in range(10)
        ]
        self.assertEqual(len(ai_analyzer.split_segments_into_chunks(short_segs)), 1)

        # 2 horas (7200s) com pausas de 2s a cada 60s
        long_segs = []
        t = 0.0
        for i in range(120):
            long_segs.append(Segment(start=t, end=t + 58.0, text=f"trecho {i} " * 5))
            t += 60.0
        chunks = ai_analyzer.split_segments_into_chunks(
            long_segs, max_duration_s=2100.0, overlap_s=120.0, pause_gap=1.5
        )
        self.assertGreaterEqual(len(chunks), 3)
        # Verifica overlap entre janelas consecutivas
        for prev, nxt in zip(chunks, chunks[1:]):
            self.assertLess(nxt[0].start, prev[-1].end)

    def test_analyze_merges_and_dedupes_multi_chunk_results(self):
        long_segs = [
            Segment(start=i * 60.0, end=i * 60.0 + 58.0, text=f"segmento {i}")
            for i in range(90)
        ]
        chunk_outputs = [
            [
                {"start": "00:05:00", "end": "00:05:45", "hook": "00:05:00", "viral_score": 8, "title": "A"},
                {"start": "00:34:00", "end": "00:34:45", "hook": "00:34:00", "viral_score": 8, "title": "Fronteira baixa"},
            ],
            [
                {"start": "00:34:05", "end": "00:34:50", "hook": "00:34:05", "viral_score": 10, "title": "Fronteira alta"},
                {"start": "01:05:00", "end": "01:05:40", "hook": "01:05:00", "viral_score": 9, "title": "B"},
            ],
            [
                {"start": "01:20:00", "end": "01:20:40", "hook": "01:20:00", "viral_score": 9, "title": "C"},
            ],
        ]
        it = iter(chunk_outputs)

        with (
            patch("core.ai_analyzer._resolve_targets", return_value=[ai_analyzer.KeyTarget("groq", "Groq", "gsk_x", "https://x", ("m",))]),
            patch("core.ai_analyzer._analyze_single_block", side_effect=lambda *a, **k: next(it)),
        ):
            clips = ai_analyzer.analyze(long_segs, api_keys=["gsk_x"], max_clips=10)

        titles = [c["title"] for c in clips]
        self.assertIn("Fronteira alta", titles)
        self.assertNotIn("Fronteira baixa", titles)
        self.assertEqual(clips[0]["viral_score"], 10)
        self.assertEqual(len(clips), 4)

    def test_window_hash_and_analysis_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "proj"
            video = Path(tmp) / "src.mp4"
            video.write_bytes(b"video-bytes-12345")

            h1 = cache.window_hash(str(video), 10.0, 45.0)
            h2 = cache.window_hash(str(video), 10.0, 45.0)
            h3 = cache.window_hash(str(video), 11.0, 45.0)
            self.assertEqual(h1, h2)
            self.assertNotEqual(h1, h3)
            self.assertTrue(
                cache.clip_transcript_path(out_dir / ".cache", h1).name.endswith(f"{h1}.json")
            )
            self.assertTrue(
                cache.framing_cache_path(out_dir / ".cache", h1).name.endswith(f"{h1}.json")
            )

            tkey = cache.make_key(str(video), "turbo", "pt", "auto")
            akey = cache.make_analysis_key(
                tkey, focus="", max_clips=10, min_viral_score=8,
                min_clip_duration=30, max_clip_duration=90,
            )
            clips = [{"start": "00:00:10", "end": "00:00:45", "viral_score": 9}]
            cache.save_analysis(out_dir, akey, clips)
            self.assertEqual(cache.load_analysis(out_dir, akey), clips)

            akey_other_focus = cache.make_analysis_key(
                tkey, focus="engraçado", max_clips=10, min_viral_score=8,
                min_clip_duration=30, max_clip_duration=90,
            )
            self.assertIsNone(cache.load_analysis(out_dir, akey_other_focus))

    def test_downloader_reuses_existing_video_by_id(self):
        self.assertEqual(
            downloader._extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            downloader._extract_youtube_id("https://youtu.be/dQw4w9WgXcQ?t=12"),
            "dQw4w9WgXcQ",
        )
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "Meu Video.dQw4w9WgXcQ.mp4"
            existing.write_bytes(b"mp4-content")
            with patch("core.downloader.yt_dlp.YoutubeDL") as mock_ydl:
                got = downloader.download_video(
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    diretorio_saida=tmp,
                )
            self.assertEqual(got, str(existing))
            mock_ydl.assert_not_called()


if __name__ == "__main__":
    unittest.main()

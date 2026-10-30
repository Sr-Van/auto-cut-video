import tempfile
import unittest
from pathlib import Path

from core import cache
from core.transcriber import Segment, Word


class TestCache(unittest.TestCase):
    def test_save_and_load_transcript_hit_and_miss(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            video_file = tmp_path / "sample.mp4"
            video_file.write_bytes(b"fake video binary data " * 64)

            key = cache.make_key(
                str(video_file),
                whisper_model="large",
                language="pt",
                compute_type="auto",
                word_timestamps=True,
            )

            segments = [
                Segment(
                    id="S0001",
                    start=0.0,
                    end=2.5,
                    text="Olá mundo",
                    words=[
                        Word(start=0.0, end=1.0, text="Olá"),
                        Word(start=1.1, end=2.5, text="mundo"),
                    ],
                )
            ]

            cache.save_transcript(tmp_path, key, segments)

            loaded = cache.load_transcript(tmp_path, key)
            self.assertIsNotNone(loaded)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].text, "Olá mundo")
            self.assertEqual(len(loaded[0].words), 2)
            self.assertEqual(loaded[0].words[0].text, "Olá")

            # Miss quando modelo ou parametro diverge
            wrong_key = cache.make_key(
                str(video_file),
                whisper_model="small",
                language="pt",
                compute_type="auto",
                word_timestamps=True,
            )
            self.assertIsNone(cache.load_transcript(tmp_path, wrong_key))

    def test_clip_key_includes_window(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_file = Path(tmp_dir) / "clip_src.mp4"
            video_file.write_bytes(b"0123456789")
            clip_key = cache.make_clip_key(
                str(video_file),
                12.3456,
                45.6789,
                "large",
                "pt",
                "auto",
            )
            self.assertEqual(clip_key["window"], [12.346, 45.679])
            self.assertTrue(clip_key["word_timestamps"])


if __name__ == "__main__":
    unittest.main()


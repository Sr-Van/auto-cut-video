import unittest
from dataclasses import dataclass

from utils.normalize import compute_cut_points, normalize_clips


@dataclass
class _DummySeg:
    start: float
    end: float
    text: str = ""


class TestNormalize(unittest.TestCase):
    def test_compute_cut_points_identifies_pauses(self):
        segments = [
            _DummySeg(0.0, 10.0),
            _DummySeg(10.5, 20.0),  # gap 0.5 < 1.5
            _DummySeg(22.0, 30.0),  # gap 2.0 >= 1.5 -> midpoint 21.0
        ]
        points = compute_cut_points(segments, total_duration=40.0, pause_gap=1.5)
        self.assertEqual(points, [0.0, 21.0, 40.0])

    def test_normalize_expands_short_clip_to_min_duration(self):
        segments = [_DummySeg(0.0, 30.0), _DummySeg(32.0, 60.0)]
        clips = [
            {
                "start": "00:00:10",
                "end": "00:00:15",
                "hook": "00:00:12",
                "viral_score": 9,
                "title": "Curto",
            }
        ]
        result = normalize_clips(
            clips,
            segments,
            total_duration=60.0,
            min_duration=30,
            max_duration=50,
            pause_gap=1.5,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["start"], "00:00:00")
        # Snap near 31.0 (midpoint between 30 and 32)
        self.assertEqual(result[0]["end"], "00:00:31")

    def test_normalize_merges_overlapping_clips_keeping_higher_score(self):
        segments = [_DummySeg(0.0, 100.0)]
        clips = [
            {
                "start": "00:00:10",
                "end": "00:00:45",
                "hook": "00:00:15",
                "viral_score": 8,
                "title": "Corte Nota 8",
            },
            {
                "start": "00:00:30",
                "end": "00:01:05",
                "hook": "00:00:35",
                "viral_score": 10,
                "title": "Corte Nota 10",
            },
        ]
        result = normalize_clips(
            clips,
            segments,
            total_duration=120.0,
            min_duration=30,
            max_duration=60,
            pause_gap=1.5,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["viral_score"], 10)
        self.assertEqual(result[0]["title"], "Corte Nota 10")
        self.assertEqual(result[0]["start"], "00:00:10")


if __name__ == "__main__":
    unittest.main()


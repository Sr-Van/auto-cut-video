import unittest

from utils.timefmt import clamp_seconds, hhmmss_to_seconds, seconds_to_hhmmss


class TestTimeFmt(unittest.TestCase):
    def test_seconds_to_hhmmss_basic(self):
        self.assertEqual(seconds_to_hhmmss(0), "00:00:00")
        self.assertEqual(seconds_to_hhmmss(59.4), "00:00:59")
        self.assertEqual(seconds_to_hhmmss(59.6), "00:01:00")
        self.assertEqual(seconds_to_hhmmss(3661.5), "01:01:02")

    def test_hhmmss_to_seconds_three_parts(self):
        self.assertEqual(hhmmss_to_seconds("00:00:00"), 0)
        self.assertEqual(hhmmss_to_seconds("01:01:02"), 3662)
        self.assertEqual(hhmmss_to_seconds("  00:02:30  "), 150)

    def test_hhmmss_to_seconds_two_parts(self):
        self.assertEqual(hhmmss_to_seconds("02:03"), 123)
        self.assertEqual(hhmmss_to_seconds("10:00"), 600)

    def test_hhmmss_to_seconds_invalid_raises(self):
        with self.assertRaises(ValueError):
            hhmmss_to_seconds("12")
        with self.assertRaises(ValueError):
            hhmmss_to_seconds("01:02:03:04")

    def test_clamp_seconds(self):
        self.assertEqual(clamp_seconds(-5.0, 100.0), 0.0)
        self.assertEqual(clamp_seconds(42.5, 100.0), 42.5)
        self.assertEqual(clamp_seconds(150.0, 100.0), 100.0)


if __name__ == "__main__":
    unittest.main()


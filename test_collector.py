import unittest
from unittest.mock import patch

from collector import INTERVAL_MS, as_ms, collect, validate


class CollectorTests(unittest.TestCase):
    def test_utc_boundary(self):
        self.assertEqual(as_ms("2024-01-01T00:00:00Z") % INTERVAL_MS, 0)
        with self.assertRaises(ValueError):
            as_ms("2024-01-01T00:00:00")

    def test_valid_candle(self):
        row = [0, "10", "12", "9", "11", "100"]
        self.assertEqual(len(validate([row], "BTCUSDT", 0, INTERVAL_MS)), 1)

    def test_gap_and_duplicate(self):
        row = [0, "10", "12", "9", "11", "100"]
        with self.assertRaises(ValueError):
            validate([row, row], "BTCUSDT", 0, 2 * INTERVAL_MS)
        with self.assertRaises(ValueError):
            validate([row], "BTCUSDT", 0, 2 * INTERVAL_MS)

    def test_no_open_candle(self):
        with patch("collector.download") as fetch:
            with self.assertRaises(ValueError):
                collect("BTCUSDT", 0, 2**60, __import__("pathlib").Path("unused"))
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()

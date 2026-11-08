import unittest
from unittest.mock import patch

from collector import INTERVAL_MS, as_ms, collect, download, validate


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

    def test_coinbase_candles_order_and_pair_separation(self):
        import io
        import json
        payload = {"candles": [
            {"start": str(INTERVAL_MS // 1000), "low": "10", "high": "14", "open": "11", "close": "13", "volume": "5"},
            {"start": "0", "low": "9", "high": "12", "open": "10", "close": "11", "volume": "4"},
        ]}
        response = io.BytesIO(json.dumps(payload).encode())
        with patch("collector.urllib.request.urlopen", return_value=response) as request:
            rows = download("BTC-USD", 0, 2 * INTERVAL_MS, "coinbase")
        self.assertEqual([row[0] for row in rows], [0, INTERVAL_MS])
        self.assertEqual(len(validate(rows, "BTC-USD", 0, 2 * INTERVAL_MS, "coinbase")), 2)
        self.assertIn("FOUR_HOUR", request.call_args[0][0].full_url)
        with self.assertRaises(ValueError):
            validate(rows, "BTC-USD", 0, 2 * INTERVAL_MS, "binance")

    def test_coinbase_invalid_payload_fails_closed(self):
        import io
        with patch("collector.urllib.request.urlopen", return_value=io.BytesIO(b'{"message":"error"}')):
            with self.assertRaises(ValueError):
                download("SOL-USD", 0, INTERVAL_MS, "coinbase")


if __name__ == "__main__":
    unittest.main()

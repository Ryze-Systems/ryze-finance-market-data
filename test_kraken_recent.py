"""Fail-closed public Kraken 4h spot collector tests."""

import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import kraken_recent
from collector import INTERVAL_MS


def payload(count=26, broken=False):
    rows = []
    for index in range(count):
        second = 1_728_000_000 + index * 14_400 + (14_400 if broken and index == 8 else 0)
        rows.append([second, "100", "105", "95", "101", "100", "5", 12])
    return {"error": [], "result": {"XXBTZUSD": rows, "last": 123}}


class KrakenRecentTests(unittest.TestCase):
    def test_parses_recent_closed_only(self):
        response = payload()
        boundary = (1_728_000_000 + 25 * 14_400) * 1000
        parsed = kraken_recent.parse(response, symbol="BTC-USD", closed_at_ms=boundary)
        self.assertEqual(len(parsed), 25)
        self.assertEqual(parsed[0]["provider"], "kraken_spot")
        self.assertEqual(parsed[0]["symbol"], "BTC-USD")

    def test_refuses_gap(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            kraken_recent.parse(payload(broken=True), symbol="BTC-USD", closed_at_ms=1_900_000_000_000)

    def test_refuses_exchange_error(self):
        response = payload()
        response["error"] = ["Rate limit exceeded"]
        with self.assertRaises(ValueError):
            kraken_recent.parse(response, symbol="BTC-USD", closed_at_ms=1_900_000_000_000)

    def test_refuses_invalid_values_and_timestamp(self):
        response = payload()
        response["result"]["XXBTZUSD"][0][3] = "not-a-number"
        with self.assertRaises(ValueError):
            kraken_recent.parse(response, symbol="BTC-USD", closed_at_ms=1_900_000_000_000)
        response = payload()
        response["result"]["XXBTZUSD"][0][0] = "bad"
        with self.assertRaisesRegex(ValueError, "timestamp"):
            kraken_recent.parse(response, symbol="BTC-USD", closed_at_ms=1_900_000_000_000)

    def test_refuses_unknown_pair_and_short_history(self):
        with self.assertRaises(ValueError):
            kraken_recent.parse(payload(), symbol="DOGE-USD", closed_at_ms=1_900_000_000_000)
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            kraken_recent.parse(payload(count=6), symbol="BTC-USD", closed_at_ms=1_900_000_000_000)

    def test_collect_writes_immutable_checksums_and_retries(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self, *_):
                return json.dumps(payload()).encode()

        with tempfile.TemporaryDirectory() as tmp:
            with patch("kraken_recent.urllib.request.urlopen", return_value=Response()) as mocked:
                files = kraken_recent.collect(pathlib.Path(tmp), as_of_ms=1_900_000_000_000)
                files2 = kraken_recent.collect(pathlib.Path(tmp), as_of_ms=1_900_000_000_000)
            self.assertEqual(files, files2)
            self.assertEqual(len(files), 3)
            self.assertEqual(mocked.call_count, 6)
            self.assertIn("pair=XBTUSD", mocked.call_args_list[0].args[0].full_url)
            for path in files:
                self.assertTrue(path.with_suffix(".sha256").is_file())
                lines = path.read_text().splitlines()
                self.assertEqual(len(lines), 26)
                self.assertEqual(json.loads(lines[-1])["open_ms"] - json.loads(lines[0])["open_ms"], 25 * INTERVAL_MS)


if __name__ == "__main__":
    unittest.main()

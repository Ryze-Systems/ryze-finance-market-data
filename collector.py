"""Public market data only. No broker accounts, strategies or execution."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import time
import urllib.parse
import urllib.request

BASE_URL = "https://api.binance.com/api/v3/klines"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
INTERVAL_MS = 4 * 60 * 60 * 1000


def as_ms(value: str) -> int:
    timestamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("UTC timezone is required")
    return int(timestamp.timestamp() * 1000)


def validate(rows: list, symbol: str, start_ms: int, end_ms: int) -> list[dict]:
    """Validate closed UTC 4-hour candles; fail on gaps or malformed OHLCV."""
    if symbol not in SYMBOLS or start_ms % INTERVAL_MS or end_ms % INTERVAL_MS:
        raise ValueError("Invalid symbol or UTC candle boundaries")
    if start_ms >= end_ms:
        raise ValueError("Empty time range")
    expected = start_ms
    cleaned = []
    for candle in rows:
        if len(candle) < 6 or type(candle[0]) is not int:
            raise ValueError("Malformed candle")
        at = candle[0]
        if at != expected:
            raise ValueError(f"Gap or duplicate at {expected}: found {at}")
        o, h, l, c, v = map(float, candle[1:6])
        if not (0 < l <= min(o, c) <= max(o, c) <= h and v >= 0):
            raise ValueError("Inconsistent OHLCV")
        cleaned.append({"symbol": symbol, "open_ms": at, "open": candle[1], "high": candle[2], "low": candle[3], "close": candle[4], "volume": candle[5]})
        expected += INTERVAL_MS
    if expected != end_ms:
        raise ValueError(f"Incomplete range: {expected} != {end_ms}")
    return cleaned


def download(symbol: str, start_ms: int, end_ms: int) -> list:
    if symbol not in SYMBOLS or start_ms >= end_ms:
        raise ValueError("Invalid market/range")
    result = []
    cursor = start_ms
    while cursor < end_ms:
        params = urllib.parse.urlencode({"symbol": symbol, "interval": "4h", "startTime": cursor, "endTime": end_ms - 1, "limit": 1000})
        request = urllib.request.Request(f"{BASE_URL}?{params}", headers={"User-Agent": "RyzePublicOHLCVCollector/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            batch = json.load(response)
        if not isinstance(batch, list) or not batch:
            raise ValueError(f"No data available for {symbol} at {cursor}")
        if len(batch) > 1000 or batch[-1][0] < cursor:
            raise ValueError("Unexpected exchange response")
        result.extend(batch)
        next_cursor = batch[-1][0] + INTERVAL_MS
        if next_cursor <= cursor:
            raise ValueError("Non-progressing API cursor")
        cursor = next_cursor
        if cursor < end_ms:
            time.sleep(0.25)
    return result


def collect(symbol: str, start_ms: int, end_ms: int, directory: pathlib.Path) -> pathlib.Path:
    # The upper bound is exclusive and must be in the past: never include a live candle.
    current_boundary = int(time.time() * 1000) // INTERVAL_MS * INTERVAL_MS
    if end_ms > current_boundary:
        raise ValueError("Only fully closed historical candles may be collected")
    rows = validate(download(symbol, start_ms, end_ms), symbol, start_ms, end_ms)
    payload = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows).encode()
    sha = hashlib.sha256(payload).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{symbol}-4h-{start_ms}-{end_ms}"
    target = directory / f"{stem}-{sha[:12]}.jsonl"
    if target.exists() and target.read_bytes() != payload:
        raise ValueError("Existing immutable data conflict")
    target.write_bytes(payload)
    (directory / f"{stem}-{sha[:12]}.sha256").write_text(f"{sha}  {target.name}\n")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Public spot OHLCV collection only")
    parser.add_argument("--start", required=True, help="UTC ISO8601 at 4h boundary")
    parser.add_argument("--end", required=True, help="UTC ISO8601 exclusive at 4h boundary")
    parser.add_argument("--output", default="out")
    arguments = parser.parse_args()
    start_ms, end_ms = as_ms(arguments.start), as_ms(arguments.end)
    for symbol in SYMBOLS:
        print(collect(symbol, start_ms, end_ms, pathlib.Path(arguments.output)))


if __name__ == "__main__":
    main()

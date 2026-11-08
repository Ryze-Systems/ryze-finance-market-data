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

BINANCE_URL = "https://api.binance.com/api/v3/klines"
COINBASE_URL = "https://api.coinbase.com/api/v3/brokerage/market/products"
MARKETS = {"coinbase": ("BTC-USD", "ETH-USD", "SOL-USD"), "binance": ("BTCUSDT", "ETHUSDT", "SOLUSDT")}
SYMBOLS = tuple(symbol for symbols in MARKETS.values() for symbol in symbols)
INTERVAL_MS = 4 * 60 * 60 * 1000


def as_ms(value: str) -> int:
    timestamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("UTC timezone is required")
    return int(timestamp.timestamp() * 1000)


def validate(rows: list, symbol: str, start_ms: int, end_ms: int, provider: str = "binance") -> list[dict]:
    """Validate closed UTC 4-hour candles; fail on gaps or malformed OHLCV."""
    if provider not in MARKETS or symbol not in MARKETS[provider] or start_ms % INTERVAL_MS or end_ms % INTERVAL_MS:
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
        cleaned.append({"provider": provider, "symbol": symbol, "open_ms": at, "open": candle[1], "high": candle[2], "low": candle[3], "close": candle[4], "volume": candle[5]})
        expected += INTERVAL_MS
    if expected != end_ms:
        raise ValueError(f"Incomplete range: {expected} != {end_ms}")
    return cleaned


def download(symbol: str, start_ms: int, end_ms: int, provider: str = "binance") -> list:
    if provider not in MARKETS or symbol not in MARKETS[provider] or start_ms >= end_ms:
        raise ValueError("Invalid market/range")
    result = []
    cursor = start_ms
    while cursor < end_ms:
        if provider == "coinbase":
            window_end = min(cursor + 300 * INTERVAL_MS, end_ms)
            params = urllib.parse.urlencode({"start": cursor // 1000, "end": window_end // 1000, "granularity": "FOUR_HOUR", "limit": 300})
            url = f"{COINBASE_URL}/{symbol}/candles?{params}"
        else:
            window_end = end_ms
            params = urllib.parse.urlencode({"symbol": symbol, "interval": "4h", "startTime": cursor, "endTime": end_ms - 1, "limit": 1000})
            url = f"{BINANCE_URL}?{params}"
        request = urllib.request.Request(url, headers={"User-Agent": "RyzePublicOHLCVCollector/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            response_data = json.load(response)
        if provider == "coinbase":
            candles = response_data.get("candles") if isinstance(response_data, dict) else None
            if not isinstance(candles, list):
                raise ValueError("Unexpected Coinbase candle response")
            # Coinbase returns newest-first objects with Unix seconds; reject
            # missing candles rather than silently filling gaps.
            batch = sorted(([
                int(c["start"]) * 1000, c["open"], c["high"], c["low"], c["close"], c["volume"]
            ] for c in candles if cursor <= int(c["start"]) * 1000 < window_end), key=lambda item: item[0])
        else:
            batch = response_data
        if not isinstance(batch, list) or not batch:
            raise ValueError(f"No data available for {symbol} at {cursor}")
        if len(batch) > (300 if provider == "coinbase" else 1000) or batch[-1][0] < cursor:
            raise ValueError("Unexpected exchange response")
        result.extend(batch)
        next_cursor = batch[-1][0] + INTERVAL_MS
        if next_cursor <= cursor:
            raise ValueError("Non-progressing API cursor")
        cursor = next_cursor
        if cursor < end_ms:
            time.sleep(0.25)
    return result


def collect(symbol: str, start_ms: int, end_ms: int, directory: pathlib.Path, provider: str = "binance") -> pathlib.Path:
    # The upper bound is exclusive and must be in the past: never include a live candle.
    current_boundary = int(time.time() * 1000) // INTERVAL_MS * INTERVAL_MS
    if end_ms > current_boundary:
        raise ValueError("Only fully closed historical candles may be collected")
    rows = validate(download(symbol, start_ms, end_ms, provider), symbol, start_ms, end_ms, provider)
    payload = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows).encode()
    sha = hashlib.sha256(payload).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{provider}-{symbol}-4h-{start_ms}-{end_ms}"
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
    parser.add_argument("--provider", choices=MARKETS, default="coinbase")
    arguments = parser.parse_args()
    start_ms, end_ms = as_ms(arguments.start), as_ms(arguments.end)
    for symbol in MARKETS[arguments.provider]:
        print(collect(symbol, start_ms, end_ms, pathlib.Path(arguments.output), arguments.provider))


if __name__ == "__main__":
    main()

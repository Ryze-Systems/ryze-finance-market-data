"""Independent unauthenticated Kraken spot OHLC sample for recent crosschecking only."""

from __future__ import annotations

import hashlib
import json
import pathlib
import time
import urllib.parse
import urllib.request

from collector import INTERVAL_MS, validate

URL = "https://api.kraken.com/0/public/OHLC"
PAIRS = {"BTC-USD": "XBTUSD", "ETH-USD": "ETHUSD", "SOL-USD": "SOLUSD"}


def parse(response: object, *, symbol: str, closed_at_ms: int) -> list[dict]:
    if symbol not in PAIRS or not isinstance(response, dict) or response.get("error") != []:
        raise ValueError("Invalid Kraken spot response")
    result = response.get("result")
    if not isinstance(result, dict):
        raise ValueError("Missing Kraken OHLC result")
    pair_keys = [name for name in result if name != "last"]
    if len(pair_keys) != 1 or not isinstance(result[pair_keys[0]], list):
        raise ValueError("Unexpected Kraken pair count")
    rows = []
    for candle in result[pair_keys[0]]:
        if not isinstance(candle, list) or len(candle) < 7:
            raise ValueError("Malformed Kraken candle")
        if not isinstance(candle[0], int) and not (isinstance(candle[0], str) and candle[0].isdigit()):
            raise ValueError("Invalid Kraken timestamp")
        at = int(candle[0]) * 1000
        if at >= closed_at_ms:
            continue
        # Use the same strict numeric OHLCV validation as the main collector.
        validate([[at, candle[1], candle[2], candle[3], candle[4], candle[6]]], symbol,
                 at, at + INTERVAL_MS, provider="coinbase")
        rows.append({"provider": "kraken_spot", "symbol": symbol, "open_ms": at,
                     "open": candle[1], "high": candle[2], "low": candle[3],
                     "close": candle[4], "volume": candle[6]})
    rows.sort(key=lambda row: row["open_ms"])
    if len(rows) < 24 or any(b["open_ms"] - a["open_ms"] != INTERVAL_MS for a, b in zip(rows, rows[1:])):
        raise ValueError("Insufficient or incomplete Kraken 4h recent source")
    return rows


def collect(directory: pathlib.Path, *, as_of_ms: int | None = None) -> list[pathlib.Path]:
    closed_at = (int(time.time() * 1000) if as_of_ms is None else as_of_ms) // INTERVAL_MS * INTERVAL_MS
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for symbol, pair in PAIRS.items():
        url = URL + "?" + urllib.parse.urlencode({"pair": pair, "interval": 240})
        request = urllib.request.Request(url, headers={"User-Agent": "RyzePublicOHLCVCollector/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.load(response)
        rows = parse(data, symbol=symbol, closed_at_ms=closed_at)
        payload = b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in rows)
        sha = hashlib.sha256(payload).hexdigest()
        first, last = rows[0]["open_ms"], rows[-1]["open_ms"] + INTERVAL_MS
        path = directory / f"kraken_spot-{symbol}-4h-{first}-{last}-{sha[:12]}.jsonl"
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError("Immutable Kraken data conflict")
        else:
            with path.open("xb") as stream:
                stream.write(payload)
        sidecar = path.with_suffix(".sha256")
        expected = f"{sha}  {path.name}\n"
        if sidecar.exists():
            if sidecar.read_text() != expected:
                raise ValueError("Kraken hash sidecar conflict")
        else:
            with sidecar.open("x") as stream:
                stream.write(expected)
        paths.append(path)
    return paths


if __name__ == "__main__":
    for file in collect(pathlib.Path("out")):
        print(file)

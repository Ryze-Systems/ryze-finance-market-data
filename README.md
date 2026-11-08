# Ryze Finance public OHLCV collector

This repository contains only a public **spot market data collector** for BTC/ETH/SOL. It has no strategies, portfolio logic, account access, API keys, trading permissions, leverage or order submission.

The private research/paper-trading engine lives in `Ryze-Systems/ryze-finance-engine` and is not imported here.

The collector defaults to the unauthenticated Coinbase public API, retrieving 4-hour **BTC-USD, ETH-USD, SOL-USD** spot candles, validating contiguous UTC timestamps and OHLCV, rejecting incomplete live candles, and exporting immutable JSONL with SHA256 sidecars. The original Binance BTCUSDT/ETHUSDT/SOLUSDT source remains an explicit opt-in but returned HTTP 451 from GitHub runners on 2026-11-08, so it is not used in cloud workflows. USD and USDT quotes are not mixed or treated as identical. Exchange availability and historical completeness must be verified; one public endpoint is not a substitute for an independent source.

Offline tests: `python -m unittest -q test_collector`

The manual GitHub workflow accepts an explicit UTC `start` and `end` (exclusive). It never schedules itself, never receives credentials, and retains the output artifact for one day. A completed workflow only establishes data availability; scientific eligibility additionally requires sufficiently long histories, a second independent feed, fees and walk-forward validation.

Example manual run: `python collector.py --provider coinbase --start 2024-01-01T00:00:00Z --end 2024-01-09T00:00:00Z --output out`

On 2026-11-08, the long-range 2022-01-01 to 2026-11-01 GitHub run #3 rejected Coinbase BTC because the first expected timestamp (2022-01-01 00:00 UTC) was absent and the first returned timestamp was 04:00 UTC. This is **not** a certified complete history. The optional `--audit-only` command / workflow input gathers per-asset diagnostic JSON with total missing candles, duplicates, first twelve gap intervals, request range and source hash. Diagnostics are explicitly **not** market datasets: no trading or backtest is permitted to treat them as validated OHLCV. Missing candles are never synthesized or forward-filled by this collector.

Example: `python collector.py --provider coinbase --start 2022-01-01T00:00:00Z --end 2026-11-01T00:00:00Z --output out --audit-only`

Cloud automation is staged in a draft PR. Do not enable recurring runs until the free runner execution, artifact retention and operational budget have been verified, and merge has been explicitly approved.

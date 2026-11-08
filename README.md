# Ryze Finance public OHLCV collector

This repository contains only a public **spot market data collector** for BTC/ETH/SOL. It has no strategies, portfolio logic, account access, API keys, trading permissions, leverage or order submission.

The private research/paper-trading engine lives in `Ryze-Systems/ryze-finance-engine` and is not imported here.

The collector downloads Binance public 4-hour candles, validates contiguous UTC timestamps and OHLCV, rejects incomplete live candles, and exports immutable JSONL with SHA256 sidecars. Exchange availability and historical completeness must be verified; the public endpoint is not a substitute for an independent data source.

Offline tests: `python -m unittest -q test_collector`

Example manual run: `python collector.py --start 2024-01-01T00:00:00Z --end 2024-01-09T00:00:00Z --output out`

Cloud automation is staged in a draft PR. Do not enable recurring runs until the free runner execution, artifact retention and operational budget have been verified, and merge has been explicitly approved.

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import EXCHANGES, daily_csv_files, ensure_project_dirs, exchange_key, raw_daily_dir, validation_report_file


def validate_file(path: Path) -> dict[str, object]:
    ticker = path.stem
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return {
            "ticker": ticker,
            "row_count": 0,
            "first_date": "",
            "last_date": "",
            "missing_count": 0,
            "duplicate_count": 0,
            "invalid_ohlc_count": 0,
            "status": f"FAILED: {exc}",
        }

    if df.empty:
        return {
            "ticker": ticker,
            "row_count": 0,
            "first_date": "",
            "last_date": "",
            "missing_count": 0,
            "duplicate_count": 0,
            "invalid_ohlc_count": 0,
            "status": "EMPTY",
        }

    for col in ["open", "high", "low", "close", "adj_close", "volume"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")

    duplicate_count = int(df.duplicated(subset=["date"]).sum())
    missing_count = int(df.isna().sum().sum())
    negative_price = (df[["open", "high", "low", "close", "adj_close"]] < 0).any(axis=1)
    negative_volume = df["volume"] < 0
    invalid_ohlc = (
        (df["high"] < df["low"])
        | (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["low"] > df["open"])
        | (df["low"] > df["close"])
        | negative_price
        | negative_volume
    )
    invalid_ohlc_count = int(invalid_ohlc.fillna(False).sum())

    status = "OK"
    if invalid_ohlc_count:
        status = "INVALID_DATA"
    elif duplicate_count or missing_count:
        status = "CHECK"

    parsed_dates = pd.to_datetime(df["date"], errors="coerce")
    return {
        "ticker": str(df.get("ticker", pd.Series([ticker])).dropna().iloc[0]),
        "row_count": int(len(df)),
        "first_date": parsed_dates.min().date().isoformat() if parsed_dates.notna().any() else "",
        "last_date": parsed_dates.max().date().isoformat() if parsed_dates.notna().any() else "",
        "missing_count": missing_count,
        "duplicate_count": duplicate_count,
        "invalid_ohlc_count": invalid_ohlc_count,
        "status": status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate downloaded daily OHLCV CSV files.")
    parser.add_argument("--exchange", choices=EXCHANGES, default="nasdaq")
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    exchange = exchange_key(args.exchange)
    input_dir = args.input_dir or raw_daily_dir(exchange)
    output = args.output or validation_report_file(exchange)
    ensure_project_dirs(exchange)
    rows = [validate_file(path) for path in daily_csv_files(input_dir, include_legacy=exchange == "nasdaq")]
    report = pd.DataFrame(
        rows,
        columns=[
            "ticker",
            "row_count",
            "first_date",
            "last_date",
            "missing_count",
            "duplicate_count",
            "invalid_ohlc_count",
            "status",
        ],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output, index=False, encoding="utf-8")
    print(f"saved validation report for {len(report):,} {exchange} files to {output}")


if __name__ == "__main__":
    main()

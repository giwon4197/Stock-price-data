from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import EXCHANGES, daily_csv_files, ensure_project_dirs, exchange_key, metadata_file, raw_daily_dir


def summarize_file(path: Path) -> dict[str, object]:
    try:
        df = pd.read_csv(path)
    except Exception:
        return {
            "ticker": path.stem,
            "first_date": "",
            "last_date": "",
            "row_count": 0,
            "data_years": 0.0,
            "has_missing": True,
            "status": "FAILED",
        }

    if df.empty:
        return {
            "ticker": path.stem,
            "first_date": "",
            "last_date": "",
            "row_count": 0,
            "data_years": 0.0,
            "has_missing": False,
            "status": "EMPTY",
        }

    dates = pd.to_datetime(df["date"], errors="coerce")
    first = dates.min()
    last = dates.max()
    data_years = round((last - first).days / 365.25, 2) if pd.notna(first) and pd.notna(last) else 0.0
    has_missing = bool(df.isna().any().any() or dates.isna().any())

    status = "OK"
    if len(df) < 252:
        status = "SHORT_HISTORY"
    if has_missing:
        status = "INVALID_DATA"

    return {
        "ticker": str(df.get("ticker", pd.Series([path.stem])).dropna().iloc[0]),
        "first_date": first.date().isoformat() if pd.notna(first) else "",
        "last_date": last.date().isoformat() if pd.notna(last) else "",
        "row_count": int(len(df)),
        "data_years": data_years,
        "has_missing": has_missing,
        "status": status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build per-ticker metadata summary.")
    parser.add_argument("--exchange", choices=EXCHANGES, default="nasdaq")
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    exchange = exchange_key(args.exchange)
    input_dir = args.input_dir or raw_daily_dir(exchange)
    output = args.output or metadata_file(exchange)
    ensure_project_dirs(exchange)
    rows = [summarize_file(path) for path in daily_csv_files(input_dir, include_legacy=exchange == "nasdaq")]
    summary = pd.DataFrame(
        rows,
        columns=["ticker", "first_date", "last_date", "row_count", "data_years", "has_missing", "status"],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output, index=False, encoding="utf-8")
    print(f"saved metadata for {len(summary):,} {exchange} files to {output}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import (
    DB_PRICE_COLUMNS,
    EXCHANGES,
    daily_csv_files,
    ensure_columns,
    ensure_project_dirs,
    exchange_key,
    parquet_file,
    raw_daily_dir,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge daily CSV files into one parquet dataset.")
    parser.add_argument("--exchange", choices=EXCHANGES, default="nasdaq")
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    exchange = exchange_key(args.exchange)
    input_dir = args.input_dir or raw_daily_dir(exchange)
    output = args.output or parquet_file(exchange)
    ensure_project_dirs(exchange)
    files = daily_csv_files(input_dir, include_legacy=exchange == "nasdaq")
    print(f"[{exchange}] merging {len(files):,} CSV files from {input_dir}")

    frames = []
    for index, path in enumerate(files, start=1):
        df = pd.read_csv(path)
        frames.append(ensure_columns(df, DB_PRICE_COLUMNS)[DB_PRICE_COLUMNS])
        if index == 1 or index % 100 == 0 or index == len(files):
            print(f"[{exchange}] read {index:,}/{len(files):,} files")

    if frames:
        print(f"[{exchange}] concatenating {len(frames):,} frames")
        merged = pd.concat(frames, ignore_index=True)
        merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
        print(f"[{exchange}] sorting {len(merged):,} rows")
        merged = merged.sort_values(["security_id", "ticker", "date"])
    else:
        merged = pd.DataFrame(columns=DB_PRICE_COLUMNS)

    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"[{exchange}] writing parquet to {output}")
    merged.to_parquet(output, index=False)
    print(f"saved {len(merged):,} {exchange} rows to {output}")


if __name__ == "__main__":
    main()

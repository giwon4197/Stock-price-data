from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import INDEX_DAILY_DIR, PRICE_COLUMNS, PROCESSED_DIR, daily_csv_files, ensure_columns, ensure_project_dirs


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge index daily CSV files into one parquet dataset.")
    parser.add_argument("--input-dir", type=Path, default=INDEX_DAILY_DIR)
    parser.add_argument("--output", type=Path, default=PROCESSED_DIR / "index_daily_all.parquet")
    args = parser.parse_args()

    ensure_project_dirs()
    files = daily_csv_files(args.input_dir)
    print(f"[index] merging {len(files):,} CSV files from {args.input_dir}")

    frames = []
    for index, path in enumerate(files, start=1):
        df = pd.read_csv(path)
        frames.append(ensure_columns(df, PRICE_COLUMNS)[PRICE_COLUMNS])
        print(f"[index] read {index:,}/{len(files):,} files: {path.name}")

    if frames:
        print(f"[index] concatenating {len(frames):,} frames")
        merged = pd.concat(frames, ignore_index=True)
        merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
        print(f"[index] sorting {len(merged):,} rows")
        merged = merged.sort_values(["ticker", "date"])
    else:
        merged = pd.DataFrame(columns=PRICE_COLUMNS)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"[index] writing parquet to {args.output}")
    merged.to_parquet(args.output, index=False)
    print(f"saved {len(merged):,} index rows to {args.output}")


if __name__ == "__main__":
    main()

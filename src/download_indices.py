from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from common import INDEX_DAILY_DIR, PRICE_COLUMNS, ensure_project_dirs


INDEX_SYMBOLS = {
    "sp500": "^GSPC",
    "nasdaq100": "^NDX",
    "dowjones_industrial_average": "^DJI",
    "russell2000": "^RUT",
    "sp100": "^OEX",
    "russell1000": "^RUI",
    "russell3000": "^RUA",
}


def normalize_index_download(df: pd.DataFrame, index_name: str, downloaded_at: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    renamed = df.reset_index().rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    renamed["date"] = pd.to_datetime(renamed["date"]).dt.date.astype(str)
    renamed["ticker"] = index_name
    renamed["source"] = "Yahoo Finance"
    renamed["downloaded_at"] = downloaded_at

    for col in ["open", "high", "low", "close", "adj_close", "volume"]:
        renamed[col] = pd.to_numeric(renamed.get(col), errors="coerce")

    return renamed[PRICE_COLUMNS].sort_values("date")


def download_index(index_name: str, symbol: str, output_dir: Path, force: bool) -> None:
    output = output_dir / f"{index_name}.csv"
    if output.exists() and not force:
        print(f"skip existing index {index_name}")
        return

    downloaded_at = datetime.now(timezone.utc).isoformat()
    data = yf.download(
        symbol,
        period="max",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    normalized = normalize_index_download(data, index_name, downloaded_at)
    if normalized.empty:
        raise RuntimeError(f"empty data for index {index_name} ({symbol})")

    output.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output, index=False, encoding="utf-8")
    print(f"saved index {index_name} ({symbol}): {len(normalized):,} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download major index daily price histories.")
    parser.add_argument("--output-dir", type=Path, default=INDEX_DAILY_DIR)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", choices=sorted(INDEX_SYMBOLS), action="append", default=[])
    args = parser.parse_args()

    ensure_project_dirs()
    names = args.only or list(INDEX_SYMBOLS)
    for name in names:
        download_index(name, INDEX_SYMBOLS[name], args.output_dir, args.force)


if __name__ == "__main__":
    main()

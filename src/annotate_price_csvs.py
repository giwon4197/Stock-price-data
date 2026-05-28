from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import (
    DB_PRICE_COLUMNS,
    EXCHANGES,
    LISTING_EVENTS_FILE,
    csv_safe_ticker,
    daily_csv_files,
    ensure_columns,
    ensure_project_dirs,
    exchange_key,
    raw_daily_dir,
)


def normalize_date_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce")


def load_listings(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"missing listing reference file: {path}. Run src/build_reference.py first.")
    listings = pd.read_csv(path, dtype=str).fillna("")
    required = {"security_id", "listing_id", "ticker", "exchange", "start_date", "end_date"}
    missing = required.difference(listings.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")

    listings["ticker_key"] = listings["ticker"].str.strip().str.upper()
    listings["exchange_key"] = listings["exchange"].str.strip().str.upper()
    listings["start_dt"] = normalize_date_series(listings["start_date"])
    listings["end_dt"] = normalize_date_series(listings["end_date"])
    return listings


def select_listing_rows(listings: pd.DataFrame, ticker: str, exchange: str) -> pd.DataFrame:
    ticker_key = ticker.strip().upper()
    exchange_key_value = exchange.strip().upper()
    rows = listings[listings["ticker_key"].eq(ticker_key)]
    if exchange_key_value:
        exchange_rows = rows[rows["exchange_key"].eq(exchange_key_value)]
        if not exchange_rows.empty:
            rows = exchange_rows
    return rows


def apply_listing_ids(df: pd.DataFrame, listings: pd.DataFrame, fallback_exchange: str) -> pd.DataFrame:
    if df.empty:
        return df

    result = ensure_columns(df.copy(), DB_PRICE_COLUMNS)

    ticker = str(result["ticker"].dropna().iloc[0]).strip() if result["ticker"].astype(str).str.strip().any() else ""
    exchange = (
        str(result["exchange"].dropna().iloc[0]).strip()
        if result["exchange"].astype(str).str.strip().any()
        else fallback_exchange.upper()
    )
    if not result["exchange"].astype(str).str.strip().any():
        result["exchange"] = exchange

    matched = select_listing_rows(listings, ticker, exchange)
    if matched.empty:
        return result[DB_PRICE_COLUMNS]

    dates = normalize_date_series(result["date"])
    for listing in matched.itertuples(index=False):
        start = listing.start_dt
        end = listing.end_dt
        mask = pd.Series(True, index=result.index)
        if pd.notna(start):
            mask &= dates >= start
        if pd.notna(end):
            mask &= dates <= end
        if not mask.any():
            continue
        result.loc[mask, "security_id"] = listing.security_id
        result.loc[mask, "listing_id"] = listing.listing_id
        result.loc[mask, "exchange"] = listing.exchange

    if result["security_id"].astype(str).str.strip().eq("").all():
        current_rows = matched[matched["is_current"].astype(str).str.lower().isin(["true", "1"])]
        selected = current_rows.iloc[-1] if not current_rows.empty else matched.iloc[-1]
        result["security_id"] = selected["security_id"]
        result["listing_id"] = selected["listing_id"]
        result["exchange"] = selected["exchange"]

    return result[DB_PRICE_COLUMNS]


def annotate_file(path: Path, listings: pd.DataFrame, fallback_exchange: str, output_dir: Path, inplace: bool) -> None:
    df = pd.read_csv(path, dtype=str).fillna("")
    annotated = apply_listing_ids(df, listings, fallback_exchange)
    output = path if inplace else output_dir / path.name
    output.parent.mkdir(parents=True, exist_ok=True)
    annotated.to_csv(output, index=False, encoding="utf-8")
    assigned = annotated["security_id"].astype(str).str.strip().ne("").sum()
    print(f"saved {output} ({assigned:,}/{len(annotated):,} rows assigned)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Add security_id/listing_id columns directly to daily price CSV files.")
    parser.add_argument("--exchange", choices=EXCHANGES, default="nasdaq")
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--listings", type=Path, default=LISTING_EVENTS_FILE)
    parser.add_argument("--ticker", action="append", default=[], help="Limit to one or more tickers.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--inplace", action="store_true", help="Rewrite files in the input directory.")
    args = parser.parse_args()

    exchange = exchange_key(args.exchange)
    input_dir = args.input_dir or raw_daily_dir(exchange)
    output_dir = args.output_dir or input_dir
    ensure_project_dirs(exchange)
    listings = load_listings(args.listings)

    files = daily_csv_files(input_dir, include_legacy=exchange == "nasdaq")
    if args.ticker:
        wanted = {csv_safe_ticker(ticker).upper() for ticker in args.ticker}
        files = [path for path in files if path.stem.upper() in wanted]
    if args.limit is not None:
        files = files[: args.limit]

    for path in files:
        annotate_file(path, listings, exchange, output_dir, args.inplace)

    print(f"annotated {len(files):,} {exchange} CSV files")


if __name__ == "__main__":
    main()

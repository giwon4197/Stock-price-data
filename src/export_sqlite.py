from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

from common import (
    DATABASE_FILE,
    DB_PRICE_COLUMNS,
    EXCHANGES,
    INDEX_DAILY_DIR,
    LISTING_EVENTS_FILE,
    OHLCV_COLUMNS,
    SCHEMA_FILE,
    SECURITY_MASTER_FILE,
    TICKER_ALIASES_FILE,
    daily_csv_files,
    ensure_columns,
    ensure_project_dirs,
    raw_daily_dir,
)


REFERENCE_TABLES = [
    ("securities", SECURITY_MASTER_FILE),
    ("listings", LISTING_EVENTS_FILE),
    ("ticker_aliases", TICKER_ALIASES_FILE),
]
DROP_TABLES = [
    "daily_prices",
    "index_daily_prices",
    "ticker_aliases",
    "listings",
    "securities",
]


def reset_schema(connection: sqlite3.Connection) -> None:
    print("resetting SQLite schema")
    for table in DROP_TABLES:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
    connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    connection.commit()


def load_reference_tables(connection: sqlite3.Connection) -> pd.DataFrame:
    listings = pd.DataFrame(columns=["ticker", "exchange", "security_id", "listing_id", "start_date", "end_date"])
    for table, path in REFERENCE_TABLES:
        if not path.exists():
            print(f"skip missing reference table: {path}")
            continue
        df = pd.read_csv(path, dtype=str).fillna("")
        if table == "listings" and "is_current" in df:
            df["is_current"] = df["is_current"].map(lambda value: 1 if str(value).lower() in {"true", "1"} else 0)
            listings = df.copy()
        df.to_sql(table, connection, if_exists="append", index=False)
        print(f"loaded {len(df):,} rows into {table}")

    return listings


def build_listing_lookup(listings: pd.DataFrame) -> dict[tuple[str, str], pd.DataFrame]:
    lookup: dict[tuple[str, str], pd.DataFrame] = {}
    if listings.empty:
        return lookup

    normalized = listings.copy()
    normalized["ticker_key"] = normalized["ticker"].astype(str).str.strip().str.upper()
    normalized["exchange_key"] = normalized["exchange"].astype(str).str.strip().str.upper()
    normalized["start_dt"] = pd.to_datetime(normalized["start_date"], errors="coerce")
    normalized["end_dt"] = pd.to_datetime(normalized["end_date"], errors="coerce")
    normalized["is_current_bool"] = normalized["is_current"].map(lambda value: str(value).lower() in {"true", "1"})

    for (ticker, exchange), group in normalized.groupby(["ticker_key", "exchange_key"], sort=False):
        lookup[(ticker, exchange)] = group.copy()
        lookup.setdefault((ticker, ""), group.copy())
    return lookup


def apply_listing_history(normalized: pd.DataFrame, listings: pd.DataFrame) -> pd.DataFrame:
    if listings.empty:
        return normalized

    dates = pd.to_datetime(normalized["date"], errors="coerce")
    for listing in listings.itertuples(index=False):
        mask = pd.Series(True, index=normalized.index)
        if pd.notna(listing.start_dt):
            mask &= dates >= listing.start_dt
        if pd.notna(listing.end_dt):
            mask &= dates <= listing.end_dt
        if not mask.any():
            continue
        normalized.loc[mask, "security_id"] = normalized.loc[mask, "security_id"].where(
            normalized.loc[mask, "security_id"].astype(str).str.strip().ne(""),
            listing.security_id,
        )
        normalized.loc[mask, "listing_id"] = normalized.loc[mask, "listing_id"].where(
            normalized.loc[mask, "listing_id"].astype(str).str.strip().ne(""),
            listing.listing_id,
        )
        normalized.loc[mask, "exchange"] = normalized.loc[mask, "exchange"].where(
            normalized.loc[mask, "exchange"].astype(str).str.strip().ne(""),
            listing.exchange,
        )

    missing = normalized["security_id"].astype(str).str.strip().eq("")
    if missing.any():
        current = listings[listings["is_current_bool"]]
        selected = current.iloc[-1] if not current.empty else listings.iloc[-1]
        normalized.loc[missing, "security_id"] = selected["security_id"]
        normalized.loc[missing, "listing_id"] = selected["listing_id"]
        normalized.loc[missing, "exchange"] = selected["exchange"]
    return normalized


def normalize_price_frame(df: pd.DataFrame, fallback_exchange: str, lookup: dict[tuple[str, str], pd.DataFrame]) -> pd.DataFrame:
    normalized = ensure_columns(df.copy(), DB_PRICE_COLUMNS)

    if "exchange" not in df or normalized["exchange"].astype(str).str.strip().eq("").all():
        normalized["exchange"] = fallback_exchange.upper()

    ticker = str(normalized["ticker"].dropna().iloc[0]).strip().upper() if not normalized.empty else ""
    exchange = str(normalized["exchange"].dropna().iloc[0]).strip().upper() if not normalized.empty else ""
    listings = lookup.get((ticker, exchange))
    if listings is None:
        listings = lookup.get((ticker, ""), pd.DataFrame())
    normalized = apply_listing_history(normalized, listings)

    normalized = normalized[DB_PRICE_COLUMNS].rename(columns={"date": "price_date"})
    for column in OHLCV_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized.drop_duplicates(["price_date", "ticker", "security_id", "listing_id"])


def load_daily_prices(connection: sqlite3.Connection, lookup: dict[tuple[str, str], pd.DataFrame]) -> None:
    total = 0
    for exchange in EXCHANGES:
        input_dir = raw_daily_dir(exchange)
        files = daily_csv_files(input_dir, include_legacy=exchange == "nasdaq")
        print(f"[{exchange}] loading {len(files):,} price files into SQLite")
        exchange_total = 0
        for index, path in enumerate(files, start=1):
            df = pd.read_csv(path, dtype=str).fillna("")
            normalized = normalize_price_frame(df, exchange, lookup)
            normalized.to_sql("daily_prices", connection, if_exists="append", index=False, chunksize=10_000)
            exchange_total += len(normalized)
            total += len(normalized)
            if index == 1 or index % 100 == 0 or index == len(files):
                print(
                    f"[{exchange}] loaded {index:,}/{len(files):,} files "
                    f"({exchange_total:,} rows)"
                )
    print(f"loaded {total:,} rows into daily_prices")


def load_index_prices(connection: sqlite3.Connection) -> None:
    total = 0
    if not INDEX_DAILY_DIR.exists():
        return
    files = sorted(INDEX_DAILY_DIR.glob("*.csv"))
    print(f"loading {len(files):,} index price files into SQLite")
    for index, path in enumerate(files, start=1):
        df = pd.read_csv(path, dtype=str).fillna("")
        df = df.rename(columns={"date": "price_date", "ticker": "index_id"})
        for column in OHLCV_COLUMNS:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        columns = [
            "price_date",
            "index_id",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "source",
            "downloaded_at",
        ]
        df = df[columns].drop_duplicates(["price_date", "index_id"])
        df.to_sql("index_daily_prices", connection, if_exists="append", index=False, chunksize=10_000)
        total += len(df)
        print(f"loaded index file {index:,}/{len(files):,}: {path.name} ({len(df):,} rows)")
    print(f"loaded {total:,} rows into index_daily_prices")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export reference, stock price, and index tables to SQLite.")
    parser.add_argument("--output", type=Path, default=DATABASE_FILE)
    parser.add_argument("--skip-prices", action="store_true")
    args = parser.parse_args()

    ensure_project_dirs()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.output) as connection:
        reset_schema(connection)
        listings = load_reference_tables(connection)
        lookup = build_listing_lookup(listings)
        if not args.skip_prices:
            load_daily_prices(connection, lookup)
            load_index_prices(connection)
        connection.commit()
    print(f"saved SQLite database to {args.output}")


if __name__ == "__main__":
    main()

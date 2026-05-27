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
    SCHEMA_FILE,
    SECURITY_MASTER_FILE,
    TICKER_ALIASES_FILE,
    current_listing_file,
    daily_csv_files,
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
    for table in DROP_TABLES:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
    connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    connection.commit()


def load_reference_tables(connection: sqlite3.Connection) -> pd.DataFrame:
    for table, path in REFERENCE_TABLES:
        if not path.exists():
            print(f"skip missing reference table: {path}")
            continue
        df = pd.read_csv(path, dtype=str).fillna("")
        if table == "listings" and "is_current" in df:
            df["is_current"] = df["is_current"].map(lambda value: 1 if str(value).lower() in {"true", "1"} else 0)
        df.to_sql(table, connection, if_exists="append", index=False)
        print(f"loaded {len(df):,} rows into {table}")

    current_frames = []
    for exchange in EXCHANGES:
        path = current_listing_file(exchange)
        if path.exists():
            current_frames.append(pd.read_csv(path, dtype=str).fillna(""))
    if current_frames:
        return pd.concat(current_frames, ignore_index=True)
    return pd.DataFrame(columns=["ticker", "exchange", "security_id", "listing_id"])


def build_listing_lookup(current_listings: pd.DataFrame) -> dict[tuple[str, str], dict[str, str]]:
    lookup = {}
    for row in current_listings.itertuples(index=False):
        ticker = str(row.ticker).strip().upper()
        exchange = str(row.exchange).strip().upper()
        lookup[(ticker, exchange)] = {
            "security_id": str(row.security_id).strip(),
            "listing_id": str(row.listing_id).strip(),
            "exchange": exchange,
        }
        lookup.setdefault(
            (ticker, ""),
            {
                "security_id": str(row.security_id).strip(),
                "listing_id": str(row.listing_id).strip(),
                "exchange": exchange,
            },
        )
    return lookup


def normalize_price_frame(df: pd.DataFrame, fallback_exchange: str, lookup: dict[tuple[str, str], dict[str, str]]) -> pd.DataFrame:
    normalized = df.copy()
    for column in DB_PRICE_COLUMNS:
        if column not in normalized:
            normalized[column] = ""

    if "exchange" not in df or normalized["exchange"].astype(str).str.strip().eq("").all():
        normalized["exchange"] = fallback_exchange.upper()

    ticker = str(normalized["ticker"].dropna().iloc[0]).strip().upper() if not normalized.empty else ""
    exchange = str(normalized["exchange"].dropna().iloc[0]).strip().upper() if not normalized.empty else ""
    listing = lookup.get((ticker, exchange)) or lookup.get((ticker, ""))
    if listing:
        normalized["security_id"] = normalized["security_id"].where(
            normalized["security_id"].astype(str).str.strip().ne(""),
            listing["security_id"],
        )
        normalized["listing_id"] = normalized["listing_id"].where(
            normalized["listing_id"].astype(str).str.strip().ne(""),
            listing["listing_id"],
        )
        normalized["exchange"] = normalized["exchange"].where(
            normalized["exchange"].astype(str).str.strip().ne(""),
            listing["exchange"],
        )

    normalized = normalized[DB_PRICE_COLUMNS].rename(columns={"date": "price_date"})
    for column in ["open", "high", "low", "close", "adj_close", "volume"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized.drop_duplicates(["price_date", "ticker", "security_id", "listing_id"])


def load_daily_prices(connection: sqlite3.Connection, lookup: dict[tuple[str, str], dict[str, str]]) -> None:
    total = 0
    for exchange in EXCHANGES:
        input_dir = raw_daily_dir(exchange)
        files = daily_csv_files(input_dir, include_legacy=exchange == "nasdaq")
        for path in files:
            df = pd.read_csv(path, dtype=str).fillna("")
            normalized = normalize_price_frame(df, exchange, lookup)
            normalized.to_sql("daily_prices", connection, if_exists="append", index=False, chunksize=10_000)
            total += len(normalized)
        if files:
            print(f"loaded {len(files):,} {exchange} price files")
    print(f"loaded {total:,} rows into daily_prices")


def load_index_prices(connection: sqlite3.Connection) -> None:
    total = 0
    if not INDEX_DAILY_DIR.exists():
        return
    for path in sorted(INDEX_DAILY_DIR.glob("*.csv")):
        df = pd.read_csv(path, dtype=str).fillna("")
        df = df.rename(columns={"date": "price_date", "ticker": "index_id"})
        for column in ["open", "high", "low", "close", "adj_close", "volume"]:
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
        current_listings = load_reference_tables(connection)
        lookup = build_listing_lookup(current_listings)
        if not args.skip_prices:
            load_daily_prices(connection, lookup)
            load_index_prices(connection)
        connection.commit()
    print(f"saved SQLite database to {args.output}")


if __name__ == "__main__":
    main()

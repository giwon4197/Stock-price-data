from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from common import (
    CURRENT_LISTINGS_FILE,
    EXCHANGES,
    LISTING_EVENTS_FILE,
    MANUAL_OVERRIDES_FILE,
    SECURITY_MASTER_FILE,
    TICKER_ALIASES_FILE,
    current_listing_file,
    ensure_project_dirs,
    exchange_key,
    ticker_file,
)


SECURITY_COLUMNS = [
    "security_id",
    "issuer_name",
    "current_ticker",
    "primary_exchange",
    "status",
    "source",
    "collected_at",
]
LISTING_COLUMNS = [
    "listing_id",
    "security_id",
    "ticker",
    "exchange",
    "security_name",
    "start_date",
    "end_date",
    "event_type",
    "is_current",
    "source",
    "collected_at",
]
ALIAS_COLUMNS = [
    "alias_id",
    "security_id",
    "ticker",
    "exchange",
    "valid_from",
    "valid_to",
    "source",
    "confidence",
]
MANUAL_COLUMNS = [
    "security_id",
    "ticker",
    "exchange",
    "security_name",
    "issuer_name",
    "start_date",
    "end_date",
    "event_type",
    "is_current",
    "status",
    "source",
    "collected_at",
    "confidence",
]


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join("" if part is None else str(part).strip().upper() for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14]
    return f"{prefix}_{digest}"


def normalize_bool(value: object) -> bool:
    text = str(value).strip().lower()
    return text in {"1", "true", "t", "yes", "y", "current"}


def build_current_rows(exchanges: list[str]) -> pd.DataFrame:
    rows = []
    for exchange in exchanges:
        exchange = exchange_key(exchange)
        path = ticker_file(exchange)
        if not path.exists():
            print(f"skip missing ticker universe: {path}")
            continue
        universe = pd.read_csv(path, dtype=str).fillna("")
        for row in universe.itertuples(index=False):
            ticker = str(row.ticker).strip()
            exchange_name = str(getattr(row, "exchange", exchange.upper())).strip() or exchange.upper()
            security_name = str(getattr(row, "security_name", ticker)).strip() or ticker
            source = str(getattr(row, "source", path)).strip() or str(path)
            collected_at = str(getattr(row, "collected_at", "")).strip()
            security_id = stable_id("sec", exchange_name, ticker, security_name)
            rows.append(
                {
                    "security_id": security_id,
                    "ticker": ticker,
                    "exchange": exchange_name,
                    "security_name": security_name,
                    "issuer_name": security_name,
                    "start_date": "",
                    "end_date": "",
                    "event_type": "current_listing",
                    "is_current": True,
                    "status": "active",
                    "source": source,
                    "collected_at": collected_at,
                    "confidence": "symbol_directory_current",
                }
            )
    return pd.DataFrame(rows, columns=MANUAL_COLUMNS)


def load_manual_overrides(path: Path) -> pd.DataFrame:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=MANUAL_COLUMNS).to_csv(path, index=False, encoding="utf-8")
        print(f"created manual override template: {path}")
        return pd.DataFrame(columns=MANUAL_COLUMNS)

    overrides = pd.read_csv(path, dtype=str).fillna("")
    missing = set(MANUAL_COLUMNS).difference(overrides.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")
    return overrides[MANUAL_COLUMNS]


def normalize_reference_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()

    normalized = rows.copy().astype("object")
    normalized = normalized.where(pd.notna(normalized), "")
    now = datetime.now(timezone.utc).isoformat()
    normalized["ticker"] = normalized["ticker"].str.strip()
    normalized["exchange"] = normalized["exchange"].str.strip().str.upper()
    normalized["security_name"] = normalized["security_name"].where(
        normalized["security_name"].str.strip().ne(""),
        normalized["ticker"],
    )
    normalized["issuer_name"] = normalized["issuer_name"].where(
        normalized["issuer_name"].str.strip().ne(""),
        normalized["security_name"],
    )
    missing_security = normalized["security_id"].str.strip().eq("")
    normalized.loc[missing_security, "security_id"] = normalized.loc[missing_security].apply(
        lambda row: stable_id("sec", row["exchange"], row["ticker"], row["issuer_name"]),
        axis=1,
    )
    normalized["event_type"] = normalized["event_type"].where(
        normalized["event_type"].str.strip().ne(""),
        "manual_listing",
    )
    normalized["status"] = normalized["status"].where(normalized["status"].str.strip().ne(""), "active")
    normalized["source"] = normalized["source"].where(normalized["source"].str.strip().ne(""), "manual")
    normalized["collected_at"] = normalized["collected_at"].where(
        normalized["collected_at"].str.strip().ne(""),
        now,
    )
    normalized["confidence"] = normalized["confidence"].where(
        normalized["confidence"].str.strip().ne(""),
        "manual",
    )
    normalized["is_current"] = normalized["is_current"].map(normalize_bool)
    return normalized


def build_tables(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = normalize_reference_rows(rows)
    if rows.empty:
        empty_security = pd.DataFrame(columns=SECURITY_COLUMNS)
        empty_listing = pd.DataFrame(columns=LISTING_COLUMNS)
        empty_alias = pd.DataFrame(columns=ALIAS_COLUMNS)
        return empty_security, empty_listing, empty_alias, pd.DataFrame(columns=LISTING_COLUMNS)

    listings = rows.copy()
    listings["listing_id"] = listings.apply(
        lambda row: stable_id(
            "lst",
            row["security_id"],
            row["ticker"],
            row["exchange"],
            row["start_date"],
            row["end_date"],
        ),
        axis=1,
    )
    listings = listings[LISTING_COLUMNS].drop_duplicates("listing_id").sort_values(["exchange", "ticker"])

    aliases = rows.copy()
    aliases["alias_id"] = aliases.apply(
        lambda row: stable_id("als", row["security_id"], row["ticker"], row["exchange"], row["start_date"]),
        axis=1,
    )
    aliases = aliases.rename(columns={"start_date": "valid_from", "end_date": "valid_to"})
    aliases = aliases[ALIAS_COLUMNS].drop_duplicates("alias_id").sort_values(["exchange", "ticker"])

    security_rows = []
    for security_id, group in rows.groupby("security_id", sort=True):
        current = group[group["is_current"]]
        selected = current.iloc[-1] if not current.empty else group.iloc[-1]
        security_rows.append(
            {
                "security_id": security_id,
                "issuer_name": selected["issuer_name"],
                "current_ticker": selected["ticker"],
                "primary_exchange": selected["exchange"],
                "status": selected["status"],
                "source": selected["source"],
                "collected_at": selected["collected_at"],
            }
        )
    securities = pd.DataFrame(security_rows, columns=SECURITY_COLUMNS).sort_values("security_id")
    current_listings = listings[listings["is_current"].astype(bool)].copy()
    return securities, listings, aliases, current_listings


def write_exchange_current_files(current_listings: pd.DataFrame) -> None:
    for exchange in EXCHANGES:
        exchange_name = exchange.upper()
        subset = current_listings[current_listings["exchange"].str.upper().eq(exchange_name)]
        subset.to_csv(current_listing_file(exchange), index=False, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DB-style security master and listing event tables.")
    parser.add_argument("--exchanges", nargs="+", choices=EXCHANGES, default=list(EXCHANGES))
    parser.add_argument("--manual-overrides", type=Path, default=MANUAL_OVERRIDES_FILE)
    args = parser.parse_args()

    ensure_project_dirs()
    current_rows = build_current_rows(args.exchanges)
    manual_rows = load_manual_overrides(args.manual_overrides)
    combined = pd.concat([current_rows, manual_rows], ignore_index=True)
    combined = combined.drop_duplicates(["security_id", "ticker", "exchange", "start_date", "end_date"], keep="last")

    securities, listings, aliases, current_listings = build_tables(combined)
    SECURITY_MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    securities.to_csv(SECURITY_MASTER_FILE, index=False, encoding="utf-8")
    listings.to_csv(LISTING_EVENTS_FILE, index=False, encoding="utf-8")
    aliases.to_csv(TICKER_ALIASES_FILE, index=False, encoding="utf-8")
    current_listings.to_csv(CURRENT_LISTINGS_FILE, index=False, encoding="utf-8")
    write_exchange_current_files(current_listings)

    print(f"saved {len(securities):,} securities to {SECURITY_MASTER_FILE}")
    print(f"saved {len(listings):,} listings to {LISTING_EVENTS_FILE}")
    print(f"saved {len(aliases):,} aliases to {TICKER_ALIASES_FILE}")
    print(f"saved {len(current_listings):,} current listings to {CURRENT_LISTINGS_FILE}")


if __name__ == "__main__":
    main()

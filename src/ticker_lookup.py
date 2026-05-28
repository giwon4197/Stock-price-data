from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from common import (
    EXCHANGES,
    LISTING_EVENTS_FILE,
    SECURITY_MASTER_FILE,
    TICKER_ALIASES_FILE,
    csv_safe_ticker,
    raw_daily_dir,
)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def find_matches(query: str, listings: pd.DataFrame, aliases: pd.DataFrame, securities: pd.DataFrame) -> set[str]:
    normalized = query.strip().upper()
    security_ids: set[str] = set()

    if not listings.empty:
        ticker_match = listings["ticker"].str.upper().eq(normalized)
        security_match = listings["security_id"].str.upper().eq(normalized)
        name_match = listings["security_name"].str.upper().str.contains(normalized, regex=False, na=False)
        security_ids.update(listings.loc[ticker_match | security_match | name_match, "security_id"])

    if not aliases.empty:
        alias_match = aliases["ticker"].str.upper().eq(normalized)
        security_match = aliases["security_id"].str.upper().eq(normalized)
        security_ids.update(aliases.loc[alias_match | security_match, "security_id"])

    if not securities.empty:
        security_match = securities["security_id"].str.upper().eq(normalized)
        ticker_match = securities["current_ticker"].str.upper().eq(normalized)
        name_match = securities["issuer_name"].str.upper().str.contains(normalized, regex=False, na=False)
        security_ids.update(securities.loc[security_match | ticker_match | name_match, "security_id"])

    return {security_id for security_id in security_ids if str(security_id).strip()}


def classify_security(listing_rows: pd.DataFrame) -> list[str]:
    flags = []
    tickers = set(listing_rows["ticker"].str.upper())
    exchanges = set(listing_rows["exchange"].str.upper())
    event_types = set(listing_rows["event_type"].str.lower())

    if len(tickers) > 1:
        flags.append("ticker_changed")
    if len(exchanges) > 1:
        flags.append("exchange_changed")
    if "reused_ticker" in event_types:
        flags.append("reused_ticker")
    if "relisted" in event_types:
        flags.append("relisted")
    if "delisted" in event_types:
        flags.append("delisted_history")
    if not flags:
        flags.append("normal_or_unconfirmed")
    return flags


def price_paths_for_ticker(ticker: str) -> list[str]:
    safe = csv_safe_ticker(ticker)
    paths = []
    for exchange in EXCHANGES:
        raw_path = raw_daily_dir(exchange) / f"{safe}.csv"
        if raw_path.exists():
            paths.append(str(raw_path))
    return paths


def build_result(query: str) -> dict[str, object]:
    listings = read_csv(LISTING_EVENTS_FILE)
    aliases = read_csv(TICKER_ALIASES_FILE)
    securities = read_csv(SECURITY_MASTER_FILE)
    security_ids = find_matches(query, listings, aliases, securities)

    results = []
    for security_id in sorted(security_ids):
        security = securities[securities["security_id"].eq(security_id)] if not securities.empty else pd.DataFrame()
        listing_rows = listings[listings["security_id"].eq(security_id)].copy() if not listings.empty else pd.DataFrame()
        alias_rows = aliases[aliases["security_id"].eq(security_id)].copy() if not aliases.empty else pd.DataFrame()

        tickers = sorted(set(listing_rows["ticker"])) if not listing_rows.empty else []
        price_paths = []
        for ticker in tickers:
            price_paths.extend(price_paths_for_ticker(ticker))

        results.append(
            {
                "security_id": security_id,
                "issuer_name": security["issuer_name"].iloc[0] if not security.empty else "",
                "current_ticker": security["current_ticker"].iloc[0] if not security.empty else "",
                "primary_exchange": security["primary_exchange"].iloc[0] if not security.empty else "",
                "flags": classify_security(listing_rows) if not listing_rows.empty else ["reference_only"],
                "listings": listing_rows.to_dict("records"),
                "aliases": alias_rows.to_dict("records"),
                "price_paths": sorted(set(price_paths)),
            }
        )

    return {
        "query": query,
        "match_count": len(results),
        "matches": results,
    }


def print_human(result: dict[str, object]) -> None:
    print(f"query: {result['query']}")
    print(f"matches: {result['match_count']}")
    for match in result["matches"]:
        print()
        print(f"security_id: {match['security_id']}")
        print(f"issuer_name: {match['issuer_name']}")
        print(f"current_ticker: {match['current_ticker']}")
        print(f"primary_exchange: {match['primary_exchange']}")
        print(f"flags: {', '.join(match['flags'])}")
        print("listings:")
        for listing in match["listings"]:
            start = listing.get("start_date", "") or "?"
            end = listing.get("end_date", "") or "current"
            print(
                f"  - {listing.get('ticker', '')} / {listing.get('exchange', '')} "
                f"[{start} ~ {end}] {listing.get('event_type', '')} "
                f"listing_id={listing.get('listing_id', '')}"
            )
        if match["price_paths"]:
            print("price_csv:")
            for path in match["price_paths"]:
                print(f"  - {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve a ticker/name/security_id to security/listing IDs.")
    parser.add_argument("query", help="Ticker, security_id, or issuer-name text to search.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    if not LISTING_EVENTS_FILE.exists():
        raise SystemExit("reference tables are missing. Run: python src/build_reference.py")

    result = build_result(args.query)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result)


if __name__ == "__main__":
    main()

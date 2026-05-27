from __future__ import annotations

import argparse
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from common import EXCHANGES, ensure_project_dirs, exchange_key, ticker_file


NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
OTHER_EXCHANGE_CODES = {
    "nyse": "N",
    "amex": "A",
    "cboe": "Z",
    "iex": "V",
}
EXCHANGE_NAMES = {
    "nasdaq": "NASDAQ",
    "nyse": "NYSE",
    "amex": "AMEX",
    "cboe": "CBOE",
    "iex": "IEX",
}


def _read_symbol_directory(url: str) -> pd.DataFrame:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    lines = [
        line
        for line in response.text.splitlines()
        if line and not line.startswith("File Creation Time")
    ]
    if not lines:
        raise RuntimeError("NASDAQ symbol directory response was empty")
    return pd.read_csv(StringIO("\n".join(lines)), sep="|", dtype=str)


def _filter_common_rows(raw: pd.DataFrame, ticker_column: str) -> pd.DataFrame:
    filtered = raw.copy()
    filtered = filtered[filtered["Test Issue"].fillna("N").str.upper().eq("N")]
    filtered = filtered[filtered["ETF"].fillna("N").str.upper().eq("N")]
    filtered = filtered[~filtered[ticker_column].fillna("").str.contains(r"[\^\$]", regex=True)]
    special_name_pattern = r"\b(?:Warrant|Right|Rights|Unit|Units)\b"
    filtered = filtered[
        ~filtered["Security Name"].fillna("").str.contains(special_name_pattern, case=False, regex=True)
    ]
    return filtered


def fetch_current_nasdaq() -> pd.DataFrame:
    raw = _read_symbol_directory(NASDAQ_LISTED_URL)
    raw.columns = [col.strip() for col in raw.columns]

    filtered = _filter_common_rows(raw, "Symbol")

    collected_at = datetime.now(timezone.utc).isoformat()
    result = pd.DataFrame(
        {
            "ticker": filtered["Symbol"].str.strip(),
            "exchange": "NASDAQ",
            "security_name": filtered["Security Name"].str.strip(),
            "source": NASDAQ_LISTED_URL,
            "collected_at": collected_at,
        }
    )
    return result.dropna(subset=["ticker"]).drop_duplicates("ticker").sort_values("ticker")


def fetch_current_other(exchange: str) -> pd.DataFrame:
    exchange = exchange_key(exchange)
    raw = _read_symbol_directory(OTHER_LISTED_URL)
    raw.columns = [col.strip() for col in raw.columns]
    raw = raw[raw["Exchange"].fillna("").eq(OTHER_EXCHANGE_CODES[exchange])]
    filtered = _filter_common_rows(raw, "ACT Symbol")

    collected_at = datetime.now(timezone.utc).isoformat()
    result = pd.DataFrame(
        {
            "ticker": filtered["ACT Symbol"].str.strip(),
            "exchange": EXCHANGE_NAMES[exchange],
            "security_name": filtered["Security Name"].str.strip(),
            "source": OTHER_LISTED_URL,
            "collected_at": collected_at,
        }
    )
    return result.dropna(subset=["ticker"]).drop_duplicates("ticker").sort_values("ticker")


def fetch_current_exchange(exchange: str) -> pd.DataFrame:
    exchange = exchange_key(exchange)
    if exchange == "nasdaq":
        return fetch_current_nasdaq()
    return fetch_current_other(exchange)


def load_extra_tickers(path: Path) -> pd.DataFrame:
    extra = pd.read_csv(path, dtype=str)
    required = {"ticker", "exchange", "security_name", "source", "collected_at"}
    missing = required.difference(extra.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")
    return extra[list(required)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch current exchange common-stock tickers.")
    parser.add_argument("--exchange", choices=EXCHANGES, default="nasdaq")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--extra",
        type=Path,
        action="append",
        default=[],
        help="Optional CSV with historical or delisted tickers to append.",
    )
    args = parser.parse_args()

    exchange = exchange_key(args.exchange)
    output = args.output or ticker_file(exchange)

    ensure_project_dirs(exchange)
    frames = [fetch_current_exchange(exchange)]
    frames.extend(load_extra_tickers(path) for path in args.extra)

    universe = pd.concat(frames, ignore_index=True)
    universe = universe.dropna(subset=["ticker"]).drop_duplicates("ticker").sort_values("ticker")
    output.parent.mkdir(parents=True, exist_ok=True)
    universe.to_csv(output, index=False, encoding="utf-8")
    print(f"saved {len(universe):,} {exchange} tickers to {output}")


if __name__ == "__main__":
    main()

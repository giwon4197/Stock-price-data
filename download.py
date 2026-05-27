"""
Yahoo Finance 일봉 OHLCV 데이터를 저장/증분 갱신하는 스크립트.

핵심 원칙:
- 기존 CSV는 삭제하지 않는다.
- 이미 저장된 마지막 날짜를 기준으로 부족한 구간만 추가로 요청한다.
- 날짜 중복은 제거하고 시간 순서를 유지한다.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable
from urllib.parse import quote

import pandas as pd
import requests


# 파일명 -> Yahoo Finance 심볼
# 파일명은 사용자가 바꾼 티커형 이름을 기준으로 맞춘다.
SYMBOLS: Dict[str, str] = {
    "btcusdt": "BTC-USD",
    "ethusdt": "ETH-USD",
    "000660": "000660.KS",
    "005930": "005930.KS",
    "kospi": "^KS11",
    "kosdaq": "^KQ11",
    "nasdaq": "^IXIC",
    "sp500": "^GSPC",
    "soxl": "SOXL",
}

# 예전 파일명 또는 오타 파일명을 새 기준으로 옮기기 위한 별칭.
# 기존 데이터를 지우지 않고 이름만 정리한다.
LEGACY_FILE_NAMES: Dict[str, str] = {
    "bitcoin_usd": "btcusdt",
    "ethereum_usd": "ethusdt",
    "sk_hynix": "000660",
    "samsung_electronics": "005930",
    "nasq": "nasdaq",
    "nasdaq_composite": "nasdaq",
    "spy": "sp500",
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


def parse_date(date_text: str) -> datetime:
    """YYYY-MM-DD 문자열을 UTC datetime으로 바꾼다."""
    return datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def format_date(value: date | datetime | str) -> str:
    """date/datetime/문자열을 YYYY-MM-DD 문자열로 통일한다."""
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def to_unix_seconds(date_time: datetime) -> int:
    """Yahoo Finance API가 요구하는 Unix timestamp 초 단위로 바꾼다."""
    return int(date_time.timestamp())


def get_default_end_date() -> str:
    """Yahoo의 period2가 미포함 경계라서 내일 날짜를 기본 종료일로 사용한다."""
    return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()


def normalize_existing_file_names(output_dir: Path) -> None:
    """예전 파일명/오타 파일명을 현재 기준 파일명으로 정리한다."""
    for old_name, new_name in LEGACY_FILE_NAMES.items():
        old_path = output_dir / f"{old_name}.csv"
        new_path = output_dir / f"{new_name}.csv"

        if not old_path.exists():
            continue

        if new_path.exists():
            print(f"skip rename {old_path.name}: {new_path.name} already exists")
            continue

        old_path.rename(new_path)
        print(f"renamed {old_path.name} -> {new_path.name}")


def read_existing_data(csv_path: Path) -> pd.DataFrame:
    """기존 CSV를 읽는다. 없으면 빈 DataFrame을 반환한다."""
    if not csv_path.exists():
        return pd.DataFrame()

    data = pd.read_csv(csv_path, parse_dates=["date"])
    data["date"] = pd.to_datetime(data["date"]).dt.date
    return data


def get_fetch_start_date(existing_data: pd.DataFrame, fallback_start: str) -> str:
    """기존 마지막 날짜부터 다시 받아 중복 제거로 안전하게 병합한다."""
    if existing_data.empty:
        return fallback_start

    last_date = max(existing_data["date"])
    return format_date(last_date)


def fetch_daily_chart(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Yahoo Finance chart API에서 특정 심볼의 일봉 데이터를 가져온다."""
    period1 = to_unix_seconds(parse_date(start_date))
    period2 = to_unix_seconds(parse_date(end_date))
    encoded_symbol = quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
    params = {
        "period1": period1,
        "period2": period2,
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    }

    response = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=30)
    if response.status_code == 429:
        # Yahoo가 요청을 잠시 제한할 수 있어 한 번 쉬고 재시도한다.
        time.sleep(10)
        response = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    payload = response.json()

    chart = payload.get("chart", {})
    error = chart.get("error")
    if error:
        raise RuntimeError(f"Yahoo Finance API error for {symbol}: {error}")

    results = chart.get("result") or []
    if not results:
        return pd.DataFrame()

    result = results[0]
    timestamps = result.get("timestamp") or []
    quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
    adjusted = (result.get("indicators", {}).get("adjclose") or [{}])[0]

    data = pd.DataFrame(
        {
            "date": pd.to_datetime(timestamps, unit="s", utc=True).date,
            "open": quote_data.get("open"),
            "high": quote_data.get("high"),
            "low": quote_data.get("low"),
            "close": quote_data.get("close"),
            "adj_close": adjusted.get("adjclose"),
            "volume": quote_data.get("volume"),
        }
    )
    data.insert(0, "symbol", symbol)
    return data.dropna(subset=["date", "open", "high", "low", "close"])


def merge_daily_data(existing_data: pd.DataFrame, new_data: pd.DataFrame) -> pd.DataFrame:
    """기존 데이터와 새 데이터를 합치고 날짜 중복을 제거한다."""
    frames = [frame for frame in [existing_data, new_data] if not frame.empty]
    if not frames:
        return pd.DataFrame(
            columns=["symbol", "date", "open", "high", "low", "close", "adj_close", "volume"]
        )

    merged = pd.concat(frames, ignore_index=True)
    merged["date"] = pd.to_datetime(merged["date"]).dt.date
    merged = merged.drop_duplicates(subset=["date"], keep="last")
    merged = merged.sort_values("date").reset_index(drop=True)
    return merged


def update_symbol_data(
    output_dir: Path,
    name: str,
    symbol: str,
    fallback_start: str,
    end_date: str,
) -> Path:
    """한 심볼 CSV를 기존 데이터 이후 구간만 받아 갱신한다."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{name}.csv"

    existing_data = read_existing_data(output_path)
    fetch_start = get_fetch_start_date(existing_data, fallback_start)

    print(f"[{name}] {symbol} update: {fetch_start} -> {end_date}")
    new_data = fetch_daily_chart(symbol, fetch_start, end_date)
    merged = merge_daily_data(existing_data, new_data)

    merged.to_csv(output_path, index=False)
    added_count = max(len(merged) - len(existing_data), 0)
    print(f"[{name}] saved {len(merged):,} rows (+{added_count:,}) -> {output_path}")
    return output_path


def write_metadata(
    output_dir: Path,
    symbols: Dict[str, str],
    start_date: str,
    end_date: str,
    saved_files: Iterable[Path],
) -> None:
    """데이터 수집 조건을 추적할 수 있도록 메타데이터를 저장한다."""
    metadata = {
        "source": "Yahoo Finance chart API",
        "interval": "1d",
        "mode": "incremental",
        "start_date": start_date,
        "end_date": end_date,
        "symbols": symbols,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": [str(path.as_posix()) for path in saved_files],
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"saved metadata -> {metadata_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Incrementally update daily OHLCV datasets from Yahoo Finance."
    )
    parser.add_argument("--start", default="2010-01-01", help="Start date for new files: YYYY-MM-DD")
    parser.add_argument(
        "--end",
        default=get_default_end_date(),
        help="End date: YYYY-MM-DD. Yahoo treats this as an exclusive boundary.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/raw/yahoo",
        help="Directory where CSV files will be written.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    normalize_existing_file_names(output_dir)

    saved_files = []
    for name, symbol in SYMBOLS.items():
        saved_files.append(
            update_symbol_data(
                output_dir=output_dir,
                name=name,
                symbol=symbol,
                fallback_start=args.start,
                end_date=args.end,
            )
        )

    write_metadata(output_dir, SYMBOLS, args.start, args.end, saved_files)


if __name__ == "__main__":
    main()
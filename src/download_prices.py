from __future__ import annotations

import argparse
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from common import (
    DB_PRICE_COLUMNS,
    EXCHANGES,
    LEGACY_RAW_DAILY_DIR,
    OHLCV_COLUMNS,
    csv_safe_ticker,
    current_listing_file,
    ensure_project_dirs,
    exchange_key,
    failed_log_file,
    raw_daily_dir,
    ticker_file,
    yahoo_symbol,
)


def _empty_failure_log() -> pd.DataFrame:
    return pd.DataFrame(columns=["ticker", "exchange", "error_message", "failed_at", "retry_count"])


def _normalize_download(
    df: pd.DataFrame,
    ticker: str,
    exchange: str,
    security_id: str,
    listing_id: str,
    downloaded_at: str,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=DB_PRICE_COLUMNS)

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
    renamed["security_id"] = security_id
    renamed["listing_id"] = listing_id
    renamed["ticker"] = ticker
    renamed["exchange"] = exchange
    renamed["source"] = "Yahoo Finance"
    renamed["downloaded_at"] = downloaded_at

    for col in OHLCV_COLUMNS:
        renamed[col] = pd.to_numeric(renamed[col], errors="coerce")

    return renamed[DB_PRICE_COLUMNS].sort_values("date")


def download_one(ticker: str, exchange: str = "", security_id: str = "", listing_id: str = "") -> pd.DataFrame:
    downloaded_at = datetime.now(timezone.utc).isoformat()
    data = yf.download(
        yahoo_symbol(ticker),
        period="max",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    return _normalize_download(
        data,
        ticker=ticker,
        exchange=exchange,
        security_id=security_id,
        listing_id=listing_id,
        downloaded_at=downloaded_at,
    )


def download_with_retries(
    ticker: str,
    exchange: str,
    security_id: str,
    listing_id: str,
    output: Path,
    retries: int,
    sleep_seconds: float,
) -> dict[str, object] | None:
    last_error = ""
    for retry_count in range(retries + 1):
        try:
            prices = download_one(ticker, exchange=exchange, security_id=security_id, listing_id=listing_id)
            if prices.empty:
                raise RuntimeError("empty data")
            output.parent.mkdir(parents=True, exist_ok=True)
            prices.to_csv(output, index=False, encoding="utf-8")
            print(f"saved {ticker}: {len(prices):,} rows")
            return None
        except Exception as exc:
            last_error = str(exc)
            if retry_count < retries:
                time.sleep(sleep_seconds * (retry_count + 1))

    print(f"failed {ticker}: {last_error}")
    return {
        "ticker": ticker,
        "exchange": exchange,
        "error_message": last_error,
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "retry_count": retries,
    }


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def print_progress(done: int, total: int, failed: int, skipped: int, started_at: float) -> None:
    elapsed = time.monotonic() - started_at
    active_done = max(1, done - skipped)
    remaining = max(0, total - done)
    seconds_per_item = elapsed / active_done
    eta = seconds_per_item * remaining
    percent = (done / total * 100) if total else 100.0
    print(
        f"progress {done:,}/{total:,} ({percent:.1f}%) | "
        f"failed {failed:,} | skipped {skipped:,} | "
        f"elapsed {format_duration(elapsed)} | eta {format_duration(eta)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Download max daily Yahoo Finance prices by ticker.")
    parser.add_argument("--exchange", choices=EXCHANGES, default="nasdaq")
    parser.add_argument("--tickers", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--failed-log", type=Path, default=None)
    parser.add_argument("--sleep", type=float, default=1.5)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1, help="Parallel downloads. Capped at 6.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Redownload files that already exist.")
    args = parser.parse_args()

    exchange = exchange_key(args.exchange)
    reference_tickers_path = current_listing_file(exchange)
    tickers_path = args.tickers or (reference_tickers_path if reference_tickers_path.exists() else ticker_file(exchange))
    output_dir = args.output_dir or raw_daily_dir(exchange)
    failed_log = args.failed_log or failed_log_file(exchange)

    ensure_project_dirs(exchange)
    universe = pd.read_csv(tickers_path, dtype=str)
    if args.limit is not None:
        universe = universe.head(args.limit)

    workers = max(1, min(args.workers, 6))
    failures: list[dict[str, object]] = []
    jobs: list[tuple[str, str, str, str, Path]] = []
    skipped = 0
    for row in universe.itertuples(index=False):
        ticker = str(row.ticker).strip()
        row_exchange = str(getattr(row, "exchange", "")).strip()
        security_id = str(getattr(row, "security_id", "")).strip()
        listing_id = str(getattr(row, "listing_id", "")).strip()
        output = output_dir / f"{csv_safe_ticker(ticker)}.csv"
        legacy_output = LEGACY_RAW_DAILY_DIR / f"{csv_safe_ticker(ticker)}.csv"

        if output.exists() and not args.force:
            print(f"skip existing {ticker}")
            skipped += 1
            continue
        if exchange == "nasdaq" and args.output_dir is None and legacy_output.exists() and not args.force:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_output, output)
            print(f"copy legacy existing {ticker}")
            skipped += 1
            continue

        jobs.append((ticker, row_exchange, security_id, listing_id, output))

    total = len(jobs) + skipped
    done = skipped
    started_at = time.monotonic()
    print(
        f"download queue: total {total:,}, pending {len(jobs):,}, "
        f"skipped {skipped:,}, workers {workers}"
    )
    if skipped:
        print_progress(done, total, len(failures), skipped, started_at)

    if not jobs:
        print("no pending downloads")
    elif workers == 1:
        for ticker, row_exchange, security_id, listing_id, output in jobs:
            failure = download_with_retries(ticker, row_exchange, security_id, listing_id, output, args.retries, args.sleep)
            if failure:
                failures.append(failure)
            done += 1
            print_progress(done, total, len(failures), skipped, started_at)
            time.sleep(args.sleep)
    else:
        print(f"downloading with {workers} workers")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    download_with_retries,
                    ticker,
                    row_exchange,
                    security_id,
                    listing_id,
                    output,
                    args.retries,
                    args.sleep,
                ): ticker
                for ticker, row_exchange, security_id, listing_id, output in jobs
            }
            for future in as_completed(futures):
                failure = future.result()
                if failure:
                    failures.append(failure)
                done += 1
                print_progress(done, total, len(failures), skipped, started_at)
                time.sleep(args.sleep)

    failed = pd.DataFrame(failures) if failures else _empty_failure_log()
    failed_log.parent.mkdir(parents=True, exist_ok=True)
    failed.to_csv(failed_log, index=False, encoding="utf-8")
    print(f"saved failure log to {failed_log}")


if __name__ == "__main__":
    main()

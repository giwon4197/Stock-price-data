from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
EXCHANGES = ("nasdaq", "nyse", "amex", "cboe", "iex")


def run_step(command: list[str]) -> None:
    print()
    print(f"> {' '.join(command)}")
    completed = subprocess.run(command, cwd=ROOT_DIR)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def parse_exchanges(value: str) -> list[str]:
    if value.strip().lower() == "all":
        return list(EXCHANGES)
    exchanges = [part.strip().lower() for part in value.split(",") if part.strip()]
    invalid = sorted(set(exchanges).difference(EXCHANGES))
    if invalid:
        raise argparse.ArgumentTypeError(f"unsupported exchange(s): {', '.join(invalid)}")
    return exchanges


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the stock and index daily price dataset pipeline.")
    parser.add_argument(
        "--exchanges",
        type=parse_exchanges,
        default=list(EXCHANGES),
        help="Comma-separated exchanges or all. Choices: nasdaq,nyse,amex,cboe,iex.",
    )
    parser.add_argument("--workers", type=int, default=6, help="Parallel downloads, capped by download_prices.py.")
    parser.add_argument("--force", action="store_true", help="Redownload existing ticker CSV files.")
    parser.add_argument("--limit", type=int, default=None, help="Optional ticker limit for testing.")
    parser.add_argument("--sleep", type=float, default=1.5, help="Sleep seconds between completed downloads.")
    parser.add_argument("--retries", type=int, default=3, help="Retry count for each ticker.")
    parser.add_argument("--postprocess", action="store_true", help="Run validation and metadata after downloads.")
    parser.add_argument("--parquet", action="store_true", help="Run parquet merge after postprocess.")
    parser.add_argument("--sqlite", action="store_true", help="Export normalized DB tables to SQLite.")
    parser.add_argument("--skip-reference", action="store_true", help="Skip security/listing reference table build.")
    parser.add_argument("--skip-index", action="store_true", help="Skip major index downloads.")
    args = parser.parse_args()

    python = sys.executable
    steps = []
    for exchange in args.exchanges:
        steps.append([python, "src/fetch_tickers.py", "--exchange", exchange])

    if not args.skip_reference:
        steps.append([python, "src/build_reference.py", "--exchanges", *args.exchanges])

    for exchange in args.exchanges:
        download_command = [
            python,
            "src/download_prices.py",
            "--exchange",
            exchange,
            "--workers",
            str(args.workers),
            "--sleep",
            str(args.sleep),
            "--retries",
            str(args.retries),
        ]
        if args.force:
            download_command.append("--force")
        if args.limit is not None:
            download_command.extend(["--limit", str(args.limit)])
        steps.append(download_command)

    if args.postprocess or args.parquet:
        for exchange in args.exchanges:
            steps.append([python, "src/validate_prices.py", "--exchange", exchange])

        for exchange in args.exchanges:
            steps.append([python, "src/build_metadata.py", "--exchange", exchange])

    if args.parquet:
        for exchange in args.exchanges:
            steps.append([python, "src/merge_to_parquet.py", "--exchange", exchange])

    if not args.skip_index:
        index_command = [python, "src/download_indices.py"]
        if args.force:
            index_command.append("--force")
        steps.append(index_command)

    if args.sqlite:
        steps.append([python, "src/export_sqlite.py"])

    for step in steps:
        run_step(step)

    print()
    print("Pipeline complete.")


if __name__ == "__main__":
    main()

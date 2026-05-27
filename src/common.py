from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
TICKERS_DIR = DATA_DIR / "tickers"
EXCHANGES = ("nasdaq", "nyse", "amex", "cboe", "iex")
DEFAULT_EXCHANGE = "nasdaq"
RAW_DAILY_DIR = DATA_DIR / "raw" / DEFAULT_EXCHANGE / "daily"
LEGACY_RAW_DAILY_DIR = DATA_DIR / "raw" / "daily"
INDEX_DAILY_DIR = DATA_DIR / "index" / "daily"
METADATA_DIR = DATA_DIR / "metadata"
PROCESSED_DIR = DATA_DIR / "processed"
LOGS_DIR = ROOT_DIR / "logs"


PRICE_COLUMNS = [
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "source",
    "downloaded_at",
]


def exchange_key(exchange: str) -> str:
    key = exchange.strip().lower()
    if key not in EXCHANGES:
        raise ValueError(f"unsupported exchange: {exchange}")
    return key


def ticker_file(exchange: str) -> Path:
    return TICKERS_DIR / f"{exchange_key(exchange)}_universe.csv"


def raw_daily_dir(exchange: str) -> Path:
    return DATA_DIR / "raw" / exchange_key(exchange) / "daily"


def failed_log_file(exchange: str) -> Path:
    return LOGS_DIR / f"{exchange_key(exchange)}_download_failed.csv"


def validation_report_file(exchange: str) -> Path:
    return LOGS_DIR / f"{exchange_key(exchange)}_validation_report.csv"


def metadata_file(exchange: str) -> Path:
    return METADATA_DIR / f"{exchange_key(exchange)}_ticker_summary.csv"


def parquet_file(exchange: str) -> Path:
    return PROCESSED_DIR / f"{exchange_key(exchange)}_daily_all.parquet"


def ensure_project_dirs(exchange: str | None = None) -> None:
    raw_dir = raw_daily_dir(exchange or DEFAULT_EXCHANGE)
    for path in [
        TICKERS_DIR,
        raw_dir,
        INDEX_DAILY_DIR,
        METADATA_DIR,
        PROCESSED_DIR,
        LOGS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def yahoo_symbol(ticker: str) -> str:
    return ticker.strip().replace(".", "-")


def csv_safe_ticker(ticker: str) -> str:
    safe = ticker.strip().replace("/", "-").replace("\\", "-")
    return safe.replace(":", "-")


def daily_csv_files(input_dir: Path, include_legacy: bool = False) -> list[Path]:
    files: dict[str, Path] = {}
    if include_legacy and LEGACY_RAW_DAILY_DIR.exists():
        files.update({path.name: path for path in LEGACY_RAW_DAILY_DIR.glob("*.csv")})
    if input_dir.exists():
        files.update({path.name: path for path in input_dir.glob("*.csv")})
    return [files[name] for name in sorted(files)]

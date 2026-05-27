CREATE TABLE IF NOT EXISTS securities (
    security_id TEXT PRIMARY KEY,
    issuer_name TEXT NOT NULL,
    current_ticker TEXT NOT NULL,
    primary_exchange TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listings (
    listing_id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL REFERENCES securities(security_id),
    ticker TEXT NOT NULL,
    exchange TEXT NOT NULL,
    security_name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    event_type TEXT NOT NULL,
    is_current INTEGER NOT NULL,
    source TEXT NOT NULL,
    collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticker_aliases (
    alias_id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL REFERENCES securities(security_id),
    ticker TEXT NOT NULL,
    exchange TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    source TEXT NOT NULL,
    confidence TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_prices (
    price_date TEXT NOT NULL,
    security_id TEXT NOT NULL DEFAULT '',
    listing_id TEXT NOT NULL DEFAULT '',
    ticker TEXT NOT NULL,
    exchange TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    adj_close REAL,
    volume REAL,
    source TEXT NOT NULL,
    downloaded_at TEXT NOT NULL,
    PRIMARY KEY (price_date, ticker, security_id, listing_id)
);

CREATE TABLE IF NOT EXISTS index_daily_prices (
    price_date TEXT NOT NULL,
    index_id TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    adj_close REAL,
    volume REAL,
    source TEXT NOT NULL,
    downloaded_at TEXT NOT NULL,
    PRIMARY KEY (price_date, index_id)
);

CREATE INDEX IF NOT EXISTS idx_listings_ticker_exchange ON listings(ticker, exchange);
CREATE INDEX IF NOT EXISTS idx_listings_security_id ON listings(security_id);
CREATE INDEX IF NOT EXISTS idx_daily_prices_security_date ON daily_prices(security_id, price_date);
CREATE INDEX IF NOT EXISTS idx_daily_prices_ticker_date ON daily_prices(ticker, price_date);

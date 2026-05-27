# DB Export

This project now keeps ticker symbols separate from the durable security identity used for database analysis.

## Tables

`securities`

- One row per inferred security.
- `security_id` is the stable project key.
- Current ticker and exchange are descriptive fields, not permanent identifiers.

`listings`

- One row per ticker/exchange listing event.
- A security can have multiple listing rows when a ticker changes, an exchange changes, or a company relists.
- `start_date` and `end_date` are blank when the public source does not provide reliable dates.

`ticker_aliases`

- Ticker history/alias table for joining old symbols to a security.
- Current symbol-directory rows are marked with `confidence = symbol_directory_current`.
- Manually confirmed rows can be added with `confidence = manual`.

`daily_prices`

- Daily OHLCV stock data.
- Includes both `ticker` and `security_id`.
- Use `security_id` for long-run company/security analysis, and `ticker` only as the observed market symbol for that row.

`index_daily_prices`

- Daily OHLCV index data such as S&P 500 and Nasdaq 100.

## Manual Corrections

Automatic detection is limited by the public source data. Yahoo Finance can provide prices, but it does not provide a complete corporate-action identity ledger.

Add confirmed ticker changes, relistings, and ticker reuse cases to:

```text
data/reference/manual_overrides.csv
```

Required columns:

```text
security_id,ticker,exchange,security_name,issuer_name,start_date,end_date,event_type,is_current,status,source,collected_at,confidence
```

Example for a ticker change:

```csv
security_id,ticker,exchange,security_name,issuer_name,start_date,end_date,event_type,is_current,status,source,collected_at,confidence
sec_meta_platforms,FB,NASDAQ,Meta Platforms Inc.,Meta Platforms Inc.,2012-05-18,2022-06-08,ticker_change,false,active,manual,,manual
sec_meta_platforms,META,NASDAQ,Meta Platforms Inc.,Meta Platforms Inc.,2022-06-09,,ticker_change,true,active,manual,,manual
```

Example for ticker reuse:

```csv
security_id,ticker,exchange,security_name,issuer_name,start_date,end_date,event_type,is_current,status,source,collected_at,confidence
sec_old_xyz,XYZ,NASDAQ,Old XYZ Corp.,Old XYZ Corp.,2000-01-01,2008-12-31,delisted,false,inactive,manual,,manual
sec_new_xyz,XYZ,NASDAQ,New XYZ Inc.,New XYZ Inc.,2021-04-15,,reused_ticker,true,active,manual,,manual
```

## Commands

Build reference tables:

```powershell
python src/build_reference.py
```

Export SQLite database:

```powershell
python src/export_sqlite.py
```

Run the full pipeline and export SQLite:

```powershell
python run_pipeline.py --sqlite
```

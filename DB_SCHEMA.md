# DB Schema

이 프로젝트의 DB는 가격 데이터와 종목 정체성을 분리한다.

티커는 바뀔 수 있고, 재사용될 수 있고, 거래소 이전으로 같은 회사가 다른 exchange에 나타날 수 있다. 그래서 분석 기준은 `ticker`가 아니라 `security_id`다.

## Core Idea

```text
security_id
= 같은 회사/종목을 장기적으로 추적하기 위한 안정적인 ID

listing_id
= 특정 ticker + exchange + 기간을 나타내는 listing 이벤트 ID

ticker
= 가격 CSV에서 관측된 시장 심볼
```

원본 가격 CSV는 `data/raw`에 보존하고, DB export 과정에서 reference 테이블을 이용해 각 가격 row에 `security_id`와 `listing_id`를 붙인다.

## Tables

### securities

하나의 `security_id`당 한 줄을 가진 종목 마스터 테이블이다.

주요 컬럼:

```text
security_id
issuer_name
current_ticker
primary_exchange
status
source
collected_at
```

사용법:

- 장기 분석의 기본 join key는 `security_id`다.
- `current_ticker`는 현재 설명용 값이지 영구 식별자가 아니다.

### listings

티커와 거래소의 기간별 이력을 나타낸다.

주요 컬럼:

```text
listing_id
security_id
ticker
exchange
security_name
start_date
end_date
event_type
is_current
source
collected_at
```

사용법:

- 같은 `security_id`가 여러 listing을 가질 수 있다.
- 티커 변경, 거래소 이전, 재상장, 상장폐지는 모두 listing row로 표현한다.
- `start_date`와 `end_date`가 있으면 가격 row 매핑 때 날짜 범위로 사용한다.

### ticker_aliases

과거 티커와 현재 티커를 연결하기 위한 alias 테이블이다.

주요 컬럼:

```text
alias_id
security_id
ticker
exchange
valid_from
valid_to
source
confidence
```

사용법:

- 사용자가 과거 티커로 검색해도 같은 `security_id`를 찾을 수 있게 한다.
- `confidence`로 자동 생성인지, 사람이 확인한 값인지 구분한다.

### daily_prices

개별 주식의 일봉 가격 테이블이다.

주요 컬럼:

```text
price_date
security_id
listing_id
ticker
exchange
open
high
low
close
adj_close
volume
source
downloaded_at
```

사용법:

- 가격 자체는 Yahoo Finance 원본 CSV에서 온다.
- `security_id`와 `listing_id`는 export 단계에서 reference를 기준으로 붙는다.
- 장기 분석은 `security_id`, 당시 시장 심볼 분석은 `ticker`를 사용한다.

### index_daily_prices

S&P 500, Nasdaq 100 같은 지수 일봉 가격 테이블이다.

주요 컬럼:

```text
price_date
index_id
open
high
low
close
adj_close
volume
source
downloaded_at
```

## Manual Corrections

자동 데이터만으로는 상장 이벤트를 완벽하게 알 수 없다. Yahoo Finance는 가격 데이터 제공처이고, 완전한 corporate action ledger가 아니다.

확인된 예외는 아래 파일에 적는다.

```text
data/reference/manual_overrides.csv
```

필수 컬럼:

```text
security_id,ticker,exchange,security_name,issuer_name,start_date,end_date,event_type,is_current,status,source,collected_at,confidence
```

## Event Types

권장 `event_type` 값:

```text
current_listing
exchange_transfer
ticker_change
delisted
relisted
reused_ticker
manual_listing
```

예시 의미:

```text
ticker_change
= 같은 회사가 티커를 바꾼 경우

exchange_transfer
= 같은 회사가 거래소를 이동한 경우

reused_ticker
= 과거에 다른 회사가 쓰던 티커를 새 회사가 다시 쓰는 경우

relisted
= 상장폐지 후 다시 상장한 경우
```

## Examples

티커 변경:

```csv
security_id,ticker,exchange,security_name,issuer_name,start_date,end_date,event_type,is_current,status,source,collected_at,confidence
sec_meta_platforms,FB,NASDAQ,Meta Platforms Inc.,Meta Platforms Inc.,2012-05-18,2022-06-08,ticker_change,false,active,manual,,manual
sec_meta_platforms,META,NASDAQ,Meta Platforms Inc.,Meta Platforms Inc.,2022-06-09,,ticker_change,true,active,manual,,manual
```

거래소 이전:

```csv
security_id,ticker,exchange,security_name,issuer_name,start_date,end_date,event_type,is_current,status,source,collected_at,confidence
sec_example,AABC,NASDAQ,Example Corp.,Example Corp.,2018-01-01,2022-04-30,exchange_transfer,false,active,manual,,manual
sec_example,AABC,NYSE,Example Corp.,Example Corp.,2022-05-01,,exchange_transfer,true,active,manual,,manual
```

티커 재사용:

```csv
security_id,ticker,exchange,security_name,issuer_name,start_date,end_date,event_type,is_current,status,source,collected_at,confidence
sec_old_xyz,XYZ,NASDAQ,Old XYZ Corp.,Old XYZ Corp.,2000-01-01,2008-12-31,delisted,false,inactive,manual,,manual
sec_new_xyz,XYZ,NASDAQ,New XYZ Inc.,New XYZ Inc.,2021-04-15,,reused_ticker,true,active,manual,,manual
```

## Rebuild Commands

reference 재생성:

```powershell
python src/build_reference.py
```

전용 실행 파일:

```powershell
.\run_reference.ps1
```

reference 재생성 후 SQLite 반영:

```powershell
.\run_reference.ps1 -Sqlite
```

SQLite 재생성:

```powershell
python src/export_sqlite.py
```

전체 파이프라인:

```powershell
python run_pipeline.py --exchanges all --postprocess --parquet --sqlite
```

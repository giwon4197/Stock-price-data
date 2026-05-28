# Project Task

## 목표

미국 주식 일봉 데이터를 수집하고, 티커만으로는 구분하기 어려운 종목 이력을 깔끔하게 관리한다.

단순히 현재 NASDAQ 티커만 모으는 것이 목표가 아니다. 티커 변경, 거래소 이전, 재상장, 티커 재사용 같은 사건을 추적해서 분석할 때 같은 회사와 다른 회사를 구분할 수 있게 만드는 것이 목표다.

## 현재 원칙

- 원본 가격 CSV는 `data/raw`에 보존한다.
- 원본 CSV를 직접 수정하지 않는다.
- 이상 티커 처리는 `data/reference/manual_overrides.csv`에 기록한다.
- 최종 분석에서는 `ticker`보다 `security_id`를 우선 사용한다.
- `data/processed` 산출물은 언제든 다시 만들 수 있는 결과물로 본다.

## 해결해야 하는 주요 케이스

1. NASDAQ 이탈 후 NASDAQ 복귀
   - 같은 회사가 NASDAQ 밖으로 나갔다가 다시 돌아온 경우
   - 중간 기간 가격 데이터도 같은 `security_id`로 연결해야 한다.

2. 거래소 완전 이전
   - 예: NASDAQ에서 NYSE로 이동
   - 회사가 같다면 `security_id`는 유지하고, `listing_id`만 기간별로 나눈다.

3. 티커 변경
   - 예: 기존 티커 A에서 새 티커 B로 변경
   - 같은 회사라면 하나의 `security_id` 아래에 여러 listing/alias를 둔다.

4. 티커 재사용
   - 과거 회사 A가 쓰던 티커를 나중에 회사 B가 다시 쓰는 경우
   - 이 경우는 반드시 서로 다른 `security_id`로 분리해야 한다.

5. 상장폐지, 재상장, M&A
   - 가격 시계열이 끊기거나 회사 정체성이 바뀔 수 있으므로 manual 검토가 필요하다.

## 데이터 구조

```text
data/tickers/
  현재 거래소별 티커 universe

data/raw/{exchange}/daily/
  원본 가격 CSV

data/reference/manual_overrides.csv
  사람이 확인한 예외 장부

data/reference/security_master.csv
  security_id 단위 종목 마스터

data/reference/listing_events.csv
  ticker/exchange/date-range 단위 listing 이력

data/reference/ticker_aliases.csv
  과거 티커와 현재 티커를 연결하는 alias 테이블

data/metadata/
  티커별 데이터 요약

data/processed/
  parquet, sqlite 등 재생성 가능한 산출물
```

## 스크립트 역할

`src/fetch_tickers.py`

- NASDAQ Trader Symbol Directory에서 현재 티커 목록을 가져온다.
- NASDAQ, NYSE, AMEX, CBOE, IEX를 거래소별로 저장한다.

`src/build_reference.py`

- 현재 티커 목록과 `manual_overrides.csv`를 합쳐 reference 테이블을 만든다.
- manual row가 현재 listing으로 지정된 경우 자동 생성 row보다 우선한다.

`src/download_prices.py`

- Yahoo Finance에서 티커별 일봉 가격 데이터를 다운로드한다.
- 결과는 `data/raw/{exchange}/daily/*.csv`에 저장한다.

`src/validate_prices.py`

- 가격 CSV의 결측, 중복 날짜, OHLC 오류, 음수 가격/거래량을 검사한다.

`src/build_metadata.py`

- 티커별 첫 날짜, 마지막 날짜, row 수, 데이터 기간, 상태를 요약한다.

`src/merge_to_parquet.py`

- 거래소별 raw CSV를 parquet로 병합한다.

`src/export_sqlite.py`

- reference 테이블과 가격 데이터를 SQLite로 내보낸다.
- 가격 row의 날짜를 기준으로 적절한 `security_id`와 `listing_id`를 붙인다.

`src/ticker_lookup.py`

- 티커, 회사명, security_id로 reference 정보를 조회한다.

## 작업 순서

기본 reference 재생성:

```powershell
python src/build_reference.py
```

또는 전용 실행 파일:

```powershell
.\run_reference.ps1
```

reference 재생성 후 SQLite까지 반영:

```powershell
.\run_reference.ps1 -Sqlite
```

가격 다운로드:

```powershell
python src/download_prices.py --exchange nasdaq
```

검증과 요약:

```powershell
python src/validate_prices.py --exchange nasdaq
python src/build_metadata.py --exchange nasdaq
```

SQLite 생성:

```powershell
python src/export_sqlite.py
```

parquet 생성:

```powershell
.\run_parquet.ps1
```

지수 parquet을 제외하려면:

```powershell
.\run_parquet.ps1 -SkipIndex
```

전체 실행:

```powershell
python run_pipeline.py --exchanges all --postprocess --parquet --sqlite
```

## Manual Override 작성 규칙

`manual_overrides.csv` 한 줄은 하나의 listing 사건을 뜻한다.

필수 컬럼:

```text
security_id,ticker,exchange,security_name,issuer_name,start_date,end_date,event_type,is_current,status,source,collected_at,confidence
```

권장 `event_type`:

```text
current_listing
exchange_transfer
ticker_change
delisted
relisted
reused_ticker
manual_listing
```

권장 `status`:

```text
active
inactive
merged
unknown
```

작성 규칙:

- 같은 회사의 티커 변경은 같은 `security_id`를 사용한다.
- 다른 회사가 같은 티커를 재사용한 경우는 다른 `security_id`를 사용한다.
- 현재 유효한 listing은 `is_current=true`로 둔다.
- 종료된 listing은 `end_date`를 채우고 `is_current=false`로 둔다.
- 날짜를 모르면 빈 값으로 두되 `confidence`에 불확실성을 표시한다.

## 다음 작업

- 이상 티커 후보 목록 만들기
- 후보별로 실제 회사 이력 확인
- `manual_overrides.csv`에 확정 케이스 추가
- `build_reference.py`와 `export_sqlite.py`로 결과 재생성
- `ticker_lookup.py`로 사람이 보기 좋은지 확인

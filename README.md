# Stock Price Data

Yahoo Finance와 NASDAQ Trader Symbol Directory를 이용해 미국 주식의 일봉 가격 데이터를 수집하고, 티커 변경/거래소 이전/재상장/티커 재사용 같은 예외를 따로 관리하는 프로젝트입니다.

핵심 원칙은 간단합니다.

1. 원본 가격 CSV는 그대로 보존합니다.
2. 이상 티커 문제는 원본을 고치지 않고 reference 테이블에서 관리합니다.
3. 분석할 때는 `ticker`가 아니라 `security_id`를 기준으로 봅니다.

## 왜 Reference가 필요한가

티커는 영구 ID가 아닙니다. 같은 회사가 티커를 바꿀 수 있고, NASDAQ에서 NYSE로 이전할 수 있고, 상장폐지 뒤 재상장할 수 있습니다. 과거에 다른 회사가 쓰던 티커를 새 회사가 다시 쓰는 경우도 있습니다.

그래서 이 프로젝트는 가격 데이터와 종목 정체성을 분리합니다.

```text
ticker
= 시장에서 관측된 심볼

security_id
= 이 프로젝트에서 관리하는 종목/회사 단위의 안정적인 ID

listing_id
= 특정 ticker + exchange + 기간에 해당하는 상장 이벤트 ID
```

## 데이터 흐름

```text
1. fetch_tickers.py
   현재 거래소별 티커 목록 수집

2. build_reference.py
   현재 티커 목록과 manual_overrides.csv를 합쳐 종목 기준 테이블 생성

3. download_prices.py
   Yahoo Finance에서 티커별 일봉 원본 CSV 다운로드

4. validate_prices.py
   원본 CSV 품질 검사

5. build_metadata.py
   티커별 데이터 요약 생성

6. merge_to_parquet.py
   거래소별 parquet 산출물 생성

7. export_sqlite.py
   reference와 가격 데이터를 합쳐 SQLite DB 생성
```

## 중요한 폴더

```text
data/tickers/
  거래소별 현재 티커 목록

data/raw/{exchange}/daily/
  Yahoo Finance에서 받은 원본 가격 CSV
  이 폴더가 source of truth입니다.

data/reference/
  종목 ID, listing 이력, 수동 보정 장부

data/metadata/
  티커별 데이터 품질/기간 요약

data/processed/
  SQLite, parquet 같은 재생성 가능한 산출물

logs/
  다운로드 실패, 검증 결과 로그
```

## 원본 데이터 보존

`data/raw/.../daily` 아래의 CSV는 원본입니다. 티커 변경이나 거래소 이전이 있어도 이 파일을 직접 수정하지 않습니다.

예를 들어 어떤 회사가 NASDAQ에서 NYSE로 이전했다면 원본 가격 파일을 합치거나 이름을 바꾸는 대신, `data/reference/manual_overrides.csv`에 listing 이력을 적습니다. 이후 SQLite export 단계에서 날짜 범위에 맞는 `security_id`와 `listing_id`가 붙습니다.

## 이상 티커 관리

아래 문제들은 `data/reference/manual_overrides.csv`에서 관리합니다.

- NASDAQ에서 나갔다가 다시 NASDAQ으로 돌아온 경우
- NASDAQ에서 NYSE/AMEX 등으로 완전히 이전한 경우
- 회사는 같은데 티커가 바뀐 경우
- 과거에 다른 회사가 쓰던 티커를 새 회사가 재사용한 경우
- 상장폐지, 재상장, M&A 등으로 가격 시계열 해석이 필요한 경우

필수 컬럼:

```text
security_id,ticker,exchange,security_name,issuer_name,start_date,end_date,event_type,is_current,status,source,collected_at,confidence
```

예시:

```csv
security_id,ticker,exchange,security_name,issuer_name,start_date,end_date,event_type,is_current,status,source,collected_at,confidence
sec_meta_platforms,FB,NASDAQ,Meta Platforms Inc.,Meta Platforms Inc.,2012-05-18,2022-06-08,ticker_change,false,active,manual,,manual
sec_meta_platforms,META,NASDAQ,Meta Platforms Inc.,Meta Platforms Inc.,2022-06-09,,ticker_change,true,active,manual,,manual
```

## 자주 쓰는 명령

의존성 설치:

```powershell
python -m pip install -r requirements.txt
```

reference 테이블 다시 만들기:

```powershell
python src/build_reference.py
```

SQLite만 다시 만들기:

```powershell
python src/export_sqlite.py
```

전체 파이프라인 실행:

```powershell
python run_pipeline.py --exchanges all --postprocess --parquet --sqlite
```

이미 있는 가격 CSV를 다시 다운로드하려면 `--force`를 추가합니다.

## 조회 예시

```powershell
python src/ticker_lookup.py AAPL
python src/ticker_lookup.py AAPL --json
```

## 한계

Yahoo Finance는 가격 데이터 제공처이지 완전한 상장 이벤트 장부가 아닙니다. 따라서 거래소 이전, 티커 변경, 재사용 티커 같은 사건은 자동 판별만으로 완벽하게 정리할 수 없습니다.

이 프로젝트는 원본 가격 데이터를 보존하고, 확인된 예외를 manual reference로 관리하는 방식을 사용합니다.

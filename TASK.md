````md
# NASDAQ 장기 시계열 데이터셋 구축 TASK

# 0. 프로젝트 목적

본 프로젝트의 목적은 Yahoo Finance 기반으로
NASDAQ 관련 미국 주식의 장기 시계열 데이터를 최대한 많이 수집하는 것이다.

단순히 현재 살아남은 NASDAQ 종목만 수집하는 것이 아니라,
과거 NASDAQ에 존재했던 종목까지 가능한 범위에서 포함하여
장기 연구용 데이터셋을 구축한다.

다만 본 프로젝트는 CRSP 수준의 완전한 survivorship-bias-free 데이터셋 구축이 목표는 아니다.

특수한 기업 이벤트(거래소 이동, 티커 변경, 상장폐지, 재상장, M&A 등)는
완벽히 추적하지 않고 README에 데이터 특성 및 한계로 명시한다.

---

# 1. 데이터 수집 범위

## 1.1 기본 수집 대상

기본 수집 대상은 NASDAQ 관련 종목이다.

수집 기준:

```text
현재 NASDAQ 상장 종목
+
과거 NASDAQ에 존재했던 종목
+
Yahoo Finance에서 가격 데이터를 제공하는 종목
````

---

## 1.2 NYSE 데이터 처리 원칙

본 프로젝트는 NYSE 전체 종목을 수집하지 않는다.

다만 다음 경우에는 NYSE 구간 데이터도 유지한다.

예시:

```text
2018~2022 NASDAQ
2022~2024 NYSE
2024~현재 NASDAQ
```

이 경우:

```text
NYSE 기간 데이터 포함
```

이유:

```text
같은 기업의 가격 시계열 연속성 유지
```

즉:

```text
NYSE 전체 종목 수집 X
NASDAQ 관련 종목의 연속 데이터 유지 O
```

---

# 2. 데이터 해상도

초기 버전 기준:

```text
일봉(1d)
```

사용 설정:

```python
period="max"
interval="1d"
```

---

# 3. 가격 데이터 컬럼

모든 가격 데이터는 다음 컬럼으로 저장한다.

```text
date
ticker
open
high
low
close
adj_close
volume
source
downloaded_at
```

---

# 4. 티커 목록 수집

## 4.1 NASDAQ 티커 목록 수집

NASDAQ Trader Symbol Directory 사용.

수집 대상:

```text
현재 NASDAQ 상장 종목
```

필터링:

```text
ETF 제외 가능
Test Issue 제외
비정상 Symbol 제외
```

---

## 4.2 과거 NASDAQ 관련 종목

가능한 경우:

```text
과거 NASDAQ 관련 티커
상장폐지 티커
거래정지 티커
재상장 티커
```

도 추가한다.

단:

```text
완전한 과거 universe 재현은 목표가 아님
```

---

# 5. 데이터 저장 구조

## 5.1 티커 목록

```text
data/tickers/nasdaq_universe.csv
```

컬럼:

```text
ticker
exchange
security_name
source
collected_at
```

---

## 5.2 개별 가격 데이터

저장 위치:

```text
data/raw/daily/{ticker}.csv
```

예시:

```text
data/raw/daily/AAPL.csv
data/raw/daily/MSFT.csv
data/raw/daily/NVDA.csv
```

---

## 5.3 병합 데이터셋

최종 병합 파일:

```text
data/processed/daily_all.parquet
```

---

# 6. 가격 데이터 다운로드

## 6.1 사용 라이브러리

```python
yfinance
```

---

## 6.2 다운로드 방식

```python
yf.download(
    ticker,
    period="max",
    interval="1d",
    auto_adjust=False
)
```

---

## 6.3 저장 방식

다운로드 즉시 저장.

이유:

```text
중간 실패 발생 시 데이터 손실 방지
```

---

# 7. 호출량 관리

Yahoo Finance는 공식 API 제한을 명확히 공개하지 않는다.

따라서 안전한 속도로 요청한다.

권장 방식:

```text
티커별 순차 다운로드
sleep 사용
batch 단위 처리
```

예시:

```text
1~3초 sleep
또는 20~50개 batch 후 30~60초 대기
```

---

# 8. 다운로드 실패 처리

## 8.1 실패 로그 저장

파일:

```text
logs/download_failed.csv
```

컬럼:

```text
ticker
exchange
error_message
failed_at
retry_count
```

---

## 8.2 재시도 규칙

```text
최대 3회 재시도
```

실패 유형:

```text
빈 데이터
Rate limit
네트워크 오류
Yahoo 오류
```

---

# 9. 데이터 검증

## 9.1 기본 검증

검사 항목:

```text
빈 데이터 여부
중복 날짜 여부
음수 가격 여부
음수 거래량 여부
결측치 여부
```

---

## 9.2 OHLC 논리 검증

```text
high >= low
high >= open
high >= close
low <= open
low <= close
```

---

## 9.3 검증 로그

파일:

```text
logs/validation_report.csv
```

컬럼:

```text
ticker
row_count
first_date
last_date
missing_count
duplicate_count
invalid_ohlc_count
status
```

---

# 10. 메타데이터 생성

파일:

```text
data/metadata/ticker_summary.csv
```

컬럼:

```text
ticker
first_date
last_date
row_count
data_years
has_missing
status
```

status 예시:

```text
OK
FAILED
EMPTY
SHORT_HISTORY
INVALID_DATA
```

---

# 11. README에 반드시 적을 데이터 특징

## 11.1 전기간 수집 원칙

각 티커에 대해 Yahoo Finance에서 제공 가능한 최대 기간의 가격 데이터를 수집한다.

---

## 11.2 거래소 이동

일부 종목은 연구 기간 중 NASDAQ과 NYSE 사이를 이동했을 수 있다.

본 프로젝트는 가격 시계열의 연속성을 유지하기 위해
거래소 이동 구간의 가격 데이터도 유지할 수 있다.

이는 NYSE 전체 종목을 수집한다는 의미가 아니다.

---

## 11.3 상장폐지 종목

일부 종목은 연구 기간 중 상장폐지되었을 수 있다.

Yahoo Finance 특성상 일부 과거 상장폐지 종목은 누락될 가능성이 존재한다.

---

## 11.4 티커 변경

기업은 동일하지만 티커가 변경되었을 수 있다.

본 프로젝트는 티커 변경 이력을 완벽히 연결하지 않는다.

---

## 11.5 재상장

일부 기업은 상장폐지 이후 재상장되었을 수 있다.

본 프로젝트는 재상장 구간을 완벽히 분리하지 않는다.

---

## 11.6 거래정지

일부 종목은 특정 기간 거래정지 상태였을 수 있으며,
그 기간 가격 데이터가 존재하지 않을 수 있다.

---

## 11.7 M&A

인수합병으로 인해 가격 데이터가 특정 시점에서 종료될 수 있다.

---

## 11.8 생존자 편향

본 프로젝트는 가능한 많은 NASDAQ 관련 종목을 수집하려 하지만,
Yahoo Finance 기반 공개 데이터의 한계로 인해
완전한 survivorship-bias-free 데이터셋은 아니다.

---

# 12. 폴더 구조

```text
project/
│
├── data/
│   ├── tickers/
│   │   └── nasdaq_universe.csv
│   │
│   ├── raw/
│   │   └── daily/
│   │       ├── AAPL.csv
│   │       ├── MSFT.csv
│   │       └── ...
│   │
│   ├── metadata/
│   │   └── ticker_summary.csv
│   │
│   └── processed/
│       └── daily_all.parquet
│
├── logs/
│   ├── download_failed.csv
│   └── validation_report.csv
│
├── src/
│   ├── fetch_tickers.py
│   ├── download_prices.py
│   ├── validate_prices.py
│   ├── build_metadata.py
│   └── merge_to_parquet.py
│
├── README.md
├── TASK.md
└── requirements.txt
```

---

# 13. 코드 파일별 역할

## 13.1 fetch_tickers.py

역할:

```text
NASDAQ 관련 티커 목록 수집
ETF/Test Issue 필터링
CSV 저장
```

출력:

```text
data/tickers/nasdaq_universe.csv
```

---

## 13.2 download_prices.py

역할:

```text
티커별 전기간 가격 데이터 다운로드
CSV 저장
실패 로그 저장
```

출력:

```text
data/raw/daily/*.csv
logs/download_failed.csv
```

---

## 13.3 validate_prices.py

역할:

```text
가격 데이터 검증
OHLC 검사
결측 검사
중복 검사
```

출력:

```text
logs/validation_report.csv
```

---

## 13.4 build_metadata.py

역할:

```text
티커별 메타데이터 생성
```

출력:

```text
data/metadata/ticker_summary.csv
```

---

## 13.5 merge_to_parquet.py

역할:

```text
개별 CSV 병합
AI 학습용 parquet 생성
```

출력:

```text
data/processed/daily_all.parquet
```

---

# 14. 실행 순서

```bash
python src/fetch_tickers.py
python src/download_prices.py
python src/validate_prices.py
python src/build_metadata.py
python src/merge_to_parquet.py
```

---

# 15. 최종 산출물

최종 생성 파일:

```text
data/tickers/nasdaq_universe.csv
data/raw/daily/*.csv
data/metadata/ticker_summary.csv
data/processed/daily_all.parquet
logs/download_failed.csv
logs/validation_report.csv
README.md
TASK.md
```

---

# 16. 현재 버전의 목표

현재 버전의 목표:

```text
1. NASDAQ 관련 종목의 장기 가격 데이터를 최대한 많이 확보한다.
2. 가격 데이터의 연속성을 유지한다.
3. 거래소 이동 구간도 필요한 경우 유지한다.
4. 실패 티커와 데이터 이상치를 로그로 남긴다.
5. 데이터 한계와 특수한 티커 특성은 README에 기록한다.
6. AI 학습 가능한 장기 시계열 데이터셋을 구축한다.
```

```
```

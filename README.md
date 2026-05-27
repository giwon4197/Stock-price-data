# Data Notes

본 데이터셋은 Yahoo Finance를 기반으로 수집된 미국 주식 시계열 데이터이다.

가격 데이터는 기업이 거래된 기간 전체를 대상으로 수집하며,
거래소 변경, 티커 변경, 상장폐지, 재상장 여부와 관계없이
수집 가능한 모든 가격 데이터를 유지한다.

사용자는 아래 특성을 고려하여 데이터를 해석해야 한다.

## Known Characteristics

### Exchange Transfer
일부 종목은 연구 기간 중 NASDAQ, NYSE, AMEX 등의 거래소를 이동할 수 있다.

### Delisted Securities
일부 종목은 연구 기간 중 상장폐지되었을 수 있다.

### Relisted Securities
일부 종목은 상장폐지 이후 재상장되었을 수 있다.

### Ticker Changes
일부 기업은 티커(Symbol)가 변경되었을 수 있다.

### Corporate Actions
인수합병(M&A), 분할(Split), 역분할(Reverse Split), 기업구조 변경 등이 포함될 수 있다.

### Trading Suspension
일부 종목은 특정 기간 동안 거래정지 상태였을 수 있다.

### Reused Symbols
과거 사용된 티커가 다른 기업에 의해 재사용되었을 가능성이 있다.

### IPO Timing
종목별 상장 시점이 다르므로 데이터 시작일이 서로 다를 수 있다.

### Survivorship Bias
현재 상장 종목만으로 구성되지 않도록 설계하였으나,
Yahoo Finance 데이터 특성상 일부 과거 상장폐지 종목이 누락될 가능성이 존재한다.
param(
    [string]$Exchanges = "all",
    [switch]$SkipIndex
)

$ErrorActionPreference = "Stop"

Write-Host "[parquet] preparing parquet rebuild"

if ($Exchanges -eq "all") {
    $exchangeList = @("nasdaq", "nyse", "amex", "cboe", "iex")
} else {
    $exchangeList = $Exchanges.Split(",") | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }
}

$total = $exchangeList.Count
Write-Host "[parquet] exchanges: $($exchangeList -join ', ')"

if ($total -eq 0) {
    Write-Host "[parquet] no exchanges selected"
    exit 0
}

for ($index = 0; $index -lt $total; $index++) {
    $exchange = $exchangeList[$index]
    $step = $index + 1
    Write-Host "[parquet] $step/$total building $exchange parquet"
    python src/merge_to_parquet.py --exchange $exchange
    Write-Host "[parquet] $step/$total finished $exchange"
}

Write-Host "[parquet] parquet rebuild complete"

if (-not $SkipIndex) {
    Write-Host "[parquet] building index parquet"
    python src/merge_indices_to_parquet.py
    Write-Host "[parquet] finished index parquet"
}

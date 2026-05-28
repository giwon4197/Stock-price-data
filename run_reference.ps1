param(
    [string]$Exchanges = "all",
    [switch]$Sqlite,
    [switch]$SkipPrices
)

$ErrorActionPreference = "Stop"

$referenceArgs = @("src/build_reference.py")
if ($Exchanges -eq "all") {
    $referenceArgs += @("--exchanges", "nasdaq", "nyse", "amex", "cboe", "iex")
} else {
    $referenceArgs += @("--exchanges")
    $referenceArgs += $Exchanges.Split(",") | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }
}

python @referenceArgs

if ($Sqlite) {
    $sqliteArgs = @("src/export_sqlite.py")
    if ($SkipPrices) {
        $sqliteArgs += "--skip-prices"
    }
    python @sqliteArgs
}

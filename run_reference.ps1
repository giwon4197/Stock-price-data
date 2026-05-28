param(
    [string]$Exchanges = "all",
    [switch]$Sqlite,
    [switch]$SkipPrices
)

$ErrorActionPreference = "Stop"

Write-Host "[reference] preparing reference rebuild"

$referenceArgs = @("src/build_reference.py")
if ($Exchanges -eq "all") {
    $referenceArgs += @("--exchanges", "nasdaq", "nyse", "amex", "cboe", "iex")
} else {
    $referenceArgs += @("--exchanges")
    $referenceArgs += $Exchanges.Split(",") | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }
}

Write-Host "[reference] running: python $($referenceArgs -join ' ')"
python @referenceArgs
Write-Host "[reference] reference rebuild complete"

if ($Sqlite) {
    $sqliteArgs = @("src/export_sqlite.py")
    if ($SkipPrices) {
        $sqliteArgs += "--skip-prices"
    }
    Write-Host "[reference] running: python $($sqliteArgs -join ' ')"
    python @sqliteArgs
    Write-Host "[reference] SQLite export complete"
}

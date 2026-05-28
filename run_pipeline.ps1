param(
    [string]$Exchanges = "all",
    [int]$Workers = 6,
    [switch]$Force,
    [int]$Limit = 0,
    [double]$Sleep = 1.5,
    [int]$Retries = 3,
    [switch]$Postprocess,
    [switch]$Parquet,
    [switch]$Sqlite,
    [switch]$SkipReference,
    [switch]$SkipIndex
)

$ErrorActionPreference = "Stop"

Write-Host "[pipeline] preparing full pipeline"

$argsList = @(
    "run_pipeline.py",
    "--exchanges", $Exchanges,
    "--workers", $Workers,
    "--sleep", $Sleep,
    "--retries", $Retries
)

if ($Force) {
    $argsList += "--force"
}

if ($Limit -gt 0) {
    $argsList += @("--limit", $Limit)
}

if ($Postprocess) {
    $argsList += "--postprocess"
}

if ($Parquet) {
    $argsList += "--parquet"
}

if ($Sqlite) {
    $argsList += "--sqlite"
}

if ($SkipReference) {
    $argsList += "--skip-reference"
}

if ($SkipIndex) {
    $argsList += "--skip-index"
}

Write-Host "[pipeline] running: python $($argsList -join ' ')"
python @argsList
Write-Host "[pipeline] pipeline complete"

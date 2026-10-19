param([switch]$SkipEmbeddingModel)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Setup command failed (exit $LASTEXITCODE)." } }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    Check-Exit
}
$requirements = if (Test-Path -LiteralPath 'requirements.lock.txt') { 'requirements.lock.txt' } else { 'requirements.txt' }
& '.\.venv\Scripts\python.exe' -m pip install -r $requirements
Check-Exit
npm ci
Check-Exit
npm run build
Check-Exit
if (-not $SkipEmbeddingModel) {
    ollama pull embeddinggemma:300m
    Check-Exit
}
# Provision OCR weights during setup, not on the first offline indexing run.
& '.\.venv\Scripts\python.exe' -c "from rapidocr import RapidOCR; RapidOCR()"
Check-Exit
& '.\.venv\Scripts\python.exe' -m pip freeze | Set-Content -Encoding utf8 requirements.lock.txt
Write-Host 'Ready. Run .\start.ps1 to open Screenshot Recall.'

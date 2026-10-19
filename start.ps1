param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath 'dist\index.html')) {
    throw 'Run .\setup.ps1 first.'
}
try { $existing = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/status' -TimeoutSec 2 } catch { $existing = $null }
if ($existing) {
    if ($existing.application -ne 'screenshot-recall') { throw 'Port 8765 is occupied by an unrecognized service.' }
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8765' }
    Write-Host 'Recall is already running. Use .\stop.ps1 to stop it.'; exit
}
try {
    $null = New-Item -ItemType Directory -Path 'data' -Force
    $server = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','recall.app:app','--host','127.0.0.1','--port','8765') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'data\server.log') -RedirectStandardError (Join-Path $PSScriptRoot 'data\server-errors.log') -PassThru
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        if ($server.HasExited) { throw 'Server exited before startup. Run the uvicorn command in README for diagnostics.' }
        try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/status' -TimeoutSec 1; $ready = $true; break } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'Server did not become ready.' }
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8765' }
    Write-Host 'Recall is running. Closing the browser does not stop indexing.'
    Write-Host 'Press Ctrl+C in this window to stop the server.'
    Write-Host 'Or run .\stop.ps1 from another PowerShell window.'
    while (-not $server.HasExited) { Start-Sleep -Seconds 1 }
} finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id }
}

$ErrorActionPreference = 'Stop'
try {
    $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/status' -TimeoutSec 3
} catch {
    Write-Host 'Screenshot Recall is not responding on port 8765. No process was stopped.'
    exit
}
if ($status.application -ne 'screenshot-recall' -or -not $status.server_pid) {
    throw 'The service on port 8765 is not a recognized Screenshot Recall instance. No process was stopped.'
}
$expected = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.venv\Scripts\python.exe'))
$expectedEnvironment = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.venv'))
if (-not $status.environment -or [System.IO.Path]::GetFullPath($status.environment) -ine $expectedEnvironment) {
    throw 'The server does not report this project virtual environment. No process was stopped.'
}
$baseExecutable = & $expected -c 'import sys; print(sys._base_executable)'
if ($LASTEXITCODE -ne 0) { throw 'Could not verify the Python runtime. No process was stopped.' }
$process = Get-Process -Id ([int]$status.server_pid) -ErrorAction Stop
if (-not $process.Path -or ([System.IO.Path]::GetFullPath($process.Path) -ine $expected -and [System.IO.Path]::GetFullPath($process.Path) -ine [System.IO.Path]::GetFullPath($baseExecutable.Trim()))) {
    throw 'The server process is outside this project virtual environment. No process was stopped.'
}
Stop-Process -Id $process.Id -ErrorAction Stop
Write-Host 'Screenshot Recall stopped. Your screenshots and saved index are unchanged.'
Write-Host 'Ollama runs separately and has not been stopped.'

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run install_windows_task.ps1 first."
}

& $python "visa_monitor.py" `
    --config "sources.json" `
    --state "data\state.json" `
    --report "reports\latest.md" `
    --json-output "reports\latest.json"

exit $LASTEXITCODE

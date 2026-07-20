param(
    [string]$TaskName = "Visa Policy Monitor",
    [string]$RunTime = "08:00"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue) -and
    -not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.10+ is required. Install Python, then run this script again."
}

$pythonCommand = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }

if (-not (Test-Path ".venv")) {
    & $pythonCommand -m venv ".venv"
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -r "requirements.txt"

# Create the initial baseline immediately.
& $python "visa_monitor.py" `
    --config "sources.json" `
    --state "data\state.json" `
    --report "reports\latest.md" `
    --json-output "reports\latest.json"

$scriptPath = Join-Path $PSScriptRoot "run_monitor.ps1"
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -Monthly -DaysOfMonth 1 -At $RunTime

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Checks official UK Skilled Worker, UK Graduate visa, and USCIS H-1B pages monthly." `
    -Force | Out-Null

Write-Host "Installed '$TaskName'. It will run on day 1 of every month at $RunTime."
Write-Host "Latest report: $(Join-Path $PSScriptRoot 'reports\latest.md')"

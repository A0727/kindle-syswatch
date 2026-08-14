$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python environment is missing. Run setup.ps1 first."
}

Set-Location -LiteralPath $projectRoot
& $python -m kindle_monitor.server

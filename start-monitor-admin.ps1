$ErrorActionPreference = "Stop"

$project = $PSScriptRoot
$pythonw = Join-Path $project ".venv\Scripts\pythonw.exe"
$pidFile = Join-Path $project "runtime\server.pid"
$bridgePath = [System.IO.Path]::GetFullPath(
    (Join-Path $project "vendor\librehardwaremonitor\KindleMonitor.SensorBridge.exe")
)
$launcherIds = @()

# The server records its own PID. Stop that exact process first so a restart
# reliably loads updated Python code even when CIM hides the command line.
if (Test-Path -LiteralPath $pidFile -PathType Leaf) {
    $recordedPid = Get-Content -Raw -LiteralPath $pidFile -ErrorAction SilentlyContinue
    if ($recordedPid -match '^\s*(\d+)\s*$') {
        Stop-Process -Id ([int]$Matches[1]) -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Milliseconds 500

$listeners = Get-NetTCPConnection `
    -LocalPort 8765 `
    -State Listen `
    -ErrorAction SilentlyContinue

foreach ($listener in $listeners) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if ($process.CommandLine -like "*kindle_monitor.server*") {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)" -ErrorAction SilentlyContinue
        if (
            $parent -and
            $parent.ExecutablePath -and
            [System.IO.Path]::GetFullPath($parent.ExecutablePath) -eq [System.IO.Path]::GetFullPath($pythonw)
        ) {
            $launcherIds += $parent.ProcessId
        }
        Stop-Process -Id $listener.OwningProcess -Force
    }
}

Start-Sleep -Seconds 1

# A forced server restart can orphan the native sensor bridge. Multiple bridge
# instances compete for PawnIO and make Ryzen SMU values read as zero, so clear
# every bridge created by this project before starting the single live sampler.
foreach ($launcherId in $launcherIds) {
    Stop-Process -Id $launcherId -Force -ErrorAction SilentlyContinue
}

$staleBridges = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "KindleMonitor.SensorBridge.exe" -and
    $_.ExecutablePath -and
    [System.IO.Path]::GetFullPath($_.ExecutablePath) -eq $bridgePath
}
foreach ($process in $staleBridges) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 1
Start-Process `
    -FilePath $pythonw `
    -ArgumentList "-m", "kindle_monitor.server" `
    -WorkingDirectory $project `
    -WindowStyle Hidden | Out-Null

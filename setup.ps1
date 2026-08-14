param(
    [switch]$SkipHardwareBridge
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$projectRoot = $PSScriptRoot
$venvDir = Join-Path $projectRoot ".venv"
$runtimeDir = Join-Path $projectRoot "runtime"
$vendorDir = Join-Path $projectRoot "vendor\librehardwaremonitor"

function Find-Python {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) {
        return @($python.Source)
    }

    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        return @($launcher.Source, "-3")
    }

    throw "Python 3.11 or newer was not found. Install Python, then run setup.ps1 again."
}

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$pythonCommand = @(Find-Python)
$pythonArguments = @()
if ($pythonCommand.Count -gt 1) {
    $pythonArguments = $pythonCommand[1..($pythonCommand.Count - 1)]
}
& $pythonCommand[0] @pythonArguments -m venv $venvDir

$venvPython = Join-Path $venvDir "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $projectRoot "requirements.txt")

if (-not $SkipHardwareBridge) {
    $headers = @{ "User-Agent" = "kindle-syswatch-setup" }
    $release = Invoke-RestMethod `
        -Headers $headers `
        -Uri "https://api.github.com/repos/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest"

    # LibreHardwareMonitor also publishes a .NET 10 archive. The sensor bridge
    # is intentionally compiled with the .NET Framework compiler included in
    # Windows, so select the classic release archive by its exact asset name.
    $asset = $release.assets |
        Where-Object { $_.name -eq "LibreHardwareMonitor.zip" } |
        Select-Object -First 1
    if (-not $asset) {
        throw "The latest LibreHardwareMonitor release does not contain a Windows ZIP asset."
    }

    $archive = Join-Path $runtimeDir $asset.name
    $extractDir = Join-Path $runtimeDir "librehardwaremonitor-download"
    Invoke-WebRequest -Headers $headers -Uri $asset.browser_download_url -OutFile $archive

    if (Test-Path -LiteralPath $extractDir) {
        Remove-Item -LiteralPath $extractDir -Recurse -Force
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $extractDir -Force

    $library = Get-ChildItem -LiteralPath $extractDir -Recurse |
        Where-Object { -not $_.PSIsContainer -and $_.Name -eq "LibreHardwareMonitorLib.dll" } |
        Select-Object -First 1
    if (-not $library) {
        throw "LibreHardwareMonitorLib.dll was not found in the downloaded release."
    }

    New-Item -ItemType Directory -Force -Path $vendorDir | Out-Null
    Copy-Item -Path (Join-Path $library.Directory.FullName "*") -Destination $vendorDir -Recurse -Force

    $compiler = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) {
        throw ".NET Framework C# compiler was not found at $compiler."
    }

    $bridgeOutput = Join-Path $vendorDir "KindleMonitor.SensorBridge.exe"
    & $compiler `
        /nologo `
        /target:exe `
        "/out:$bridgeOutput" `
        /reference:System.Web.Extensions.dll `
        "/reference:$($library.FullName)" `
        (Join-Path $projectRoot "sensor_bridge\Program.cs")
    if ($LASTEXITCODE -ne 0) {
        throw "The sensor bridge build failed."
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "config.toml"))) {
    Copy-Item `
        -LiteralPath (Join-Path $projectRoot "config.example.toml") `
        -Destination (Join-Path $projectRoot "config.toml")
}

Write-Host "SYSWATCH setup completed. Edit config.toml before starting the service."

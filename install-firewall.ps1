param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$')]
    [string]$KindleMac
)

$ErrorActionPreference = "Stop"

$ruleName = "Kindle Monitor"
$normalizedMac = $KindleMac.Replace(":", "-").ToUpperInvariant()
$neighbor = Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.LinkLayerAddress -and
        $_.LinkLayerAddress.Replace(":", "-").ToUpperInvariant() -eq $normalizedMac -and
        $_.IPAddress -ne "0.0.0.0"
    } |
    Sort-Object @{ Expression = { if ($_.State -eq "Reachable") { 0 } else { 1 } } } |
    Select-Object -First 1

if (-not $neighbor) {
    throw "Kindle was not found. Disconnect USB, connect Kindle to this PC's hotspot, then run this script again."
}

$localAddress = Get-NetIPAddress `
    -InterfaceIndex $neighbor.InterfaceIndex `
    -AddressFamily IPv4 `
    -ErrorAction Stop |
    Where-Object {
        $_.IPAddress -notlike "169.254.*" -and
        $_.IPAddress -ne "127.0.0.1"
    } |
    Select-Object -First 1

if (-not $localAddress) {
    throw "No usable PC address was found on the Kindle hotspot interface."
}

$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    $existing | Remove-NetFirewallRule
}

New-NetFirewallRule `
    -DisplayName $ruleName `
    -Description "Allow only the paired Kindle to reach the local Kindle monitor service." `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 8765 `
    -LocalAddress $localAddress.IPAddress `
    -RemoteAddress $neighbor.IPAddress `
    -Profile Any | Out-Null

Write-Output "Firewall paired: $($localAddress.IPAddress):8765 <- Kindle $($neighbor.IPAddress) [$normalizedMac]"

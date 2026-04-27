$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "== $Title ==" -ForegroundColor Cyan
}

function Show-Check {
    param(
        [string]$Name,
        [bool]$Ok,
        [string]$Detail
    )

    $status = if ($Ok) { "[OK]" } else { "[WARN]" }
    $color = if ($Ok) { "Green" } else { "Yellow" }
    Write-Host ("{0} {1} - {2}" -f $status, $Name, $Detail) -ForegroundColor $color
}

function Test-TcpEndpoint {
    param(
        [string]$Address,
        [int]$Port,
        [int]$TimeoutMs = 1500
    )

    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($Address, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            $client.Close()
            return $false
        }
        $client.EndConnect($iar)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

Write-Section "RustDesk"
$rustDeskExe = "C:\Program Files\RustDesk\rustdesk.exe"
$rustDeskInstalled = Test-Path $rustDeskExe
Show-Check "RustDesk Installed" $rustDeskInstalled ($rustDeskExe)

$rustDeskService = Get-Service -Name "Rustdesk" -ErrorAction SilentlyContinue
$rustDeskServiceDetail = if ($null -eq $rustDeskService) { "service not found" } else { $rustDeskService.Status.ToString() }
Show-Check "RustDesk Service" ($null -ne $rustDeskService -and $rustDeskService.Status -eq "Running") $rustDeskServiceDetail

if ($rustDeskInstalled) {
    try {
        $idOut = Join-Path $env:TEMP "rustdesk_id.txt"
        if (Test-Path $idOut) {
            Remove-Item $idOut -Force
        }
        Start-Process -FilePath $rustDeskExe -ArgumentList "--get-id" -NoNewWindow -RedirectStandardOutput $idOut -Wait
        $rustDeskId = (Get-Content $idOut -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
        $rustDeskIdDetail = if ([string]::IsNullOrWhiteSpace($rustDeskId)) { "not available" } else { $rustDeskId }
        Show-Check "RustDesk ID" (-not [string]::IsNullOrWhiteSpace($rustDeskId)) $rustDeskIdDetail
    } catch {
        Show-Check "RustDesk ID" $false $_.Exception.Message
    }
}

Write-Section "Network"
$ipconfigLines = ipconfig
$adapters = @()
$currentAdapter = $null

foreach ($line in $ipconfigLines) {
    if ($line -match '^[A-Za-z].*adapter (.+):$') {
        if ($null -ne $currentAdapter) {
            $adapters += [pscustomobject]$currentAdapter
        }
        $currentAdapter = @{
            Name = $matches[1].Trim()
            IPv4 = $null
        }
        continue
    }

    if ($null -ne $currentAdapter -and $line -match 'IPv4 Address[.\s]*:\s*([0-9.]+)') {
        $currentAdapter["IPv4"] = $matches[1]
    }
}

if ($null -ne $currentAdapter) {
    $adapters += [pscustomobject]$currentAdapter
}

$adapters = $adapters | Where-Object { $_.IPv4 }

if (-not $adapters) {
    Show-Check "Active Adapters" $false "no active IPv4 adapters"
} else {
    foreach ($adapter in $adapters) {
        $detail = "{0} {1}" -f $adapter.Name, $adapter.IPv4
        Show-Check "Adapter" $true $detail
    }
}

$ethernetUp = $adapters | Where-Object { $_.Name -match "Ethernet" }
$ethernetDetail = if ($null -ne $ethernetUp) { "connected" } else { "disconnected" }
Show-Check "Robot-side Ethernet" ($null -ne $ethernetUp) $ethernetDetail

Write-Section "Robot Endpoints"
$tcpChecks = @(
    @{ Name = "AGX sensor"; Host = "192.168.1.100"; Port = 5001 },
    @{ Name = "AGX gripper"; Host = "192.168.1.100"; Port = 5002 },
    @{ Name = "Arm direct_232"; Host = "192.168.1.232"; Port = 502 },
    @{ Name = "Arm direct_233"; Host = "192.168.1.233"; Port = 502 }
)

foreach ($check in $tcpChecks) {
    $ok = Test-TcpEndpoint -Address $check.Host -Port $check.Port
    Show-Check $check.Name $ok ("{0}:{1}" -f $check.Host, $check.Port)
}

Write-Section "Virtual Environment"
try {
    $resp = Invoke-RestMethod "http://140.127.205.127:8765/health" -TimeoutSec 3
    Show-Check "VE Health" ([bool]$resp.ok) "http://140.127.205.127:8765/health"
} catch {
    Show-Check "VE Health" $false "request failed"
}

Write-Host ""
Write-Host "Done. If Robot-side Ethernet is disconnected, plug in the lab Ethernet before leaving." -ForegroundColor White

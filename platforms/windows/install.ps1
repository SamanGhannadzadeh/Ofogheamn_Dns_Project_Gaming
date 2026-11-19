# Ofogheamn DNS — Windows server node installer
# Core: AdGuard Home (native Windows build) + sing-box proxy.
# Run in an ELEVATED PowerShell from the repo's platforms\windows.
#Requires -RunAsAdministrator
param([switch]$Lite)   # Lite: no exposed panel (AGH UI stays on localhost), CLI/config management
$ErrorActionPreference = "Stop"

$AGH_VER = "v0.107.80"
$SINGBOX_VER = "1.14.4"
$Root = "C:\Program Files\OfogheamnDNS"
$Data = "C:\ProgramData\OfogheamnDNS"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..\..").Path

Write-Host "== Ofogheamn DNS node for Windows ==" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $Root, $Data | Out-Null

# ---------- AdGuard Home ----------
$aghZip = "$env:TEMP\AdGuardHome_windows_amd64.zip"
if (-not (Test-Path "$Root\AdGuardHome.exe")) {
    Write-Host "Downloading AdGuard Home $AGH_VER ..."
    Invoke-WebRequest "https://github.com/AdguardTeam/AdGuardHome/releases/download/$AGH_VER/AdGuardHome_windows_amd64.zip" -OutFile $aghZip
    Expand-Archive $aghZip -DestinationPath "$env:TEMP\agh" -Force
    Copy-Item "$env:TEMP\agh\AdGuardHome\AdGuardHome.exe" "$Root\"
}

# ---------- config (rewrites come from the project's hijack.conf) ----------
$tpl = Get-Content "$RepoRoot\platforms\common\AdGuardHome.template.yaml" -Raw
$rewrites = ""
$hijack = "$RepoRoot\config\hijack.conf"
if (Test-Path $hijack) {
    foreach ($line in Get-Content $hijack) {
        if ($line -match '^\s*address\s+/([^/]+)/(\S+)') {
            $rewrites += "    - domain: $($Matches[1])`n      answer: $($Matches[2])`n      type: A`n      enabled: true`n"
        }
    }
}
if (-not $rewrites) { $rewrites = "    []`n" }
$tpl = $tpl -replace "__REWRITES__", $rewrites.TrimEnd()
if ($Lite) { $tpl = $tpl -replace "0\.0\.0\.0:3000", "127.0.0.1:3000" }
if (-not (Test-Path "$Data\AdGuardHome.yaml")) {
    Set-Content "$Data\AdGuardHome.yaml" $tpl -Encoding UTF8
}

# ---------- sing-box proxy ----------
$sbZip = "$env:TEMP\sing-box.zip"
if (-not (Test-Path "$Root\sing-box.exe")) {
    Write-Host "Downloading sing-box $SINGBOX_VER ..."
    Invoke-WebRequest "https://github.com/SagerNet/sing-box/releases/download/v$SINGBOX_VER/sing-box-$SINGBOX_VER-windows-amd64.zip" -OutFile $sbZip
    Expand-Archive $sbZip -DestinationPath "$env:TEMP\sb" -Force
    Copy-Item "$env:TEMP\sb\sing-box-$SINGBOX_VER-windows-amd64\sing-box.exe" "$Root\"
}
$proxyPass = -join ((48..57) + (97..122) | Get-Random -Count 16 | ForEach-Object { [char]$_ })
$proxyCfg = @{
    log = @{ level = "warn" }
    inbounds = @(@{ type = "mixed"; tag = "mixed-in"; listen = "0.0.0.0"; listen_port = 2080;
                    users = @(@{ username = "ofogh"; password = $proxyPass }) })
    outbounds = @(@{ type = "direct"; tag = "direct" })
} | ConvertTo-Json -Depth 6
if (-not (Test-Path "$Data\proxy.json")) { Set-Content "$Data\proxy.json" $proxyCfg -Encoding UTF8 }

# ---------- firewall ----------
foreach ($r in @(
    @("Ofogh DNS UDP", 53, "UDP"), @("Ofogh DNS TCP", 53, "TCP"),
    @("Ofogh DoT", 853, "TCP"), @("Ofogh Proxy", 2080, "TCP"),
    @("Ofogh AGH Panel", 3000, "TCP"), @("Ofogh Mesh Report", 51821, "TCP"))) {
    if ($Lite -and $r[0] -eq "Ofogh AGH Panel") { continue }
    if (-not (Get-NetFirewallRule -DisplayName $r[0] -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $r[0] -Direction Inbound -Protocol $r[2] -LocalPort $r[1] -Action Allow | Out-Null
    }
}

# ---------- services / tasks ----------
Push-Location $Root
& .\AdGuardHome.exe -s install -c "$Data\AdGuardHome.yaml" -w $Data 2>$null
& .\AdGuardHome.exe -s start 2>$null
Pop-Location
$action = New-ScheduledTaskAction -Execute "$Root\sing-box.exe" -Argument "run -c `"$Data\proxy.json`""
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "OfogheamnProxy" -Action $action -Trigger $trigger -User "SYSTEM" -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName "OfogheamnProxy"

Write-Host ""
Write-Host "DONE. Ofogheamn DNS node is running on this Windows machine." -ForegroundColor Green
Write-Host " DNS (this server's IP): port 53 (UDP/TCP), DoT 853"
if ($Lite) { Write-Host " LITE edition: no exposed panel - AGH UI is bound to localhost:3000 on this machine only." }
else { Write-Host " AdGuard Home panel:     http://localhost:3000  (first visit: create the admin user)" }
Write-Host " Proxy:                  <this server IP>:2080  user: ofogh  password: $proxyPass"
Write-Host " WireGuard: install the official WireGuard app to import client configs from your nodes."

# Ofogheamn DNS — Windows server node installer
# Core: AdGuard Home (native Windows build) + sing-box proxy.
# Run in an ELEVATED PowerShell from the repo's platforms\windows.
#Requires -RunAsAdministrator
param([switch]$Lite)   # Lite: no exposed panel (AGH UI stays on localhost), CLI/config management
$ErrorActionPreference = "Stop"

# GitHub requires TLS 1.2+. Windows PowerShell 5.1 on older .NET
# defaults may negotiate only TLS 1.0/1.1, and then every download
# below dies with a bare "could not create SSL/TLS channel" error.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# PS 5.1's Set-Content -Encoding UTF8 writes a BOM. The files
# generated below are parsed by Go programs (sing-box reads
# proxy.json with a strict JSON parser that rejects a BOM), so
# they are written BOM-free.
function Write-NoBom($Path, $Text) {
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding $false))
}

# Same download-integrity policy as the Linux installer: every
# binary is checked against the SHA-256 digest GitHub records
# for the release asset. API unreachable -> warn and continue;
# a KNOWN mismatch -> abort.
function Test-Digest($Repo, $Tag, $Asset, $File) {
    try {
        $rel = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/tags/$Tag" -TimeoutSec 30
        $a = $rel.assets | Where-Object { $_.name -eq $Asset } | Select-Object -First 1
        $want = ($a.digest -replace '^sha256:', '')
        if (-not $want) { Write-Host "WARNING: no official digest for $Asset; installing unverified"; return }
        $got = (Get-FileHash $File -Algorithm SHA256).Hash.ToLower()
        if ($got -ne $want.ToLower()) { throw "SECURITY ABORT: sha256 mismatch for $Asset" }
        Write-Host "digest verified: $Asset"
    } catch {
        if ($_.Exception.Message -like 'SECURITY ABORT*') { throw }
        Write-Host "WARNING: could not fetch the official digest for $Asset; installing unverified"
    }
}

$AGH_VER = "v0.107.80"
$SINGBOX_VER = "1.14.4"
$Root = "C:\Program Files\OfogheamnDNS"
$Data = "C:\ProgramData\OfogheamnDNS"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path

Write-Host "== Ofogheamn DNS node for Windows ==" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $Root, $Data | Out-Null

# ---------- AdGuard Home ----------
$aghZip = "$env:TEMP\AdGuardHome_windows_amd64.zip"
if (-not (Test-Path "$Root\AdGuardHome.exe")) {
    Write-Host "Downloading AdGuard Home $AGH_VER ..."
    Invoke-WebRequest "https://github.com/AdguardTeam/AdGuardHome/releases/download/$AGH_VER/AdGuardHome_windows_amd64.zip" -OutFile $aghZip
    Test-Digest "AdguardTeam/AdGuardHome" $AGH_VER "AdGuardHome_windows_amd64.zip" $aghZip
    Expand-Archive $aghZip -DestinationPath "$env:TEMP\agh" -Force
    Copy-Item "$env:TEMP\agh\AdGuardHome\AdGuardHome.exe" "$Root\"
}

# ---------- config (rewrites come from the project's hijack.conf) ----------
if (-not (Test-Path "$RepoRoot\platforms\common\AdGuardHome.template.yaml")) {
    throw "Project files not found next to this script. Run install.ps1 from a full clone of the Ofogheamn_Dns_Project_Gaming repo (this script must stay in platforms\windows inside the repo)."
}
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
    Write-NoBom "$Data\AdGuardHome.yaml" $tpl
}

# ---------- sing-box proxy ----------
$sbZip = "$env:TEMP\sing-box.zip"
if (-not (Test-Path "$Root\sing-box.exe")) {
    Write-Host "Downloading sing-box $SINGBOX_VER ..."
    Invoke-WebRequest "https://github.com/SagerNet/sing-box/releases/download/v$SINGBOX_VER/sing-box-$SINGBOX_VER-windows-amd64.zip" -OutFile $sbZip
    Test-Digest "SagerNet/sing-box" "v$SINGBOX_VER" "sing-box-$SINGBOX_VER-windows-amd64.zip" $sbZip
    Expand-Archive $sbZip -DestinationPath "$env:TEMP\sb" -Force
    Copy-Item "$env:TEMP\sb\sing-box-$SINGBOX_VER-windows-amd64\sing-box.exe" "$Root\"
}
# The password is generated ONLY when proxy.json is first
# created, and the banner below prints it only then. This used
# to mint a fresh password on every run and print THAT — on a
# re-run the printed password was not the stored one (v1.4 fix).
$proxyPass = $null
if (-not (Test-Path "$Data\proxy.json")) {
    $proxyPass = -join ((48..57) + (97..122) | Get-Random -Count 16 | ForEach-Object { [char]$_ })
    $proxyCfg = @{
        log = @{ level = "warn" }
        inbounds = @(@{ type = "mixed"; tag = "mixed-in"; listen = "0.0.0.0"; listen_port = 2080;
                        users = @(@{ username = "ofogh"; password = $proxyPass }) })
        outbounds = @(@{ type = "direct"; tag = "direct" })
    } | ConvertTo-Json -Depth 6
    Write-NoBom "$Data\proxy.json" $proxyCfg
}

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
# Windows PowerShell 5.1 turns a native exe's stderr output into a
# terminating NativeCommandError while $ErrorActionPreference is
# "Stop" — and AdGuard Home logs its normal startup line to stderr
# even on success, which killed the install right here. Relax the
# preference around these two calls only.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& .\AdGuardHome.exe -s install -c "$Data\AdGuardHome.yaml" -w $Data 2>$null
& .\AdGuardHome.exe -s start 2>$null
$ErrorActionPreference = $prevEAP
Pop-Location
$action = New-ScheduledTaskAction -Execute "$Root\sing-box.exe" -Argument "run -c `"$Data\proxy.json`""
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "OfogheamnProxy" -Action $action -Trigger $trigger -User "SYSTEM" -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName "OfogheamnProxy"

# ---------- self-verification (v1.4): report, don't assume ----------
# The banner used to declare the node "running" unconditionally.
# Now each piece is actually checked and reported PASS/FAIL.
Write-Host ""
Write-Host "Self-test:"
$fail = $false
$svc = Get-Service AdGuardHome -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq 'Running') { Write-Host "  PASS  AdGuard Home service is running" }
else { Write-Host "  FAIL  AdGuard Home service is NOT running"; $fail = $true }
$dnsOk = $false
foreach ($try in 1..3) {
    try { Resolve-DnsName -Name example.com -Server 127.0.0.1 -Type A -DnsOnly -ErrorAction Stop | Out-Null; $dnsOk = $true; break }
    catch { Start-Sleep -Seconds 2 }
}
if ($dnsOk) { Write-Host "  PASS  DNS answers on 127.0.0.1:53" }
else { Write-Host "  FAIL  DNS does not answer on 127.0.0.1:53"; $fail = $true }
if (Get-NetTCPConnection -LocalPort 2080 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "  PASS  proxy is listening on 2080"
} else { Write-Host "  FAIL  proxy is NOT listening on 2080 (scheduled task OfogheamnProxy)"; $fail = $true }
if ($fail) { Write-Host "SELF-TEST: FAIL - installed, but not fully up (see the FAIL lines above)." -ForegroundColor Red }
else { Write-Host "SELF-TEST: PASS" -ForegroundColor Green }

Write-Host ""
if ($fail) { Write-Host "INSTALLED WITH PROBLEMS. Ofogheamn DNS node is not fully up on this Windows machine." -ForegroundColor Red }
else { Write-Host "DONE. Ofogheamn DNS node is running on this Windows machine." -ForegroundColor Green }
Write-Host " DNS (this server's IP): port 53 (UDP/TCP)"
Write-Host " DoT/DoH: not served by default - enable it in the AdGuard Home panel (Settings -> Encryption) with a certificate."
if ($Lite) { Write-Host " LITE edition: no exposed panel - AGH UI is bound to localhost:3000 on this machine only." }
else { Write-Host " AdGuard Home panel:     http://localhost:3000  (first visit: create the admin user)" }
if ($proxyPass) { Write-Host " Proxy:                  <this server IP>:2080  user: ofogh  password: $proxyPass" }
else { Write-Host " Proxy:                  <this server IP>:2080  user: ofogh  password: (unchanged - stored in $Data\proxy.json)" }
Write-Host " WireGuard: install the official WireGuard app to import client configs from your nodes."

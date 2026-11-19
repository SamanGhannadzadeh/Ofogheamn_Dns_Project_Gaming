# ============================================================
#  Ofogheamn DNS — Windows installer (run as Administrator)
#    powershell -ExecutionPolicy Bypass -File install.ps1
#  Installs SmartDNS + sing-box as Windows services (via NSSM),
#  seeds the project config under C:\OfogheamnDns, opens the
#  firewall ports, and prints the panel/proxy credentials.
#  The web panel needs Python 3 (winget install Python.Python.3)
#  and is registered as a service too when Python is present.
# ============================================================
$ErrorActionPreference = 'Stop'
$Root = 'C:\OfogheamnDns'
$Repo = 'https://github.com/saman-ghannadzadeh/Ofogheamn_Dns_Project_Gaming'
New-Item -ItemType Directory -Force -Path $Root, "$Root\logs", "$Root\cache" | Out-Null

function Get-LatestAsset($repo, $pattern) {
  $rel = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest"
  $asset = $rel.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
  if (-not $asset) { throw "asset $pattern not found in $repo $($rel.tag_name)" }
  return $asset.browser_download_url
}

Write-Host '==> downloading cores'
$sd = Get-LatestAsset 'pymumu/smartdns' 'win.*x86_64|windows.*x86_64|x86_64.*win'
Invoke-WebRequest $sd -OutFile "$Root\smartdns.zip"
Expand-Archive "$Root\smartdns.zip" -DestinationPath "$Root\smartdns-bin" -Force
$sb = Get-LatestAsset 'SagerNet/sing-box' 'windows-amd64\.zip$'
Invoke-WebRequest $sb -OutFile "$Root\sing-box.zip"
Expand-Archive "$Root\sing-box.zip" -DestinationPath "$Root\singbox-bin" -Force
$nssm = 'https://nssm.cc/release/nssm-2.24.zip'
Invoke-WebRequest $nssm -OutFile "$Root\nssm.zip"
Expand-Archive "$Root\nssm.zip" -DestinationPath "$Root\nssm-bin" -Force
$NssmExe = (Get-ChildItem "$Root\nssm-bin" -Recurse -Filter nssm.exe | Where-Object { $_.FullName -match 'win64' } | Select-Object -First 1).FullName
$SmartDnsExe = (Get-ChildItem "$Root\smartdns-bin" -Recurse -Filter smartdns.exe | Select-Object -First 1).FullName
$SingBoxExe = (Get-ChildItem "$Root\singbox-bin" -Recurse -Filter sing-box.exe | Select-Object -First 1).FullName

Write-Host '==> fetching project config'
Invoke-WebRequest "$Repo/archive/refs/heads/main.zip" -OutFile "$Root\repo.zip"
Expand-Archive "$Root\repo.zip" -DestinationPath "$Root\repo" -Force
$Src = (Get-ChildItem "$Root\repo" -Directory | Select-Object -First 1).FullName
Copy-Item "$Src\config\*" "$Root\" -Recurse -Force
Copy-Item "$Src\config\lists" "$Root\lists" -Recurse -Force
# point the config at Windows paths
(Get-Content "$Root\smartdns.conf") `
  -replace '/etc/ofogheamn-dns', ($Root -replace '\\','/') `
  -replace '/var/cache/ofogheamn-dns', (($Root + '\cache') -replace '\\','/') `
  -replace '/var/log/ofogheamn-dns', (($Root + '\logs') -replace '\\','/') |
  Set-Content "$Root\smartdns.conf"

Write-Host '==> registering services'
& $NssmExe install OfogheamnDNS $SmartDnsExe "-c `"$Root\smartdns.conf`""
& $NssmExe set OfogheamnDNS Start SERVICE_AUTO_START
& $NssmExe install OfogheamnProxy $SingBoxExe "run -c `"$Root\singbox.json`""
& $NssmExe set OfogheamnProxy Start SERVICE_AUTO_START
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
  & $NssmExe install OfogheamnPanel $py.Source "`"$Src\panel\panel.py`""
  & $NssmExe set OfogheamnPanel AppEnvironmentExtra "OFOGH_ETC=$Root"
  & $NssmExe set OfogheamnPanel Start SERVICE_AUTO_START
} else {
  Write-Host 'Python not found: panel skipped (winget install Python.Python.3, then re-run)'
}

Write-Host '==> firewall'
foreach ($p in 53, 853, 443, 2080, 8080) {
  New-NetFirewallRule -DisplayName "Ofogheamn $p" -Direction Inbound -LocalPort $p `
    -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
  New-NetFirewallRule -DisplayName "Ofogheamn $p UDP" -Direction Inbound -LocalPort $p `
    -Protocol UDP -Action Allow -ErrorAction SilentlyContinue | Out-Null
}
Start-Service OfogheamnDNS, OfogheamnProxy -ErrorAction SilentlyContinue
Write-Host ''
Write-Host 'Ofogheamn DNS is installed. Set the panel password hash and'
Write-Host 'proxy users in the panel config under' $Root '(see README, Windows section).'

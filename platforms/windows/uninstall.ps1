# Ofogheamn DNS — Windows node uninstaller (run elevated)
#Requires -RunAsAdministrator
$Root = "C:\Program Files\OfogheamnDNS"
# Guarded: on a machine where the install never finished (or a
# second uninstall run) the folder is gone, and the unguarded
# Push-Location used to spray raw errors (v1.4 fix).
if (Test-Path "$Root\AdGuardHome.exe") {
    Push-Location $Root
    & .\AdGuardHome.exe -s stop 2>$null
    & .\AdGuardHome.exe -s uninstall 2>$null
    Pop-Location
}
Stop-ScheduledTask -TaskName "OfogheamnProxy" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1   # let sing-box exit before its files are removed
Unregister-ScheduledTask -TaskName "OfogheamnProxy" -Confirm:$false -ErrorAction SilentlyContinue
foreach ($n in "Ofogh DNS UDP", "Ofogh DNS TCP", "Ofogh DoT", "Ofogh Proxy", "Ofogh AGH Panel", "Ofogh Mesh Report") {
    Remove-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue
}
Remove-Item $Root -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Removed. Config/data kept in C:\ProgramData\OfogheamnDNS (delete manually if wanted)."

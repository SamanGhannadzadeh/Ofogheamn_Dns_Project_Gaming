# Ofogheamn DNS — Windows node uninstaller (run elevated)
#Requires -RunAsAdministrator
$Root = "C:\Program Files\OfogheamnDNS"
Push-Location $Root
& .\AdGuardHome.exe -s stop 2>$null
& .\AdGuardHome.exe -s uninstall 2>$null
Pop-Location
Stop-ScheduledTask -TaskName "OfogheamnProxy" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "OfogheamnProxy" -Confirm:$false -ErrorAction SilentlyContinue
foreach ($n in "Ofogh DNS UDP", "Ofogh DNS TCP", "Ofogh DoT", "Ofogh Proxy", "Ofogh AGH Panel", "Ofogh Mesh Report") {
    Remove-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue
}
Remove-Item $Root -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Removed. Config/data kept in C:\ProgramData\OfogheamnDNS (delete manually if wanted)."

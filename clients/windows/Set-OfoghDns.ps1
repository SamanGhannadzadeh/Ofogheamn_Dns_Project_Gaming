#Requires -RunAsAdministrator
<#
  Ofogh Amn DNS for Windows.
  Usage:
    .\Set-OfoghDns.ps1           -> set node DNS on all active adapters
    .\Set-OfoghDns.ps1 -Restore  -> back to DHCP (automatic DNS)
#>
param([switch]$Restore)

$Node = "180.149.45.237"
$adapters = Get-NetAdapter -Physical | Where-Object { $_.Status -eq "Up" }
if (-not $adapters) { Write-Host "No active adapter found."; exit 1 }

foreach ($a in $adapters) {
    if ($Restore) {
        Set-DnsClientServerAddress -InterfaceIndex $a.ifIndex -ResetServerAddresses
        Write-Host "$($a.Name): DNS back to automatic (DHCP)"
    } else {
        Set-DnsClientServerAddress -InterfaceIndex $a.ifIndex -ServerAddresses ($Node, $Node)
        Write-Host "$($a.Name): DNS set to $Node"
    }
}
Clear-DnsClientCache
Write-Host "Done."

# Encrypted DNS (DoH), enabled automatically once dns.ofogheamn.ir is
# publicly registered and the node carries a public certificate:
#   netsh dns add encryption server=$Node template=https://dns.ofogheamn.ir/dns-query autoupgrade=yes udpfallback=no

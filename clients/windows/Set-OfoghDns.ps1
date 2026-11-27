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

if (-not $Restore) {
    # Encrypted DNS (DoH) — the node name is public and its certificate
    # is publicly trusted, so Windows accepts the template directly.
    netsh dns add encryption server=$Node template=https://ofogheamn.mytunnel.org/dns-query autoupgrade=yes udpfallback=no | Out-Null
    Write-Host "DoH template registered for $Node"
}
Write-Host "Done."

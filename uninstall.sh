#!/bin/bash
# Remove Ofogheamn DNS completely (services, files, firewall chain).
set -e
[ "$(id -u)" = "0" ] || { echo "run with sudo"; exit 1; }
systemctl disable --now ofogheamn-dns ofogheamn-panel ofogheamn-proxy cod-warmup.timer 2>/dev/null || true
rm -f /etc/systemd/system/ofogheamn-dns.service /etc/systemd/system/ofogheamn-panel.service \
      /etc/systemd/system/ofogheamn-proxy.service /etc/systemd/system/cod-warmup.service \
      /etc/systemd/system/cod-warmup.timer
rm -f /etc/sysctl.d/99-ofogheamn-dns.conf
rm -f /usr/local/bin/ofogheamn-dns /usr/local/bin/smartdns /usr/local/bin/sing-box \
      /usr/local/bin/cod-warmup /usr/local/bin/ofogheamn-firewall
rm -rf /usr/local/lib/ofogheamn-dns
iptables -F OFOGH_DNS_IN 2>/dev/null && iptables -X OFOGH_DNS_IN 2>/dev/null || true
rm -rf /etc/ofogheamn-dns /var/cache/ofogheamn-dns /var/log/ofogheamn-dns
systemctl daemon-reload
echo "Ofogheamn DNS removed."

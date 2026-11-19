#!/bin/bash
# Remove Ofogheamn DNS completely (services, files, firewall chain).
set -e
[ "$(id -u)" = "0" ] || { echo "run with sudo"; exit 1; }
systemctl disable --now ofogheamn-dns ofogheamn-panel ofogheamn-proxy cod-warmup.timer ofogheamn-health.timer 2>/dev/null || true
rm -f /etc/systemd/system/ofogheamn-dns.service /etc/systemd/system/ofogheamn-panel.service \
      /etc/systemd/system/ofogheamn-proxy.service /etc/systemd/system/cod-warmup.service \
      /etc/systemd/system/cod-warmup.timer /etc/systemd/system/ofogheamn-health.service \
      /etc/systemd/system/ofogheamn-health.timer /etc/systemd/system/ofogheamn-wg.service \
      /etc/systemd/system/ofogheamn-mesh.service /etc/systemd/system/ofogheamn-blocklist.service \
      /etc/systemd/system/ofogheamn-blocklist.timer
rm -f /etc/sysctl.d/99-ofogheamn-dns.conf
rm -f /usr/local/bin/ofogheamn-dns /usr/local/bin/smartdns /usr/local/bin/sing-box \
      /usr/local/bin/cod-warmup /usr/local/bin/ofogheamn-firewall \
      /usr/local/bin/ofogheamn-region.py /usr/local/bin/ofogheamn-bench.py \
      /usr/local/bin/ofogheamn-health.py /usr/local/bin/ofogheamn-wg-peer.py \
      /usr/local/bin/ofogheamn-mesh.py
rm -rf /usr/local/lib/ofogheamn-dns
iptables -F OFOGH_DNS_IN 2>/dev/null && iptables -X OFOGH_DNS_IN 2>/dev/null || true
rm -rf /etc/ofogheamn-dns /var/cache/ofogheamn-dns /var/log/ofogheamn-dns
systemctl daemon-reload
echo "Ofogheamn DNS removed."

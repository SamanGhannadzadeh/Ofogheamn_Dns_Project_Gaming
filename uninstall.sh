#!/bin/bash
# Remove Ofogheamn DNS completely (services, files, firewall chain).
set -e
[ "$(id -u)" = "0" ] || { echo "run with sudo"; exit 1; }
systemctl disable --now ofogheamn-dns ofogheamn-panel ofogheamn-proxy cod-warmup.timer ofogheamn-health.timer ofogheamn-recursive 2>/dev/null || true
# Also disable the units install.sh (or the owner, for mesh)
# enables conditionally — deleting an enabled unit's file without
# disabling it leaves a dangling wants symlink behind (v1.4 fix).
systemctl disable --now ofogheamn-vpn ofogheamn-wg ofogheamn-mesh ofogheamn-blocklist.timer 2>/dev/null || true
systemctl stop strongswan-starter xl2tpd pptpd 2>/dev/null || true
ip link del wg0 2>/dev/null || true
rm -f /etc/systemd/system/ofogheamn-dns.service /etc/systemd/system/ofogheamn-panel.service \
      /etc/systemd/system/ofogheamn-proxy.service /etc/systemd/system/cod-warmup.service \
      /etc/systemd/system/cod-warmup.timer /etc/systemd/system/ofogheamn-health.service \
      /etc/systemd/system/ofogheamn-health.timer /etc/systemd/system/ofogheamn-wg.service \
      /etc/systemd/system/ofogheamn-vpn.service \
      /etc/systemd/system/ofogheamn-mesh.service /etc/systemd/system/ofogheamn-blocklist.service \
      /etc/systemd/system/ofogheamn-blocklist.timer /etc/systemd/system/ofogheamn-recursive.service
rm -f /etc/sysctl.d/99-ofogheamn-dns.conf
rm -f /usr/local/bin/ofogheamn-dns /usr/local/bin/smartdns /usr/local/bin/sing-box \
      /usr/local/bin/cod-warmup /usr/local/bin/ofogheamn-firewall \
      /usr/local/bin/ofogheamn-region.py /usr/local/bin/ofogheamn-bench.py \
      /usr/local/bin/ofogheamn-health.py /usr/local/bin/ofogheamn-wg-peer \
      /usr/local/bin/ofogheamn-vpn-setup /usr/local/bin/ofogheamn-wg-setup \
      /usr/local/bin/ofogheamn-mesh.py /usr/local/bin/update-blocklist
rm -rf /usr/local/lib/ofogheamn-dns
iptables -F OFOGH_DNS_IN 2>/dev/null && iptables -X OFOGH_DNS_IN 2>/dev/null || true
# Remove the ufw openings install.sh added (only where ufw is
# active, mirroring the installer's condition).
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  for r in 53 853 443/udp 443/tcp 2080 8080 51820/udp 500/udp 4500/udp 1701/udp 1723/tcp; do
    ufw delete allow "$r" >/dev/null 2>&1 || true
  done
  ufw delete allow proto esp >/dev/null 2>&1 || true
  ufw delete allow proto gre >/dev/null 2>&1 || true
fi
# Credential files the VPN setup rendered from vpn.conf: the PSK
# file is wholly ours; chap-secrets is removed only when it
# carries our rendered header (an admin's own entries stay).
rm -f /etc/ipsec.secrets
grep -q '^# rendered by ofogheamn-vpn-setup' /etc/ppp/chap-secrets 2>/dev/null && rm -f /etc/ppp/chap-secrets
rm -rf /etc/ofogheamn-dns /var/cache/ofogheamn-dns /var/log/ofogheamn-dns
userdel ofodns 2>/dev/null || true
systemctl daemon-reload
echo "Ofogheamn DNS removed."

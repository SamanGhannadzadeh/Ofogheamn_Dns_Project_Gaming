#!/bin/bash
# Gateway enforcement, layer 3 — run ON the LAN gateway.
# Encrypted DNS to PUBLIC resolvers is dropped by destination IP,
# so DoH (443) / DoT (853) clients that ignore DHCP and ignore the
# port-53 redirect simply fail — and fall back to the system DNS,
# which is the Ofogheamn server. Together with redirect-53.sh
# this is what makes ALL subscriber DNS pass through the server.
#
#   LAN_NET=192.168.1.0/24 sudo bash block-doh-ips.sh
set -e
LAN_NET="${LAN_NET:?set LAN_NET, e.g. 192.168.1.0/24}"

# Well-known public resolver IPs (Cloudflare, Google, Quad9,
# AdGuard, OpenDNS, Control D, CleanBrowsing, NextDNS anycast).
PUBLIC_DNS_IPS="
1.1.1.1 1.0.0.1 8.8.8.8 8.8.4.4 9.9.9.9 149.112.112.112
94.140.14.14 94.140.15.15 208.67.222.222 208.67.220.220
76.76.2.0 76.76.10.0 185.228.168.9 185.228.169.9 45.90.28.0 45.90.30.0
"

for ip in $PUBLIC_DNS_IPS; do
  for proto in udp tcp; do
    for port in 443 853; do
      iptables -C FORWARD -s "$LAN_NET" -d "$ip" -p "$proto" --dport "$port" -j DROP 2>/dev/null \
        || iptables -A FORWARD -s "$LAN_NET" -d "$ip" -p "$proto" --dport "$port" -j DROP
    done
  done
done
echo "Public encrypted-DNS egress blocked for $LAN_NET"

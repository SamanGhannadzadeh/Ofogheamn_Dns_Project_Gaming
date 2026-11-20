#!/bin/bash
# Gateway enforcement — run ON the LAN gateway (Linux router).
# Forces every subscriber device's DNS through the Ofogheamn DNS
# server and blocks the usual bypass transports:
#   * UDP/TCP 53 from the LAN  -> DNAT to the DNS server
#   * TCP/UDP 853 (DoT/DoQ)    -> dropped for LAN clients
#     (public DoH on 443 cannot be port-blocked; the resolver's
#      canary rule in force-dns.conf stops browser auto-DoH, and
#      managed devices should be pointed at this DNS directly.)
#
#   DNS_SERVER=192.168.1.2 LAN_NET=192.168.1.0/24 sudo bash redirect-53.sh
set -e
DNS_SERVER="${DNS_SERVER:?set DNS_SERVER to the Ofogheamn DNS server IP}"
LAN_NET="${LAN_NET:?set LAN_NET, e.g. 192.168.1.0/24}"
add() { local t="$1"; shift; iptables -t "$t" -C "$@" 2>/dev/null || iptables -t "$t" -A "$@"; }

for proto in udp tcp; do
  add nat PREROUTING -s "$LAN_NET" ! -d "$DNS_SERVER" -p "$proto" --dport 53 -j DNAT --to-destination "$DNS_SERVER":53
  add filter FORWARD -s "$LAN_NET" -p "$proto" --dport 853 -j DROP
done
echo "DNS enforcement active: $LAN_NET -> $DNS_SERVER (53 redirected, 853 blocked)"

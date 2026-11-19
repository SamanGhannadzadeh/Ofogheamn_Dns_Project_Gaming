#!/bin/bash
# Bring up the Ofogheamn WireGuard gaming tunnel (wg0).
# Used by ofogheamn-wg.service instead of wg-quick so it works
# the same on a plain server and inside Saman OS Server.
# Config: /etc/ofogheamn-dns/wg0.conf (standard WireGuard format,
# managed by the panel/CLI peer tools). Peers' DNS = this server,
# so lookups AND game traffic share one path:
#   device -> tunnel -> this server (DNS + NAT) -> game servers.
set -u
CONF=/etc/ofogheamn-dns/wg0.conf
[ -r "$CONF" ] || { echo "no wg0.conf"; exit 1; }
ip link del wg0 2>/dev/null || true
ip link add wg0 type wireguard
wg setconf wg0 "$CONF"
ip addr add 10.66.0.1/24 dev wg0
ip link set wg0 up
sysctl -qw net.ipv4.ip_forward=1
EXT="$(ip route show default | awk '{print $5; exit}')"
iptables -t nat -C POSTROUTING -s 10.66.0.0/24 -o "$EXT" -j MASQUERADE 2>/dev/null \
  || iptables -t nat -A POSTROUTING -s 10.66.0.0/24 -o "$EXT" -j MASQUERADE
echo "wg0 up (egress: $EXT)"

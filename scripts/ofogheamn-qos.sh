#!/bin/sh
# ofogheamn-qos — gaming QoS for the node (optional, idempotent).
#
# Marks game-bound UDP leaving the node with DSCP EF so it wins
# queues on the way out: by game port, by Call of Duty ranges
# (lists/cod-ip-ranges.txt) and by aggregated datacenter ranges
# (lists/datacenter-ranges.txt — build it with update-dc-ranges).
# Also puts the egress interface on the fq qdisc.
#
# Run after install and after every update-dc-ranges refresh.
# Safe to re-run: every rule is check-then-add.
set -u
ETC=/etc/ofogheamn-dns
IFACE="$(ip route show default 2>/dev/null | awk '{print $5; exit}')"
[ -n "$IFACE" ] || IFACE=eth0
command -v ipset >/dev/null || { echo "ipset missing: apt install ipset" >&2; exit 1; }

load_set() {
  name="$1"; file="$2"
  [ -f "$file" ] || return 0
  ipset create "$name" hash:net -exist
  ipset flush "$name"
  grep -vE '^[[:space:]]*(#|$)' "$file" | while read -r r; do
    ipset add "$name" "$r" -exist 2>/dev/null
  done
  iptables -t mangle -C OUTPUT -o "$IFACE" -p udp -m set --match-set "$name" dst \
    -j DSCP --set-dscp-class EF 2>/dev/null || \
  iptables -t mangle -A OUTPUT -o "$IFACE" -p udp -m set --match-set "$name" dst \
    -j DSCP --set-dscp-class EF
}

for p in 3074 3075 3076 9308; do
  iptables -t mangle -C OUTPUT -o "$IFACE" -p udp --dport "$p" \
    -j DSCP --set-dscp-class EF 2>/dev/null || \
  iptables -t mangle -A OUTPUT -o "$IFACE" -p udp --dport "$p" \
    -j DSCP --set-dscp-class EF
done

load_set cod "$ETC/lists/cod-ip-ranges.txt"
load_set dc "$ETC/lists/datacenter-ranges.txt"
tc qdisc replace dev "$IFACE" root fq 2>/dev/null || true
echo "ofogheamn-qos applied on $IFACE"

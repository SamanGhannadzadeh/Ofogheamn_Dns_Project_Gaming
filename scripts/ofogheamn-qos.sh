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
  # All ports, both protocols: game traffic to these ranges is
  # marked EF whether it rides UDP (gameplay) or TCP (logins,
  # downloads, store) — the set rule carries no port filter.
  for proto in udp tcp; do
    iptables -t mangle -C OUTPUT -o "$IFACE" -p "$proto" -m set --match-set "$name" dst \
      -j DSCP --set-dscp-class EF 2>/dev/null || \
    iptables -t mangle -A OUTPUT -o "$IFACE" -p "$proto" -m set --match-set "$name" dst \
      -j DSCP --set-dscp-class EF
  done
}

# Well-known console/game ports to ANY destination (the ranges
# above cannot cover every game server on earth): Xbox Live
# 88/500/3074/3544/4500, PlayStation Network 3478/3479/3480,
# Call of Duty 3075/3076/9308, Steam/Source 27015.
for p in 88 500 3074 3075 3076 3478 3479 3544 4500 9308 27015; do
  iptables -t mangle -C OUTPUT -o "$IFACE" -p udp --dport "$p" \
    -j DSCP --set-dscp-class EF 2>/dev/null || \
  iptables -t mangle -A OUTPUT -o "$IFACE" -p udp --dport "$p" \
    -j DSCP --set-dscp-class EF
done
for p in 3074 3480 27015; do
  iptables -t mangle -C OUTPUT -o "$IFACE" -p tcp --dport "$p" \
    -j DSCP --set-dscp-class EF 2>/dev/null || \
  iptables -t mangle -A OUTPUT -o "$IFACE" -p tcp --dport "$p" \
    -j DSCP --set-dscp-class EF
done

load_set cod "$ETC/lists/cod-ip-ranges.txt"
load_set dc "$ETC/lists/datacenter-ranges.txt"
tc qdisc replace dev "$IFACE" root fq 2>/dev/null || true
echo "ofogheamn-qos applied on $IFACE"

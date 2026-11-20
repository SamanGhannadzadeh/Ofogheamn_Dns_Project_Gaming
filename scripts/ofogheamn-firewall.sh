#!/bin/bash
# Apply the DNS access mode (public / private) with iptables.
#   ofogheamn-firewall            re-apply the saved mode
# Mode + allowlist live in /etc/ofogheamn-dns/{mode.conf,allowlist.txt}
# A dedicated chain OFOGH_DNS_IN guards the DNS ports (53, 853, 443)
# on INPUT. Public mode = chain empty (world may query).
# Private mode = only allowlisted sources + localhost pass; the
# rest is dropped. The panel (8080) and the proxy (2080) are NOT
# touched here: the panel has its own login, the proxy its users.
set -u
ETC=/etc/ofogheamn-dns
CHAIN=OFOGH_DNS_IN
MODE=public
[ -r "$ETC/mode.conf" ] && MODE="$(grep -E '^mode=' "$ETC/mode.conf" | cut -d= -f2)"
MODE="${MODE:-public}"

iptables -N "$CHAIN" 2>/dev/null || iptables -F "$CHAIN"
for proto in udp tcp; do
  for port in 53 853 443; do
    iptables -C INPUT -p "$proto" --dport "$port" -j "$CHAIN" 2>/dev/null \
      || iptables -I INPUT 1 -p "$proto" --dport "$port" -j "$CHAIN"
  done
done

if [ "$MODE" = "public" ]; then
  # Public-resolver abuse guard: per-source rate limit on the
  # plain DNS ports (open resolvers are amplification targets).
  # hashlimit (--hashlimit = --hashlimit-upto) matches packets that
  # are WITHIN the rate, so the construction is: within-limit ->
  # RETURN (carry on to INPUT's policy), anything past the limit
  # falls through to the DROP below. The intuitive "-j DROP" on
  # the hashlimit line itself does the exact opposite — it drops
  # every well-behaved client and lets floods through (verified
  # against the iptables-extensions man page; v1.4 fix).
  for proto in udp tcp; do
    iptables -A "$CHAIN" -p "$proto" --dport 53 -m hashlimit \
      --hashlimit-name "ofogh_dns_$proto" --hashlimit 120/second \
      --hashlimit-burst 240 --hashlimit-mode srcip -j RETURN
    iptables -A "$CHAIN" -p "$proto" --dport 53 -j DROP
  done
fi

if [ "$MODE" = "private" ]; then
  iptables -A "$CHAIN" -i lo -j RETURN
  if [ -r "$ETC/allowlist.txt" ]; then
    while read -r net; do
      case "$net" in ''|\#*) continue ;; esac
      iptables -A "$CHAIN" -s "$net" -j RETURN
    done < "$ETC/allowlist.txt"
  fi
  iptables -A "$CHAIN" -j DROP
  echo "mode=private applied (allowlist only)"
else
  echo "mode=public applied (open resolver)"
fi

# VPN servers (L2TP/IPsec + PPTP): accept the tunnel ports on INPUT.
# Idempotent. UDP 1701 is only ever useful inside IPsec (the PSK
# gate is strongSwan on 500/4500), but xl2tpd binds it plainly, so
# it is accepted like the rest; ESP has no port (IP protocol 50),
# GRE (protocol 47) carries the PPTP payload after TCP 1723 setup.
for spec in "udp 500" "udp 4500" "udp 1701" "tcp 1723"; do
  set -- $spec
  iptables -C INPUT -p "$1" --dport "$2" -j ACCEPT 2>/dev/null \
    || iptables -I INPUT 1 -p "$1" --dport "$2" -j ACCEPT
done
for proto in esp gre; do
  iptables -C INPUT -p "$proto" -j ACCEPT 2>/dev/null \
    || iptables -I INPUT 1 -p "$proto" -j ACCEPT
done

# MSS clamping for tunnel traffic (research 2026-11-19): peers behind
# PPPoE/mobile paths announce MSS values the tunnel cannot carry;
# clamping TCP MSS to the path MTU on forwarding stops silent
# fragmentation stalls. Idempotent; UDP (game traffic) is untouched.
for iface in wg0 ppp+; do
  for dir in -i -o; do
    iptables -t mangle -C FORWARD $dir "$iface" -p tcp --tcp-flags SYN,RST SYN \
      -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null \
      || iptables -t mangle -A FORWARD $dir "$iface" -p tcp --tcp-flags SYN,RST SYN \
           -j TCPMSS --clamp-mss-to-pmtu
  done
done

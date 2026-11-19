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
  for proto in udp tcp; do
    for port in 53; do
      iptables -A "$CHAIN" -p "$proto" --dport "$port" -m hashlimit \
        --hashlimit-name "ofogh_dns_$proto" --hashlimit 120/second \
        --hashlimit-burst 240 --hashlimit-mode srcip -j DROP
    done
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

# MSS clamping for tunnel traffic (research 2026-11-19): peers behind
# PPPoE/mobile paths announce MSS values the tunnel cannot carry;
# clamping TCP MSS to the path MTU on wg0 forwarding stops silent
# fragmentation stalls. Idempotent; UDP (game traffic) is untouched.
for dir in -i -o; do
  iptables -t mangle -C FORWARD $dir wg0 -p tcp --tcp-flags SYN,RST SYN \
    -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null \
    || iptables -t mangle -A FORWARD $dir wg0 -p tcp --tcp-flags SYN,RST SYN \
         -j TCPMSS --clamp-mss-to-pmtu
done

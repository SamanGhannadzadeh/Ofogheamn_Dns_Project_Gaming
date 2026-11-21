#!/bin/bash
# Apply the DNS access mode (public / private) with iptables.
#   ofogheamn-firewall            re-apply the saved mode
# Mode + allowlist live in /etc/ofogheamn-dns/{mode.conf,allowlist.txt}
# A dedicated chain OFOGH_DNS_IN guards the DNS ports (53, 853, 443)
# on INPUT. Public mode = chain empty (world may query).
# Private mode = only allowlisted sources + localhost pass; the
# rest is dropped. The panel (8080) and the proxy (2080) are NOT
# touched here: the panel has its own login, the proxy its users.
# Exception: the optional no-auth CONSOLE proxy port (console.json)
# has no login to protect it, so this script guards it — allowlist
# chain in private mode, hard DROP in public mode.
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

# Console proxy port (opt-in, no-auth — see gen-singbox-config.py):
# consoles have no proxy-auth fields, so this port's only protection
# is right here. Private mode routes it through the allowlist chain
# like the DNS ports; public mode drops it outright — a no-auth
# proxy must never be world-reachable.
CPORT=""
if [ -r "$ETC/console.json" ]; then
  CPORT="$(python3 -c "import json;print(json.load(open('$ETC/console.json'))['port'])" 2>/dev/null || true)"
fi
if [ -n "$CPORT" ]; then
  if [ "$MODE" = "private" ]; then
    for proto in udp tcp; do
      iptables -C INPUT -p "$proto" --dport "$CPORT" -j "$CHAIN" 2>/dev/null \
        || iptables -I INPUT 1 -p "$proto" --dport "$CPORT" -j "$CHAIN"
    done
    echo "console port $CPORT: allowlist only (private)"
  else
    for proto in udp tcp; do
      iptables -C INPUT -p "$proto" --dport "$CPORT" -j DROP 2>/dev/null \
        || iptables -I INPUT 1 -p "$proto" --dport "$CPORT" -j DROP
    done
    echo "console port $CPORT: blocked (public mode)"
  fi
fi

# Hysteria2 tunnel port (opt-in, password-authenticated — see
# gen-singbox-config.py): private mode routes it through the
# allowlist chain like the other service ports; public mode opens
# it, because unlike the console port it has real auth.
HY2=""
if [ -r "$ETC/hysteria2.json" ]; then
  HY2="$(python3 -c "import json;print(json.load(open('$ETC/hysteria2.json'))['port'])" 2>/dev/null || true)"
fi
if [ -n "$HY2" ]; then
  if [ "$MODE" = "private" ]; then
    iptables -C INPUT -p udp --dport "$HY2" -j "$CHAIN" 2>/dev/null \
      || iptables -I INPUT 1 -p udp --dport "$HY2" -j "$CHAIN"
    echo "hysteria2 port $HY2: allowlist only (private)"
  else
    iptables -C INPUT -p udp --dport "$HY2" -j ACCEPT 2>/dev/null \
      || iptables -I INPUT 1 -p udp --dport "$HY2" -j ACCEPT
    echo "hysteria2 port $HY2: open (password auth)"
  fi
fi

# Hysteria2 port hopping: a client may land on any UDP port in
# hop_range; NAT-redirect the whole range to the real port. The
# INPUT rules above still filter the redirected packets (they
# arrive with the real port as destination), so private mode
# keeps its allowlist. Idempotent.
if [ -n "$HY2" ] && [ -r "$ETC/hysteria2.json" ]; then
  HOP="$(python3 -c "import json;print(json.load(open('$ETC/hysteria2.json')).get('hop_range',''))" 2>/dev/null || true)"
  if [ -n "$HOP" ]; then
    HOPDPT="${HOP%-*}:${HOP#*-}"
    iptables -t nat -C PREROUTING -p udp --dport "$HOPDPT" -j REDIRECT --to-ports "$HY2" 2>/dev/null \
      || iptables -t nat -A PREROUTING -p udp --dport "$HOPDPT" -j REDIRECT --to-ports "$HY2"
    echo "hysteria2 port hopping: udp/$HOP -> $HY2"
  fi
fi

# TUIC v5 (UDP) and AnyTLS (TCP): opt-in, password-authenticated,
# same treatment as Hysteria2 — allowlist in private mode, open
# in public mode.
for spec in "tuic.json udp TUIC" "anytls.json tcp AnyTLS" "hysteria2-gecko.json udp Hysteria2-Gecko" "reality.json tcp REALITY"; do
  set -- $spec
  if [ -r "$ETC/$1" ]; then
    P="$(python3 -c "import json;print(json.load(open('$ETC/$1'))['port'])" 2>/dev/null || true)"
    if [ -n "$P" ]; then
      if [ "$MODE" = "private" ]; then
        iptables -C INPUT -p "$2" --dport "$P" -j "$CHAIN" 2>/dev/null \
          || iptables -I INPUT 1 -p "$2" --dport "$P" -j "$CHAIN"
        echo "$3 port $P: allowlist only (private)"
      else
        iptables -C INPUT -p "$2" --dport "$P" -j ACCEPT 2>/dev/null \
          || iptables -I INPUT 1 -p "$2" --dport "$P" -j ACCEPT
        echo "$3 port $P: open (password auth)"
      fi
    fi
  fi
done

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

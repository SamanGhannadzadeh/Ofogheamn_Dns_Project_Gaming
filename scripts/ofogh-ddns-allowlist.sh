#!/bin/bash
# ofogh-ddns-allowlist — keep the private-mode allowlist in sync
# with the admin's Dynamic DNS hostname(s).
#
# The problem: a private node trusts the admin by home IP, but a
# home connection's public IP changes (PPPoE reconnect, ISP
# rotation) and the admin is locked out of their own node. The
# modem's Dynamic DNS page exists for exactly this: it keeps a
# hostname (No-IP / DynDNS / TZO) pointing at the home IP.
#
# This keeper resolves the hostname(s) listed in
# /etc/ofogheamn-dns/ddns.conf (one per line) every 5 minutes
# (ofogh-ddns.timer) and swaps the DDNS-contributed IPs in
# allowlist.txt, re-applying the firewall only when they change.
# It only ever removes IPs it added itself — they are tracked in
# ddns-state.txt; hand-written allowlist lines are never touched.
# If a lookup returns nothing (DNS hiccup, lapsed hostname), the
# old IPs stay: a bad lookup must never lock the admin out.
#
# Managed by:  ofogheamn-dns ddns set <hostname>|clear|status
set -u
ETC="${OFOGH_ETC:-/etc/ofogheamn-dns}"
CONF="$ETC/ddns.conf"
ALLOW="$ETC/allowlist.txt"
STATE="$ETC/ddns-state.txt"
[ -f "$CONF" ] || exit 0

resolve() {
  dig +short A "$1" @127.0.0.1 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' && return 0
  dig +short A "$1" 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'
}

NEW="$(grep -vE '^[[:space:]]*(#|$)' "$CONF" | while read -r host; do resolve "$host"; done | sort -u)"
[ -n "$NEW" ] || exit 0
OLD="$(sort -u "$STATE" 2>/dev/null || true)"
[ "$NEW" = "$OLD" ] && exit 0

touch "$ALLOW"
if [ -n "$OLD" ]; then
  grep -vxF -f "$STATE" "$ALLOW" > "$ALLOW.tmp" || true
  mv "$ALLOW.tmp" "$ALLOW"
fi
for ip in $NEW; do
  grep -qxF "$ip" "$ALLOW" || echo "$ip" >> "$ALLOW"
done
printf '%s\n' $NEW > "$STATE"
if [ -x /usr/local/bin/ofogheamn-firewall ]; then
  bash /usr/local/bin/ofogheamn-firewall >/dev/null 2>&1 || true
fi
logger -t ofogh-ddns "allowlist DDNS IPs now: $(echo $NEW | tr '\n' ' ')" 2>/dev/null || true

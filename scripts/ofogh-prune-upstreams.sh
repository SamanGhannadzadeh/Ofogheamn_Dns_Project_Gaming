#!/bin/bash
# Prune slow upstreams (Google 47ms, Quad9 74ms vs 2-4ms leaders) from
# the edge and default groups. Gaming group untouched by design.
set -e
CONF="${SMARTDNS_CONF:-/etc/ofogheamn-dns/smartdns.conf}"
cp "$CONF" "$CONF.bak-prune-$(date +%Y%m%d%H%M)"

sed -i '/^server 8\.8\.8\.8 -group edge /d' "$CONF"
sed -i '/^server 8\.8\.8\.8$/d' "$CONF"
sed -i '/^server 9\.9\.9\.9$/d' "$CONF"

echo "remaining server lines:"
grep -cE '^server ' "$CONF"
grep -nE '^server ' "$CONF" | grep -E 'edge|^2(0[5-9]|1[0-9]):' || true
grep -nE '^server (8\.8\.8\.8|9\.9\.9\.9)( |$)' "$CONF" && echo "STILL PRESENT - BAD" || echo "slow members gone"

systemctl restart ofogheamn-dns.service
sleep 2
echo "dns: $(systemctl is-active ofogheamn-dns.service)"
echo "default-group cold test (www.bbc.com):"
dig @127.0.0.1 www.bbc.com +stats 2>/dev/null | grep -E "Query time|status:"
dig @127.0.0.1 www.bbc.com +stats 2>/dev/null | grep "Query time"
echo "edge-group test (psn name):"
dig @127.0.0.1 profile.callofduty.com +stats 2>/dev/null | grep -E "Query time|status:"
echo PRUNEDONE

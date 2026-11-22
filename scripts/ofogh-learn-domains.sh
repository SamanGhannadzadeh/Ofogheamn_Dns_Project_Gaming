#!/bin/bash
# ofogh-learn-domains.sh — teach the node the gaming domains its
# customers actually use. Mines the SmartDNS log for frequent
# domains that are in no set yet, resolves them, and keeps the
# ones whose A answers land inside the game (cod) or datacenter
# (dc) ipsets. Those join lists/learned.domains and from then on
# get the gaming treatment (edge group + fastest-response +
# cache warming). Runs daily from ofogh-learn.timer.
set -u
ETC=/etc/ofogheamn-dns
LOG=/var/log/ofogheamn-dns/smartdns.log
LEARNED="$ETC/lists/learned.domains"
MIN_COUNT=5
MAX_CANDIDATES=200
MAX_LEARNED=2000
[ -f "$LOG" ] || exit 0
command -v ipset >/dev/null || exit 0
touch "$LEARNED"

known=$(mktemp); cands=$(mktemp); hits=$(mktemp)
trap 'rm -f "$known" "$cands" "$hits"' EXIT
cat "$ETC"/lists/*.domains 2>/dev/null \
  | grep -vE '^[[:space:]]*(#|$)' | sort -u > "$known"

# Frequent queried names from the recent log tail.
tail -c 8000000 "$LOG" 2>/dev/null \
  | grep -oE "request: [a-zA-Z0-9.-]+, qtype" \
  | sed -E 's/^request: //; s/, qtype$//' \
  | sort | uniq -c | awk -v m="$MIN_COUNT" '$1 >= m {print $2}' \
  | grep -vxF -f "$known" | head -n "$MAX_CANDIDATES" > "$cands"

while IFS= read -r d; do
  [ -n "$d" ] || continue
  for ip in $(dig +short +time=2 +tries=1 @127.0.0.1 "$d" A 2>/dev/null \
              | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'); do
    if ipset test cod "$ip" >/dev/null 2>&1 \
       || ipset test dc "$ip" >/dev/null 2>&1; then
      echo "$d" >> "$hits"; break
    fi
  done
done < "$cands"

[ -s "$hits" ] || exit 0
sort -u "$LEARNED" "$hits" | head -n "$MAX_LEARNED" > "$LEARNED.new"
if ! cmp -s "$LEARNED.new" "$LEARNED"; then
  mv "$LEARNED.new" "$LEARNED"
  systemctl restart smartdns 2>/dev/null \
    || systemctl restart ofogheamn-dns 2>/dev/null || true
  echo "learned: $(wc -l < "$LEARNED") domains"
else
  rm -f "$LEARNED.new"
fi

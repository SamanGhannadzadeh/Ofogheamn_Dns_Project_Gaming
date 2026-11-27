#!/bin/bash
# Warm the whole gaming sets (A + AAAA) so every gaming lookup is
# a cache hit; serve-expired covers the gaps between runs.
# Failure backoff (v1.33, state shared with cod-warmup): names
# that keep failing — dead domains in the sets SERVFAIL every
# cycle — are skipped for 24 h after 4 consecutive failures. On
# the reference node ~11% of all resolver answers were
# warmer-driven SERVFAILs before this.
LISTS=/etc/ofogheamn-dns/lists
STATE=/var/cache/ofogheamn-dns/warm-fails.txt
mkdir -p "$(dirname "$STATE")"; touch "$STATE"
now=$(date +%s)
CAND="$(mktemp)"; TRY="$(mktemp)"; FAIL="$(mktemp)"
trap 'rm -f "$CAND" "$TRY" "$FAIL"' EXIT
# Two tiers (v1.42): the session ring (CoD + PSN sets) is small
# and latency-critical — it warms every 4 minutes at moderate
# parallelism. The bulk gaming catalogue is large; warming it
# at full tilt saturated the node's single vCPU for ~90 s per
# cycle and queued the proxy/tunnel traffic behind thousands
# of dig processes (visible as ping spikes). Bulk now warms on
# a 15-minute cadence, 2 workers, staggered starts.
case "${TIER:-hot}" in
  hot)
    FILES="$LISTS/cod.domains $LISTS/psn.domains"; P=4; STAGGER=0 ;;
  bulk)
    FILES="$(ls "$LISTS"/*.domains | grep -vE '/(cod|psn)\.domains$')"; P=2; STAGGER=0.05 ;;
  *) echo "unknown TIER=${TIER}" >&2; exit 2 ;;
esac
{ cat $FILES 2>/dev/null; } \
  | grep -vE '^[[:space:]]*(#|$)' | sort -u > "$CAND"
awk -v now="$now" 'FILENAME==ARGV[1] { if (($2+0)>=4 && now-($3+0)<86400) skip[$1]=1; next } !($1 in skip)' "$STATE" "$CAND" > "$TRY"
xargs -P "$P" -I{} sh -c '
  [ "'"$STAGGER"'" != "0" ] && sleep "'"$STAGGER"'"
  a="$(dig +short +time=2 +tries=1 @127.0.0.1 "{}" A 2>/dev/null)"
  b="$(dig +short +time=2 +tries=1 @127.0.0.1 "{}" AAAA 2>/dev/null)"
  [ -z "$a" ] && [ -z "$b" ] && echo "{}"
' < "$TRY" > "$FAIL"
awk -v now="$now" '
  FILENAME==ARGV[1] { cnt[$1]=$2; ts[$1]=$3; next }
  FILENAME==ARGV[2] { tried[$1]=1; next }
  FILENAME==ARGV[3] { failed[$1]=1; next }
  END {
    for (n in cnt) {
      if (n in tried) { if (n in failed) print n, cnt[n]+1, now }
      else print n, cnt[n], ts[n]
    }
    for (n in failed) if (!(n in cnt)) print n, 1, now
  }' "$STATE" "$TRY" "$FAIL" > "$STATE.new"
mv "$STATE.new" "$STATE"

#!/bin/bash
# "Match-Ready" cache warmer — an Ofogheamn DNS method.
# Every few minutes (cod-warmup.timer) re-resolve every Call of
# Duty / Warzone domain through the local server, so:
#   * the cache entry is always fresh (never a cold lookup when
#     a player launches the game or a match starts), and
#   * SmartDNS re-runs its fastest-IP measurement regularly, so
#     the cached winner tracks changing network conditions.
set -u
# CoD list: warmed every run (every 4 min). The big gaming list is
# warmed in rotating quarters, so each gaming domain is refreshed
# at least every ~16 minutes without hammering upstreams.
COD=/etc/ofogheamn-dns/lists/cod.domains
GAMING=/etc/ofogheamn-dns/lists/gaming.domains
# Failure backoff (v1.33, state shared with ofogh-warm-all): the
# sets contain dead domains that SERVFAIL every cycle — on the
# reference node ~11% of all resolver answers were warmer-driven
# SERVFAILs, flooding the log and burning CPU on a 1-core box.
# A name that fails 4 runs in a row is skipped for 24 h.
STATE=/var/cache/ofogheamn-dns/warm-fails.txt
mkdir -p "$(dirname "$STATE")"; touch "$STATE"
now=$(date +%s)
CAND="$(mktemp)"; TRY="$(mktemp)"; FAIL="$(mktemp)"
trap 'rm -f "$CAND" "$TRY" "$FAIL"' EXIT
{
  grep -vE '^\s*(#|$)' "$COD" 2>/dev/null
  if [ -r "$GAMING" ]; then
    total=$(grep -cvE '^\s*(#|$)' "$GAMING" 2>/dev/null || true)
    if [ "${total:-0}" -gt 0 ]; then
      quarter=$(( (10#$(date +%M) / 4) % 4 ))
      grep -vE '^\s*(#|$)' "$GAMING" | awk -v q="$quarter" 'NR % 4 == q'
    fi
  fi
} | sort -u > "$CAND"
awk -v now="$now" 'FILENAME==ARGV[1] { if (($2+0)>=4 && now-($3+0)<86400) skip[$1]=1; next } !($1 in skip)' "$STATE" "$CAND" > "$TRY"
# Parallel since v1.14: the serial loop took minutes of
# wall-clock on big lists, so late entries were warmed long
# after early ones had already cooled again.
xargs -P 8 -I{} sh -c '
  a="$(dig +short +time=2 +tries=1 @127.0.0.1 "{}" A 2>/dev/null)"
  b="$(dig +short +time=2 +tries=1 @127.0.0.1 "{}" AAAA 2>/dev/null)"
  [ -z "$a" ] && [ -z "$b" ] && echo "{}"
  # a couple of well-known live subdomains per apex
  dig +short +time=2 +tries=1 @127.0.0.1 "www.{}" A >/dev/null 2>&1
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
exit 0

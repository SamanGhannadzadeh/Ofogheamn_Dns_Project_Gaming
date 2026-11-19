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
{
  grep -vE '^\s*(#|$)' "$COD" 2>/dev/null
  if [ -r "$GAMING" ]; then
    total=$(grep -cvE '^\s*(#|$)' "$GAMING" 2>/dev/null || echo 0)
    if [ "${total:-0}" -gt 0 ]; then
      quarter=$(( (10#$(date +%M) / 4) % 4 ))
      grep -vE '^\s*(#|$)' "$GAMING" | awk -v q="$quarter" 'NR % 4 == q'
    fi
  fi
} | sort -u | while read -r d; do
  dig +short +time=2 +tries=1 @127.0.0.1 "$d" A >/dev/null 2>&1
  dig +short +time=2 +tries=1 @127.0.0.1 "$d" AAAA >/dev/null 2>&1
  # a couple of well-known live subdomains per apex
  dig +short +time=2 +tries=1 @127.0.0.1 "www.$d" A >/dev/null 2>&1
done
exit 0

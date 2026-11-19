#!/bin/bash
# "Match-Ready" cache warmer — an Ofogheamn DNS method.
# Every few minutes (cod-warmup.timer) re-resolve every Call of
# Duty / Warzone domain through the local server, so:
#   * the cache entry is always fresh (never a cold lookup when
#     a player launches the game or a match starts), and
#   * SmartDNS re-runs its fastest-IP measurement regularly, so
#     the cached winner tracks changing network conditions.
set -u
LISTS="/etc/ofogheamn-dns/lists/cod.domains /etc/ofogheamn-dns/lists/gaming.domains"
cat $LISTS 2>/dev/null | grep -vE '^\s*(#|$)' | sort -u | while read -r d; do
  dig +short +time=2 +tries=1 @127.0.0.1 "$d" A >/dev/null 2>&1
  dig +short +time=2 +tries=1 @127.0.0.1 "$d" AAAA >/dev/null 2>&1
  # a couple of well-known live subdomains per apex
  dig +short +time=2 +tries=1 @127.0.0.1 "www.$d" A >/dev/null 2>&1
done
exit 0

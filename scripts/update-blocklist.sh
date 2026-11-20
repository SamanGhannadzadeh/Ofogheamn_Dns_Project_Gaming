#!/bin/bash
# Refresh the managed blocklist section of blocklist.conf from a
# hosts-format source (default: StevenBlack unified ads+malware).
# Manual rules outside the markers are preserved. Safe by design:
# a download with too few entries aborts and keeps the old list.
set -u
ETC=/etc/ofogheamn-dns
FILE="$ETC/blocklist.conf"
URL="${OFOGH_BLOCKLIST_URL:-https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts}"
TMP="$(mktemp)"
trap 'rm -f "$TMP" "$TMP.rules"' EXIT

curl -fsSL --max-time 120 -o "$TMP" "$URL" || { echo "download failed"; exit 1; }
awk '$1 == "0.0.0.0" || $1 == "127.0.0.1" {print $2}' "$TMP" \
  | grep -E '^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$' | sort -u > "$TMP.rules"
COUNT="$(wc -l < "$TMP.rules")"
echo "blocklist candidates: $COUNT"
[ "$COUNT" -ge 1000 ] || { echo "too few entries; keeping the old list"; exit 1; }
[ "$COUNT" -le 300000 ] || { echo "list suspiciously large; aborting"; exit 1; }

{
  sed '/^# --- managed blocklist begin/,/^# --- managed blocklist end/d' "$FILE" 2>/dev/null
  echo "# --- managed blocklist begin (update-blocklist.sh; do not edit) ---"
  # The "#" answer form is load-bearing: it is the only form the
  # real SmartDNS (Release48.5) answers locally with NXDOMAIN and
  # zero answers. The empty form (address /domain/) is parsed but
  # never answered locally — it silently turned this whole list
  # into a no-op (v1.4 fix, proven against the real binary).
  sed 's|.*|address /&/#|' "$TMP.rules"
  echo "# --- managed blocklist end ---"
} > "$FILE.new" && mv "$FILE.new" "$FILE"
echo "blocklist updated: $COUNT domains"
systemctl restart ofogheamn-dns 2>/dev/null || true

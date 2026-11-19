#!/bin/bash
# Container entrypoint: seed config on first run, then run
# SmartDNS + sing-box + panel in the foreground (no systemd here).
set -u
ETC=/etc/ofogheamn-dns
SRC=/opt/ofogheamn/config
mkdir -p "$ETC/lists" "$ETC/tls" /var/cache/ofogheamn-dns /var/log/ofogheamn-dns

seed() { [ -e "$ETC/$1" ] || cp "$SRC/$1" "$ETC/$1"; }
seed smartdns.conf; seed hijack.conf; seed blocklist.conf; seed force-dns.conf
seed lists/gaming.domains; seed lists/cod.domains
HOSTNAME_DNS="${OFOGH_DNS_HOSTNAME:-dns.ofogheamn.ir}"
sed -i "s/^bind-cert-san .*/bind-cert-san $HOSTNAME_DNS/" "$ETC/smartdns.conf"

if [ ! -s "$ETC/tls/fullchain.pem" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
    -keyout "$ETC/tls/privkey.pem" -out "$ETC/tls/fullchain.pem" \
    -subj "/CN=$HOSTNAME_DNS" -addext "subjectAltName=DNS:$HOSTNAME_DNS" >/dev/null 2>&1
  chmod 600 "$ETC/tls/privkey.pem"
fi
if [ ! -f "$ETC/panel.conf" ]; then
  PANEL_PASS="${OFOGH_PANEL_PASSWORD:-$(openssl rand -hex 8)}"
  HASH="$(printf %s "$PANEL_PASS" | sha256sum | cut -d' ' -f1)"
  printf 'port=8080\nbind=0.0.0.0\npassword_hash=%s\n' "$HASH" > "$ETC/panel.conf"
  chmod 600 "$ETC/panel.conf"
  echo "*** PANEL PASSWORD: $PANEL_PASS"
fi
[ -f "$ETC/mode.conf" ] || echo "mode=public" > "$ETC/mode.conf"
[ -f "$ETC/allowlist.txt" ] || echo "# one IP or CIDR per line (private mode)" > "$ETC/allowlist.txt"
if [ ! -f "$ETC/proxy-users.json" ]; then
  PROXY_PASS="${OFOGH_PROXY_PASSWORD:-$(openssl rand -hex 8)}"
  printf '[{"user": "ofogh", "pass": "%s"}]\n' "$PROXY_PASS" > "$ETC/proxy-users.json"
  chmod 600 "$ETC/proxy-users.json"
  echo "*** PROXY USER: ofogh  PASSWORD: $PROXY_PASS"
fi
OFOGH_ETC="$ETC" python3 /usr/local/lib/ofogheamn-dns/gen-singbox-config.py || true

/usr/local/bin/smartdns -f -c "$ETC/smartdns.conf" -p /tmp/smartdns.pid &
/usr/local/bin/sing-box run -c "$ETC/singbox.json" &
python3 /usr/local/lib/ofogheamn-dns/panel.py &
# CoD/gaming cache warmer loop (replaces the systemd timer)
( while true; do sleep 240; bash /opt/ofogheamn/scripts/cod-warmup.sh || true; done ) &
wait -n

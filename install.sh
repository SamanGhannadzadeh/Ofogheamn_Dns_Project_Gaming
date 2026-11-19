#!/bin/bash
# ============================================================
#  Ofogheamn DNS Project — Gaming Edition — installer
#  One command on a fresh Debian/Ubuntu server:
#    curl -fsSL https://raw.githubusercontent.com/saman-ghannadzadeh/Ofogheamn_Dns_Project_Gaming/main/install.sh | sudo bash
#  or from a clone:  sudo bash install.sh
#  Env knobs:
#    OFOGH_DNS_HOSTNAME  public name for DoT/DoH cert (default dns.ofogheamn.ir)
#    SMARTDNS_VERSION    pin a SmartDNS release tag (default: latest)
# ============================================================
set -euo pipefail

REPO_URL="https://github.com/saman-ghannadzadeh/Ofogheamn_Dns_Project_Gaming"
HOSTNAME_DNS="${OFOGH_DNS_HOSTNAME:-dns.ofogheamn.ir}"
ETC=/etc/ofogheamn-dns
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo .)"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "run as root (sudo bash install.sh)"
grep -qiE "debian|ubuntu" /etc/os-release || die "Debian/Ubuntu only"
case "$(uname -m)" in
  x86_64) SD_ARCH=x86_64 ;;
  aarch64|arm64) SD_ARCH=aarch64 ;;
  *) die "unsupported arch: $(uname -m)" ;;
esac

say "installing base tools"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates openssl dnsutils iproute2 >/dev/null

# If we were piped in (no repo files next to us), fetch the project.
if [ ! -f "$SRC_DIR/config/smartdns.conf" ]; then
  say "fetching project files"
  TMP="$(mktemp -d)"
  curl -fsSL "$REPO_URL/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP" --strip-components=1
  SRC_DIR="$TMP"
fi

# ---------- SmartDNS binary (newest release) ----------
TAG="${SMARTDNS_VERSION:-}"
if [ -z "$TAG" ]; then
  TAG="$(curl -sIL -o /dev/null -w '%{url_effective}' https://github.com/pymumu/smartdns/releases/latest | sed 's#.*/tag/##')"
  [ -n "$TAG" ] || TAG="Release48.5-RC1"
fi
say "installing SmartDNS $TAG ($SD_ARCH)"
curl -fsSL -o /usr/local/bin/smartdns \
  "https://github.com/pymumu/smartdns/releases/download/$TAG/smartdns-$SD_ARCH"
chmod 755 /usr/local/bin/smartdns
/usr/local/bin/smartdns -v || true

# ---------- user, dirs, config ----------
id ofodns >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin ofodns
mkdir -p "$ETC/lists" "$ETC/tls" /var/cache/ofogheamn-dns /var/log/ofogheamn-dns
cp "$SRC_DIR/config/smartdns.conf" "$ETC/smartdns.conf"
cp "$SRC_DIR/config/hijack.conf" "$ETC/hijack.conf"
cp "$SRC_DIR/config/blocklist.conf" "$ETC/blocklist.conf"
cp "$SRC_DIR/config/force-dns.conf" "$ETC/force-dns.conf"
cp "$SRC_DIR/config/lists/gaming.domains" "$ETC/lists/gaming.domains"
cp "$SRC_DIR/config/lists/cod.domains" "$ETC/lists/cod.domains"
sed -i "s/^bind-cert-san .*/bind-cert-san $HOSTNAME_DNS/" "$ETC/smartdns.conf"
install -m 755 "$SRC_DIR/scripts/ofogheamn-dns" /usr/local/bin/ofogheamn-dns
install -m 755 "$SRC_DIR/scripts/cod-warmup.sh" /usr/local/bin/cod-warmup
install -m 755 "$SRC_DIR/scripts/ofogheamn-firewall.sh" /usr/local/bin/ofogheamn-firewall
install -m 755 "$SRC_DIR/scripts/update-blocklist.sh" /usr/local/bin/update-blocklist
mkdir -p /usr/local/lib/ofogheamn-dns
install -m 644 "$SRC_DIR/panel/panel.py" /usr/local/lib/ofogheamn-dns/panel.py
install -m 755 "$SRC_DIR/scripts/gen-singbox-config.py" /usr/local/lib/ofogheamn-dns/gen-singbox-config.py

# ---------- proxy core (sing-box, newest release) ----------
SB_TAG="$(curl -sIL -o /dev/null -w '%{url_effective}' https://github.com/SagerNet/sing-box/releases/latest | sed 's#.*/tag/##' || true)"
case "$(uname -m)" in x86_64) SB_ARCH=amd64 ;; aarch64|arm64) SB_ARCH=arm64 ;; esac
if [ -n "${SB_TAG:-}" ]; then
  say "installing sing-box $SB_TAG (proxy core)"
  curl -fsSL "https://github.com/SagerNet/sing-box/releases/download/$SB_TAG/sing-box-${SB_TAG#v}-linux-$SB_ARCH.tar.gz" \
    | tar -xz -C /tmp
  install -m 755 "/tmp/sing-box-${SB_TAG#v}-linux-$SB_ARCH/sing-box" /usr/local/bin/sing-box
else
  echo "WARNING: sing-box download failed; proxy will be unavailable until 'ofogheamn-dns update' succeeds"
fi

# ---------- gaming tunnel (WireGuard) ----------
install -m 755 "$SRC_DIR/scripts/ofogheamn-wg-setup.sh" /usr/local/bin/ofogheamn-wg-setup
install -m 755 "$SRC_DIR/scripts/ofogheamn-wg-peer.py" /usr/local/bin/ofogheamn-wg-peer
if ! command -v wg >/dev/null 2>&1; then
  say "installing wireguard-tools"
  apt-get update -qq >/dev/null 2>&1 || true
  apt-get install -y -qq wireguard-tools >/dev/null 2>&1 || echo "WARNING: wireguard-tools install failed; tunnel unavailable until 'apt install wireguard-tools'"
fi
if command -v wg >/dev/null 2>&1 && [ ! -f "$ETC/wg-server.key" ]; then
  wg genkey > "$ETC/wg-server.key"; chmod 600 "$ETC/wg-server.key"
  printf 'port=51820\nendpoint=%s\n' "${OFOGH_WG_ENDPOINT:-$PUBIP}" > "$ETC/wg-server.conf"
  echo "[]" > "$ETC/wg-peers.json"
  OFOGH_ETC="$ETC" python3 -c "
import sys; sys.path.insert(0, '/usr/local/bin')
import importlib.util
spec = importlib.util.spec_from_file_location('peer', '/usr/local/bin/ofogheamn-wg-peer')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.write_conf([])"
fi

# ---------- panel + mode + proxy credentials (first run only) ----------
PANEL_PASS=""
if [ ! -f "$ETC/panel.conf" ]; then
  PANEL_PASS="$(openssl rand -hex 8)"
  HASH="$(printf %s "$PANEL_PASS" | sha256sum | cut -d' ' -f1)"
  printf 'port=8080\nbind=0.0.0.0\npassword_hash=%s\n' "$HASH" > "$ETC/panel.conf"
  chmod 600 "$ETC/panel.conf"
fi
[ -f "$ETC/mode.conf" ] || echo "mode=public" > "$ETC/mode.conf"
[ -f "$ETC/allowlist.txt" ] || printf '# one IP or CIDR per line (private mode)\n' > "$ETC/allowlist.txt"
PROXY_PASS=""
if [ ! -f "$ETC/proxy-users.json" ]; then
  PROXY_PASS="$(openssl rand -hex 8)"
  printf '[{"user": "ofogh", "pass": "%s"}]\n' "$PROXY_PASS" > "$ETC/proxy-users.json"
  chmod 600 "$ETC/proxy-users.json"
fi
OFOGH_ETC="$ETC" python3 /usr/local/lib/ofogheamn-dns/gen-singbox-config.py || true
bash /usr/local/bin/ofogheamn-firewall || true

# ---------- TLS (self-signed until you drop in a real cert) ----------
if [ ! -s "$ETC/tls/fullchain.pem" ]; then
  say "generating self-signed TLS certificate for $HOSTNAME_DNS"
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
    -keyout "$ETC/tls/privkey.pem" -out "$ETC/tls/fullchain.pem" \
    -subj "/CN=$HOSTNAME_DNS" -addext "subjectAltName=DNS:$HOSTNAME_DNS" >/dev/null 2>&1
  chmod 600 "$ETC/tls/privkey.pem"
fi
chown -R ofodns:ofodns /var/cache/ofogheamn-dns /var/log/ofogheamn-dns "$ETC"

# ---------- kernel tuning for high-rate UDP DNS ----------
say "applying network tuning"
cp "$SRC_DIR/systemd/99-ofogheamn-dns.conf" /etc/sysctl.d/99-ofogheamn-dns.conf
sysctl --system >/dev/null || true

# ---------- service ----------
cp "$SRC_DIR/systemd/ofogheamn-dns.service" /etc/systemd/system/ofogheamn-dns.service
cp "$SRC_DIR/systemd/cod-warmup.service" /etc/systemd/system/cod-warmup.service
cp "$SRC_DIR/systemd/cod-warmup.timer" /etc/systemd/system/cod-warmup.timer
cp "$SRC_DIR/systemd/ofogheamn-panel.service" /etc/systemd/system/ofogheamn-panel.service
cp "$SRC_DIR/systemd/ofogheamn-wg.service" /etc/systemd/system/ofogheamn-wg.service
cp "$SRC_DIR/systemd/ofogheamn-blocklist.service" /etc/systemd/system/ofogheamn-blocklist.service
cp "$SRC_DIR/systemd/ofogheamn-blocklist.timer" /etc/systemd/system/ofogheamn-blocklist.timer
cp "$SRC_DIR/systemd/ofogheamn-proxy.service" /etc/systemd/system/ofogheamn-proxy.service
systemctl daemon-reload
systemctl enable ofogheamn-dns >/dev/null 2>&1 || true
systemctl enable --now cod-warmup.timer >/dev/null 2>&1 || true
systemctl enable --now ofogheamn-panel >/dev/null 2>&1 || true
[ -x /usr/local/bin/sing-box ] && systemctl enable --now ofogheamn-proxy >/dev/null 2>&1 || true
[ -f "$ETC/wg0.conf" ] && systemctl enable --now ofogheamn-wg >/dev/null 2>&1 || true
if ! systemctl restart ofogheamn-dns; then
  echo "Service failed to start. If systemd-resolved holds port 53, run:"
  echo "  sed -i 's/^#DNSStubListener=.*/DNSStubListener=no/' /etc/systemd/resolved.conf"
  echo "  systemctl restart systemd-resolved ofogheamn-dns"
  die "see /var/log/ofogheamn-dns/smartdns.log"
fi

# ---------- firewall (only if ufw is already active) ----------
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  say "opening firewall ports in ufw"
  ufw allow 53 >/dev/null; ufw allow 853 >/dev/null; ufw allow 443/udp >/dev/null; ufw allow 443/tcp >/dev/null
  ufw allow 2080 >/dev/null; ufw allow 8080 >/dev/null; ufw allow 51820/udp >/dev/null
fi

sleep 2
say "self-test"
dig +short +time=3 +tries=1 @127.0.0.1 callofduty.com A | head -3 || true
dig +short +time=3 +tries=1 @127.0.0.1 store.steampowered.com A | head -3 || true

PUBIP="$(curl -s --max-time 5 https://ifconfig.me || hostname -I | awk '{print $1}')"
cat <<EOF

============================================================
 Ofogheamn DNS is up.  Server: $PUBIP
   Plain DNS : $PUBIP  (UDP/TCP 53)         <- PS5, Xbox, router
   DoT       : $HOSTNAME_DNS : 853          <- Android Private DNS
   DoH       : https://$HOSTNAME_DNS/dns-query
   DoQ       : $HOSTNAME_DNS : 853 (UDP)
 Proxy    : $PUBIP : 2080 (mixed HTTP/SOCKS5 + UDP, auth required)
 Panel    : http://$PUBIP:8080
 Manage:  ofogheamn-dns            (interactive menu)
          ofogheamn-dns status|mode|proxy|cod-test|...
 Logs:    /var/log/ofogheamn-dns/smartdns.log
 NOTE: the TLS cert is self-signed. For public DoT/DoH, replace
 $ETC/tls/{fullchain,privkey}.pem with a real certificate for
 $HOSTNAME_DNS and restart the service.
============================================================
EOF
[ -n "$PANEL_PASS" ] && echo " *** PANEL PASSWORD (shown once): $PANEL_PASS"
[ -n "$PROXY_PASS" ] && echo " *** PROXY USER: ofogh  PASSWORD (shown once): $PROXY_PASS"
echo " Change them later:  ofogheamn-dns panel-password <new>  /  panel -> Proxy tab"

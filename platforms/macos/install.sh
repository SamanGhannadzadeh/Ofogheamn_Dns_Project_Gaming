#!/bin/bash
# Ofogheamn DNS — macOS server node installer
# Core: AdGuard Home (native macOS build) + sing-box proxy.
# Run:  bash platforms/macos/install.sh   (asks for sudo)
set -euo pipefail

AGH_VER="v0.107.80"
SINGBOX_VER="1.14.4"
ROOT="/opt/ofogheamn"
DATA="/usr/local/etc/ofogheamn"
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ARCH="$(uname -m)"
[ "$ARCH" = "arm64" ] && AGH_ARCH="arm64" || AGH_ARCH="amd64"
[ "$ARCH" = "arm64" ] && SB_ARCH="arm64" || SB_ARCH="amd64"

echo "== Ofogheamn DNS node for macOS ($ARCH) =="
sudo mkdir -p "$ROOT" "$DATA"

# ---------- AdGuard Home ----------
if [ ! -x "$ROOT/AdGuardHome" ]; then
  echo "Downloading AdGuard Home $AGH_VER ..."
  curl -fsSL -o /tmp/agh.zip "https://github.com/AdguardTeam/AdGuardHome/releases/download/$AGH_VER/AdGuardHome_darwin_${AGH_ARCH}.zip"
  unzip -o -q /tmp/agh.zip -d /tmp/agh
  sudo install -m 755 /tmp/agh/AdGuardHome/AdGuardHome "$ROOT/"
fi

# ---------- config (rewrites from the project's hijack.conf) ----------
if [ ! -f "$DATA/AdGuardHome.yaml" ]; then
  python3 - "$REPO_ROOT" "$DATA" <<'PYEOF'
import re, sys
repo, data = sys.argv[1], sys.argv[2]
tpl = open(repo + "/platforms/common/AdGuardHome.template.yaml").read()
rew = []
try:
    for line in open(repo + "/config/hijack.conf"):
        m = re.match(r"\s*address\s+/([^/]+)/(\S+)", line)
        if m:
            rew.append("    - domain: %s\n      answer: %s\n      type: A\n      enabled: true"
                       % (m.group(1), m.group(2)))
except FileNotFoundError:
    pass
tpl = tpl.replace("__REWRITES__", "\n".join(rew) if rew else "    []")
open(data + "/AdGuardHome.yaml", "w").write(tpl)
print("config written")
PYEOF
fi

# ---------- sing-box proxy ----------
if [ ! -x "$ROOT/sing-box" ]; then
  echo "Downloading sing-box $SINGBOX_VER ..."
  curl -fsSL -o /tmp/sb.tar.gz "https://github.com/SagerNet/sing-box/releases/download/v$SINGBOX_VER/sing-box-$SINGBOX_VER-darwin-${SB_ARCH}.tar.gz"
  tar -xzf /tmp/sb.tar.gz -C /tmp
  sudo install -m 755 "/tmp/sing-box-$SINGBOX_VER-darwin-${SB_ARCH}/sing-box" "$ROOT/"
fi
if [ ! -f "$DATA/proxy.json" ]; then
  PROXY_PASS="$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 16)"
  sudo tee "$DATA/proxy.json" >/dev/null <<EOF
{"log": {"level": "warn"},
 "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen": "0.0.0.0",
               "listen_port": 2080,
               "users": [{"username": "ofogh", "password": "$PROXY_PASS"}]}],
 "outbounds": [{"type": "direct", "tag": "direct"}]}
EOF
  echo "Proxy user: ofogh   password: $PROXY_PASS   (saved in $DATA/proxy.json)"
fi

# ---------- services (launchd) ----------
( cd "$ROOT" && sudo ./AdGuardHome -s install -c "$DATA/AdGuardHome.yaml" -w "$DATA" || true )
sudo tee /Library/LaunchDaemons/ir.ofogheamn.proxy.plist >/dev/null <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>ir.ofogheamn.proxy</string>
<key>ProgramArguments</key><array><string>$ROOT/sing-box</string><string>run</string><string>-c</string><string>$DATA/proxy.json</string></array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
</dict></plist>
EOF
sudo launchctl load -w /Library/LaunchDaemons/ir.ofogheamn.proxy.plist 2>/dev/null || true

echo ""
echo "DONE. Ofogheamn DNS node is running on this Mac."
echo " DNS (this Mac's IP): port 53 (UDP/TCP), DoT 853"
echo " AdGuard Home panel:  http://localhost:3000  (first visit: create the admin user)"
echo " Proxy:               <this Mac IP>:2080  user ofogh (password in $DATA/proxy.json)"

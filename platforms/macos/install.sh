#!/bin/bash
# Ofogheamn DNS — macOS server node installer
# Core: AdGuard Home (native macOS build) + sing-box proxy.
# Run:  bash platforms/macos/install.sh   (asks for sudo)
set -euo pipefail

AGH_VER="v0.107.80"
SINGBOX_VER="1.14.4"
ROOT="/opt/ofogheamn"
DATA="/usr/local/etc/ofogheamn"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ARCH="$(uname -m)"
[ "$ARCH" = "arm64" ] && AGH_ARCH="arm64" || AGH_ARCH="amd64"
[ "$ARCH" = "arm64" ] && SB_ARCH="arm64" || SB_ARCH="amd64"

echo "== Ofogheamn DNS node for macOS ($ARCH) =="
sudo mkdir -p "$ROOT" "$DATA"

# ---------- download integrity ----------
# Same policy as the Linux and Windows installers: every binary
# is checked against the SHA-256 digest GitHub records for the
# release asset. API unreachable -> warn and continue; a KNOWN
# mismatch -> abort. This installer skipped verification until
# v1.5 — Linux, Windows and Docker already verified (v1.4).
verify_digest() { # repo tag asset file
  local want got
  want="$(curl -fsSL --max-time 30 "https://api.github.com/repos/$1/releases/tags/$2" 2>/dev/null \
    | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    a = [x for x in d.get("assets", []) if x["name"] == sys.argv[1]]
    print((a[0].get("digest") or "").replace("sha256:", "") if a else "")
except Exception:
    print("")' "$3" 2>/dev/null || true)"
  if [ -z "$want" ]; then
    echo "WARNING: could not fetch the official digest for $3; installing unverified"
    return 0
  fi
  got="$(shasum -a 256 "$4" | awk '{print $1}')"
  if [ "$got" != "$want" ]; then
    echo "SECURITY ABORT: sha256 mismatch for $3 (got $got, want $want)" >&2
    exit 1
  fi
  echo "digest verified: $3"
}

# ---------- AdGuard Home ----------
if [ ! -x "$ROOT/AdGuardHome" ]; then
  echo "Downloading AdGuard Home $AGH_VER ..."
  curl -fsSL -o /tmp/agh.zip "https://github.com/AdguardTeam/AdGuardHome/releases/download/$AGH_VER/AdGuardHome_darwin_${AGH_ARCH}.zip"
  verify_digest "AdguardTeam/AdGuardHome" "$AGH_VER" "AdGuardHome_darwin_${AGH_ARCH}.zip" /tmp/agh.zip
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

# Lite edition: keep the AGH web UI on localhost only (no exposed panel)
if [ "${OFOGH_LITE:-0}" = "1" ] && [ -f "$DATA/AdGuardHome.yaml" ]; then
  sudo sed -i '' 's/0.0.0.0:3000/127.0.0.1:3000/' "$DATA/AdGuardHome.yaml" 2>/dev/null || \
  sed -i 's/0.0.0.0:3000/127.0.0.1:3000/' "$DATA/AdGuardHome.yaml"
  echo "Lite edition: panel bound to localhost only."
fi

# ---------- sing-box proxy ----------
if [ ! -x "$ROOT/sing-box" ]; then
  echo "Downloading sing-box $SINGBOX_VER ..."
  curl -fsSL -o /tmp/sb.tar.gz "https://github.com/SagerNet/sing-box/releases/download/v$SINGBOX_VER/sing-box-$SINGBOX_VER-darwin-${SB_ARCH}.tar.gz"
  verify_digest "SagerNet/sing-box" "v$SINGBOX_VER" "sing-box-$SINGBOX_VER-darwin-${SB_ARCH}.tar.gz" /tmp/sb.tar.gz
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

# ---------- self-verification (v1.4): report, don't assume ----------
echo ""
echo "Self-test:"
FAIL=0
sleep 2
if dig +short +time=3 +tries=1 @127.0.0.1 example.com A 2>/dev/null | grep -q .; then
  echo "  PASS  DNS answers on 127.0.0.1:53"
else
  echo "  FAIL  DNS does not answer on 127.0.0.1:53"; FAIL=1
fi
if nc -z 127.0.0.1 2080 2>/dev/null; then
  echo "  PASS  proxy is listening on 2080"
else
  echo "  FAIL  proxy is NOT listening on 2080"; FAIL=1
fi
if [ "$FAIL" = "0" ]; then echo "SELF-TEST: PASS"; else echo "SELF-TEST: FAIL - installed, but not fully up (see FAIL lines)."; fi

echo ""
if [ "$FAIL" = "0" ]; then echo "DONE. Ofogheamn DNS node is running on this Mac."; else echo "INSTALLED WITH PROBLEMS. Ofogheamn DNS node is not fully up on this Mac."; fi
echo " DNS (this Mac's IP): port 53 (UDP/TCP)"
echo " DoT/DoH: not served by default - enable it in the AdGuard Home panel (Settings -> Encryption) with a certificate."
if [ "${OFOGH_LITE:-0}" = "1" ]; then echo " LITE edition: no exposed panel - AGH UI on localhost:3000 only."; else echo " AdGuard Home panel:  http://localhost:3000  (first visit: create the admin user)"; fi
echo " Proxy:               <this Mac IP>:2080  user ofogh (password in $DATA/proxy.json)"

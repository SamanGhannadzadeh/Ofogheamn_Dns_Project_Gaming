#!/bin/bash
# Static + config regression tests for the Ofogheamn DNS project.
# Runs anywhere (no live server needed):
#   tests/static-test.sh
# Every check here guards a bug that a real first-time user hit
# or would have hit (v1.4 audit). The SmartDNS section downloads
# the real core binary and runs the shipped config against it;
# it SKIPs (does not fail) when the download is impossible.
set -u
cd "$(dirname "$0")/.."
fail=0
chk() { if [ "$2" = "0" ]; then echo "PASS  $1"; else echo "FAIL  $1"; fail=1; fi }
has() { grep -q "$2" "$1" 2>/dev/null; }
hasnot() { ! grep -q "$2" "$1" 2>/dev/null; }

echo "== syntax =="
for f in install.sh uninstall.sh scripts/ofogheamn-dns \
         scripts/ofogheamn-firewall.sh scripts/ofogheamn-wg-setup.sh \
         scripts/ofogheamn-vpn-setup.sh scripts/cod-warmup.sh \
         scripts/update-blocklist.sh gateway/redirect-53.sh \
         gateway/block-doh-ips.sh platforms/macos/install.sh \
         platforms/macos/uninstall.sh platforms/saman-os/install-saman-os.sh \
         docker/entrypoint.sh tests/smoke-test.sh; do
  bash -n "$f" 2>/dev/null; chk "bash -n $f" $?
done
sh -n platforms/openwrt/install-openwrt.sh 2>/dev/null
chk "sh -n platforms/openwrt/install-openwrt.sh" $?
for f in panel/panel.py scripts/gen-singbox-config.py \
         scripts/ofogheamn-wg-peer.py scripts/ofogheamn-mesh.py \
         scripts/ofogheamn-region.py scripts/ofogheamn-bench.py \
         scripts/ofogheamn-health.py docker/verify-download.py; do
  python3 -m py_compile "$f" 2>/dev/null; chk "py_compile $f" $?
done

echo "== regression invariants (v1.4 audit) =="
# install.sh crashed fresh installs with "PUBIP: unbound variable":
# PUBIP must be assigned before the WireGuard block uses it.
A="$(grep -n '^PUBIP=' install.sh | head -1 | cut -d: -f1)"
U="$(grep -n 'OFOGH_WG_ENDPOINT' install.sh | grep -v '^[0-9]*:[[:space:]]*#' | head -1 | cut -d: -f1)"
[ -n "$A" ] && [ -n "$U" ] && [ "$A" -lt "$U" ]
chk "install.sh assigns PUBIP before the wg block uses it" $?
# verify_digest: under set -e + pipefail, a failed digest lookup
# (GitHub API rate-limit 403 is routine) made the want= pipeline
# kill the installer silently instead of reaching the documented
# "warn and continue" path (v1.5 fix; proven by isolation test).
has install.sh 'print("")'"'"' "\$3" 2>/dev/null || true'
chk "linux verify_digest tolerates API failure" $?
has platforms/macos/install.sh 'print("")'"'"' "\$3" 2>/dev/null || true'
chk "macos verify_digest tolerates API failure" $?
has scripts/ofogheamn-dns 'print("")'"'"' "\$3" 2>/dev/null || true'
chk "CLI verify_digest tolerates API failure" $?
# The public-mode hashlimit rule was inverted (dropped the
# well-behaved, passed the floods): hashlimit lines must RETURN,
# never DROP.
hasnot scripts/ofogheamn-firewall.sh 'hashlimit.*-j DROP'
chk "firewall: no hashlimit line targets DROP" $?
has scripts/ofogheamn-firewall.sh 'hashlimit.*-j RETURN'
chk "firewall: hashlimit under-limit path RETURNs" $?
# smartdns.conf includes mesh-upstream.conf; a missing include is
# fatal at startup. Every installer path must provide the file.
has docker/entrypoint.sh 'seed mesh-upstream.conf'
chk "docker entrypoint seeds mesh-upstream.conf" $?
has platforms/openwrt/install-openwrt.sh 'mesh-upstream.conf'
chk "openwrt installer downloads mesh-upstream.conf" $?
has install.sh 'config/mesh-upstream.conf'
chk "linux installer installs mesh-upstream.conf" $?
# Missing TLS cert files are equally fatal (no auto-generation).
has platforms/openwrt/install-openwrt.sh 'fullchain.pem'
chk "openwrt installer generates the TLS cert" $?
# The blocklist generator must emit the "#" answer form — the
# empty form is parsed by SmartDNS but never answered locally.
has scripts/update-blocklist.sh 'address /&/#'
chk "update-blocklist emits address /domain/# rules" $?
# macOS REPO_ROOT resolved one level too high (the Windows v1.3.1
# bug, twin copy).
has platforms/macos/install.sh 'dirname "$0")/../\.\.'
chk "macos install.sh REPO_ROOT goes up two levels" $?
hasnot platforms/macos/install.sh 'dirname "$0")/../../\.\.'
chk "macos install.sh REPO_ROOT does not go up three levels" $?
# Panel must regenerate sing-box config via the shared generator
# (hand-writing it dropped the REALITY inbound).
has panel/panel.py 'gen-singbox-config.py'
chk "panel regenerates sing-box config via the generator" $?
# CLI update hardcoded the amd64 sing-box asset (broke ARM nodes).
hasnot scripts/ofogheamn-dns 'linux-amd64\.tar\.gz'
chk "CLI update has no hardcoded linux-amd64 tarball" $?
hasnot scripts/ofogheamn-dns 'linux-amd64/sing-box'
chk "CLI update has no hardcoded linux-amd64 install path" $?
# Uninstaller must remove what the installer installed, by the
# names it installed them under.
has uninstall.sh '/usr/local/bin/update-blocklist'
chk "uninstall removes update-blocklist" $?
has uninstall.sh '/usr/local/bin/ofogheamn-wg-peer '
chk "uninstall removes ofogheamn-wg-peer (installed name)" $?
hasnot uninstall.sh '/usr/local/bin/ofogheamn-wg-peer.py'
chk "uninstall does not use the wrong .py name" $?

echo "== windows installer (structural; no pwsh here) =="
W=platforms/windows/install.ps1
has "$W" 'SecurityProtocolType]::Tls12'
chk "windows install pins TLS 1.2 for downloads" $?
has "$W" 'Write-NoBom "\$Data\\AdGuardHome.yaml"'
chk "windows install writes AdGuardHome.yaml BOM-free" $?
has "$W" 'Write-NoBom "\$Data\\proxy.json"'
chk "windows install writes proxy.json BOM-free" $?
hasnot "$W" '^ *Set-Content.*-Encoding UTF8'
chk "windows install has no BOM-writing Set-Content left" $?
has "$W" 'Test-Digest "AdguardTeam/AdGuardHome"'
chk "windows install verifies the AdGuard Home digest" $?
has "$W" 'Test-Digest "SagerNet/sing-box"'
chk "windows install verifies the sing-box digest" $?
has "$W" 'PSScriptRoot\\.\.\\\.\.'
chk "windows install RepoRoot goes up two levels" $?
hasnot "$W" 'PSScriptRoot\\.\.\\\.\.\\\.\.'
chk "windows install RepoRoot does not go up three levels" $?

echo "== macos installer (structural) =="
# The macOS installer downloaded both binaries with no digest
# check until v1.5; the project policy (Linux/Windows/Docker)
# is that every fetched binary is verified.
has platforms/macos/install.sh 'verify_digest "AdguardTeam/AdGuardHome"'
chk "macos install verifies the AdGuard Home digest" $?
has platforms/macos/install.sh 'verify_digest "SagerNet/sing-box"'
chk "macos install verifies the sing-box digest" $?

echo "== smartdns: real binary vs shipped config =="
SD_DIR="$(mktemp -d)"
SD_BIN="$SD_DIR/smartdns"
if curl -fsSL --max-time 90 -o "$SD_BIN" \
     "https://github.com/pymumu/smartdns/releases/download/Release48.5-RC1/smartdns-x86_64" 2>/dev/null \
   && chmod +x "$SD_BIN" && "$SD_BIN" -v >/dev/null 2>&1; then
  T="$SD_DIR/t"; mkdir -p "$T/etc/lists" "$T/cache" "$T/log" "$T/etc/tls"
  sed -e "s#/etc/ofogheamn-dns#$T/etc#g" \
      -e "s#/var/cache/ofogheamn-dns#$T/cache#g" \
      -e "s#/var/log/ofogheamn-dns#$T/log#g" \
      -e 's#^bind \[::\]:53#bind 127.0.0.1:15353#' \
      -e 's#^bind-tcp \[::\]:53#bind-tcp 127.0.0.1:15353#' \
      -e 's#^bind-tls \[::\]:853#bind-tls 127.0.0.1:15853#' \
      -e 's#^bind-https \[::\]:443#bind-https 127.0.0.1:15443#' \
      config/smartdns.conf > "$T/smartdns.conf"
  for f in hijack.conf blocklist.conf force-dns.conf mesh-upstream.conf; do
    cp "config/$f" "$T/etc/"
  done
  cp config/lists/*.domains "$T/etc/lists/"
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
    -keyout "$T/etc/tls/privkey.pem" -out "$T/etc/tls/fullchain.pem" \
    -subj "/CN=dns.ofogheamn.ir" >/dev/null 2>&1
  "$SD_BIN" -f -c "$T/smartdns.conf" -p "$T/pid" >"$T/run.log" 2>&1 &
  PID=$!; sleep 3
  kill -0 "$PID" 2>/dev/null; chk "shipped smartdns.conf starts and stays up" $?
  kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null
  # The invariant behind three installer bugs: remove the mesh
  # include and the core must refuse to start.
  mv "$T/etc/mesh-upstream.conf" "$T/mesh.bak"
  "$SD_BIN" -f -c "$T/smartdns.conf" -p "$T/pid" >"$T/run2.log" 2>&1 &
  PID=$!; sleep 2
  kill -0 "$PID" 2>/dev/null; [ "$?" != "0" ]; chk "missing mesh-upstream.conf is fatal (documents the invariant)" $?
  kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null
  mv "$T/mesh.bak" "$T/etc/mesh-upstream.conf"
  # Answer forms against a dead upstream (127.0.0.1:9 = discard):
  # "#" must answer locally (NXDOMAIN), the empty form must not.
  M="$SD_DIR/m"; mkdir -p "$M"
  cat > "$M/c.conf" <<EOF
bind-tcp 127.0.0.1:15354
cache-size 1024
server 127.0.0.1:9
address /hash.example/#
address /empty.example/
EOF
  "$SD_BIN" -f -c "$M/c.conf" -p "$M/pid" >"$M/run.log" 2>&1 &
  PID=$!; sleep 2
  H="$(dig +tcp +time=3 +tries=1 @127.0.0.1 -p 15354 hash.example A 2>/dev/null | awk '/status:/{print $6}' | tr -d ,)"
  E="$(dig +tcp +time=3 +tries=1 @127.0.0.1 -p 15354 empty.example A 2>/dev/null | awk '/status:/{print $6}' | tr -d ,)"
  kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null
  [ "$H" = "NXDOMAIN" ]; chk "address /domain/# answers NXDOMAIN locally" $?
  [ "$E" != "NXDOMAIN" ]; chk "address /domain/ (empty) does NOT answer locally" $?
else
  echo "SKIP  smartdns binary unavailable (offline?) — config tests skipped"
fi
rm -rf "$SD_DIR"
exit $fail

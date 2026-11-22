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
         scripts/apply-node-profile.sh \
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
# Console proxy (v1.6): generator, firewall and CLI must agree —
# a no-auth inbound without its firewall guard is a hole.
has scripts/gen-singbox-config.py 'console.json'
chk "generator reads console.json for the console proxy" $?
has scripts/gen-singbox-config.py 'ofogh-console'
chk "generator emits the ofogh-console inbound" $?
has scripts/ofogheamn-firewall.sh 'CPORT'
chk "firewall guards the console port" $?
has scripts/ofogheamn-dns 'console)'
chk "CLI exposes the console command" $?
has scripts/ofogheamn-health.py 'upstream-dead'
chk "health reports dead upstreams by name" $?
# Functional: the generator really emits the console inbound
# only while console.json exists — end to end, not just strings.
GT=$(mktemp -d)
printf '[{"user":"t","pass":"t"}]' > "$GT/proxy-users.json"
OFOGH_ETC="$GT" python3 scripts/gen-singbox-config.py >/dev/null 2>&1
cp "$GT/singbox.json" "$GT/off.json" 2>/dev/null
echo '{"port": 2081}' > "$GT/console.json"
OFOGH_ETC="$GT" python3 scripts/gen-singbox-config.py >/dev/null 2>&1
cp "$GT/singbox.json" "$GT/on.json" 2>/dev/null
python3 - "$GT" <<'EOF'
import json, sys
gt = sys.argv[1]
off = [i.get("tag") for i in json.load(open(gt + "/off.json"))["inbounds"]]
on = [i.get("tag") for i in json.load(open(gt + "/on.json"))["inbounds"]]
assert "ofogh-console" not in off, "console inbound without console.json"
assert "ofogh-console" in on, "console inbound missing with console.json"
ctype = [i.get("type") for i in json.load(open(gt + "/on.json"))["inbounds"] if i.get("tag") == "ofogh-console"][0]
assert ctype == "http", "console inbound must be HTTP only (the one proxy protocol a PS5 speaks)"
EOF
chk "generator emits console inbound only with console.json" $?
# Hysteria2 (v1.7): generator, firewall and CLI must agree, and
# the generator must emit the inbound with the file's port and
# password — the ladder's rung 2 is a real feature, not a doc.
has scripts/gen-singbox-config.py 'hysteria2.json'
chk "generator reads hysteria2.json" $?
has scripts/gen-singbox-config.py 'ofogh-hysteria2'
chk "generator emits the ofogh-hysteria2 inbound" $?
has scripts/ofogheamn-dns 'hysteria2)'
chk "CLI exposes the hysteria2 command" $?
has scripts/ofogheamn-firewall.sh 'HY2'
chk "firewall guards the hysteria2 port" $?
echo '{"port": 443, "password": "testpass"}' > "$GT/hysteria2.json"
OFOGH_ETC="$GT" python3 scripts/gen-singbox-config.py >/dev/null 2>&1
python3 - "$GT" <<'EOF'
import json, sys
gt = sys.argv[1]
inb = {i.get("tag"): i for i in json.load(open(gt + "/singbox.json"))["inbounds"]}
assert "ofogh-hysteria2" in inb, "hysteria2 inbound missing with hysteria2.json"
assert inb["ofogh-hysteria2"]["listen_port"] == 443
assert inb["ofogh-hysteria2"]["users"][0]["password"] == "testpass"
EOF
chk "generator emits hysteria2 inbound with hysteria2.json" $?
# TUIC v5 + AnyTLS + Hysteria2 Gecko (v1.8): same opt-in pattern.
has scripts/gen-singbox-config.py 'tuic.json'
chk "generator reads tuic.json" $?
has scripts/gen-singbox-config.py 'ofogh-tuic'
chk "generator emits the ofogh-tuic inbound" $?
has scripts/gen-singbox-config.py 'anytls.json'
chk "generator reads anytls.json" $?
has scripts/gen-singbox-config.py 'ofogh-anytls'
chk "generator emits the ofogh-anytls inbound" $?
has scripts/ofogheamn-dns 'tuic)'
chk "CLI exposes the tuic command" $?
has scripts/ofogheamn-dns 'anytls)'
chk "CLI exposes the anytls command" $?
has scripts/ofogheamn-firewall.sh 'hop_range'
chk "firewall implements hysteria2 port hopping" $?
echo '{"port": 8443, "uuid": "11111111-2222-3333-4444-555555555555", "password": "tuicpass"}' > "$GT/tuic.json"
echo '{"port": 8443, "password": "anypass"}' > "$GT/anytls.json"
echo '{"port": 443, "password": "testpass", "obfs": "gecko", "obfs_password": "obfspass"}' > "$GT/hysteria2.json"
OFOGH_ETC="$GT" python3 scripts/gen-singbox-config.py >/dev/null 2>&1
python3 - "$GT" <<'EOF'
import json, sys
gt = sys.argv[1]
inb = {i.get("tag"): i for i in json.load(open(gt + "/singbox.json"))["inbounds"]}
assert inb["ofogh-tuic"]["congestion_control"] == "bbr", "tuic must use bbr"
assert inb["ofogh-tuic"]["users"][0]["password"] == "tuicpass"
assert inb["ofogh-anytls"]["users"][0]["password"] == "anypass"
assert inb["ofogh-hysteria2"]["obfs"]["type"] == "gecko", "gecko obfs not emitted"
EOF
chk "generator emits tuic, anytls and gecko obfs from their files" $?
rm -rf "$GT"

echo "== awgify functional (v1.11) =="
AT="$(mktemp -d)"
cat > "$AT/wg.conf" <<'EOF'
[Interface]
PrivateKey = AAAA
Address = 10.66.0.1/24
ListenPort = 51820

[Peer]
PublicKey = BBBB
AllowedIPs = 0.0.0.0/0
EOF
python3 platforms/amneziawg/awgify.py "$AT/wg.conf" --write-params "$AT/p.json" > "$AT/awg.conf" 2>/dev/null
grep -q "^Jc = " "$AT/awg.conf"; chk "awgify adds junk parameters" $?
grep -q "^H4 = " "$AT/awg.conf"; chk "awgify adds magic header ranges" $?
grep -q "PrivateKey = AAAA" "$AT/awg.conf"; chk "awgify preserves the interface keys" $?
python3 platforms/amneziawg/awgify.py "$AT/wg.conf" --params "$AT/p.json" > "$AT/awg2.conf" 2>/dev/null
cmp -s "$AT/awg.conf" "$AT/awg2.conf"; chk "awgify reuses shared params identically (both ends match)" $?
rm -rf "$AT"

echo "== generator port-collision guard (v1.12) =="
CT="$(mktemp -d)"
printf '[{"user":"t","pass":"t"}]' > "$CT/proxy-users.json"
echo '{"port": 443, "password": "x"}' > "$CT/hysteria2.json"
echo '{"port": 8443, "uuid": "11111111-2222-3333-4444-555555555555", "password": "y"}' > "$CT/tuic.json"
echo '{"port": 8443, "password": "z"}' > "$CT/anytls.json"
OFOGH_ETC="$CT" python3 scripts/gen-singbox-config.py >/dev/null 2>&1
chk "same port on different transports (tuic udp + anytls tcp) is allowed" $?
echo '{"port": 443, "uuid": "11111111-2222-3333-4444-555555555555", "password": "y"}' > "$CT/tuic.json"
OFOGH_ETC="$CT" python3 scripts/gen-singbox-config.py >/dev/null 2>"$CT/err"
[ $? -ne 0 ]; chk "same transport+port (tuic udp 443 vs hy2 udp 443) is refused" $?
grep -q "port collision" "$CT/err"; chk "the refusal names the collision" $?
rm -rf "$CT"

echo "== panel functional (v1.13) =="
PT="$(mktemp -d)"
cat > "$PT/hijack.conf" <<'EOF'
# comment
address /pair.example/203.0.113.10
address /pair.example/::
cname /alias.example/target.example.com
nameserver /routed.example/gaming
address /sink.example/-
EOF
printf '{"port": 2081}' > "$PT/console.json"
printf 'server 127.0.0.1:5335 -group recursive\n' > "$PT/recursive.conf"
OFOGH_ETC="$PT" PT="$PT" python3 - <<'EOF'
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("panel", "panel/panel.py")
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)
rules = {r["domain"]: r for r in panel.hijack_list()}
assert len(rules) == 3, rules
pair = rules["pair.example"]
assert pair["target"] == "203.0.113.10" and pair["v6_blocked"], pair
assert rules["alias.example"]["type"] == "cname"
assert rules["sink.example"]["target"] == "-"
panel.hijack_save(panel.hijack_list())
text = open(os.path.join(os.environ["PT"], "hijack.conf")).read()
assert "address /pair.example/203.0.113.10" in text, text
assert "address /pair.example/::" in text, text
assert "nameserver /routed.example/gaming" in text, text
t = panel.transports_get()
assert t["console"]["on"] and t["console"]["port"] == 2081, t
assert t["recursive"]["on"] and not t["tuic"]["on"], t
print("panel functional OK")
EOF
chk "panel pairs dual-stack hijack rules and reads transport state" $?
has panel/panel.py '/api/feature'
chk "panel exposes the feature toggle route" $?
has panel/panel.py '/api/vpn-creds'
chk "panel exposes VPN credential control" $?
has panel/panel.py '/api/password'
chk "panel exposes admin password change" $?
rm -rf "$PT"
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
  for f in hijack.conf blocklist.conf force-dns.conf mesh-upstream.conf recursive.conf doh-resolvers.conf; do
    cp "config/$f" "$T/etc/"
  done
  cp config/lists/*.domains "$T/etc/lists/"
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
    -keyout "$T/etc/tls/privkey.pem" -out "$T/etc/tls/fullchain.pem" \
    -subj "/CN=dns.ofogheamn.ir" >/dev/null 2>&1
  "$SD_BIN" -f -c "$T/smartdns.conf" -p "$T/pid" >"$T/run.log" 2>&1 &
  PID=$!; sleep 3
  kill -0 "$PID" 2>/dev/null; chk "shipped smartdns.conf starts and stays up" $?
  DG="$(dig +tcp +time=3 +tries=1 @127.0.0.1 -p 15353 dns.google A 2>/dev/null | awk '/status:/{print $6}' | tr -d ,)"
  [ "$DG" != "NXDOMAIN" ]; chk "public DoH name (dns.google) is NOT sinkholed by the shipped config (all domains pass)" $?
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
address /hij.example/203.0.113.10
address /hij.example/::
EOF
  "$SD_BIN" -f -c "$M/c.conf" -p "$M/pid" >"$M/run.log" 2>&1 &
  PID=$!; sleep 2
  H="$(dig +tcp +time=3 +tries=1 @127.0.0.1 -p 15354 hash.example A 2>/dev/null | awk '/status:/{print $6}' | tr -d ,)"
  E="$(dig +tcp +time=3 +tries=1 @127.0.0.1 -p 15354 empty.example A 2>/dev/null | awk '/status:/{print $6}' | tr -d ,)"
  HA="$(dig +tcp +time=3 +tries=1 @127.0.0.1 -p 15354 hij.example A 2>/dev/null | awk '/^hij\.example\./{print $5}')"
  HV="$(dig +tcp +time=3 +tries=1 @127.0.0.1 -p 15354 hij.example AAAA 2>/dev/null | awk '/^hij\.example\./{print $5}')"
  kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null
  [ "$H" = "NXDOMAIN" ]; chk "address /domain/# answers NXDOMAIN locally" $?
  [ "$E" != "NXDOMAIN" ]; chk "address /domain/ (empty) does NOT answer locally" $?
  [ "$HA" = "203.0.113.10" ]; chk "hijack A answered locally with the relay IPv4" $?
  [ "$HV" = "::" ]; chk "hijack AAAA answered locally (::) - no upstream leak" $?
  has scripts/ofogheamn-dns 'hijack_set'
  chk "CLI writes hijack rules through the dual-stack helper" $?
  # Recursive back-end (v1.10): the include must exist in the
  # shipped config, the installer must ship every piece, and
  # the CLI must expose the toggle — a missing conf-file is
  # fatal to SmartDNS, so this chain is load-bearing.
  has config/smartdns.conf 'conf-file /etc/ofogheamn-dns/recursive.conf'
  chk "smartdns.conf includes recursive.conf" $?
  has install.sh 'config/recursive.conf'
  chk "installer ships recursive.conf" $?
  has install.sh 'config/unbound.conf'
  chk "installer ships unbound.conf" $?
  has scripts/ofogheamn-dns 'recursive)'
  chk "CLI exposes the recursive command" $?
else
  echo "SKIP  smartdns binary unavailable (offline?) — config tests skipped"
fi
# Standing guarantee (owner decision, 2026-11-21): the shipped
# template must not ACTIVELY load the DoH-resolver sinkhole —
# every domain passes and resolves by default.
grep -q '^conf-file /etc/ofogheamn-dns/doh-resolvers.conf' config/smartdns.conf
[ $? -ne 0 ]; chk "template does NOT sinkhole DoH resolvers (all domains pass)" $?
has scripts/apply-node-profile.sh 'ofogh-warm-all'
chk "node profile warms the full gaming sets" $?
has scripts/apply-node-profile.sh 'ofogh-gecko-client.json'
chk "node profile emits client configs" $?
has scripts/gen-singbox-config.py '"udp_timeout": "10m"'
chk "server config overrides sniffed UDP session timeouts" $?
has scripts/gen-singbox-config.py 'ofogheamn:operator'
chk "REALITY emits an operator client with an empty user store" $?
has scripts/ofogheamn-firewall.sh 'hysteria2-gecko.json'
chk "firewall guards the Gecko port like other transports" $?
has scripts/ofogheamn-firewall.sh 'reality.json tcp REALITY'
chk "firewall guards the REALITY port like other transports" $?
has scripts/apply-node-profile.sh 'ofogh-client.json'
chk "node profile emits the self-healing auto client" $?
has scripts/apply-node-profile.sh 'urltest'
chk "auto client uses an urltest fallback group" $?
has scripts/apply-node-profile.sh 'ofogh-gateway.json'
chk "node profile emits the console gateway config" $?
has scripts/apply-node-profile.sh 'hijack-dns'
chk "gateway config hijacks LAN DNS to the node resolver" $?
has scripts/apply-node-profile.sh 'ofogheamn-dns tuic enable'
chk "node profile enables TUIC as a QUIC rung" $?
has scripts/apply-node-profile.sh 'proxy-tuic'
chk "auto client group includes TUIC" $?
has scripts/apply-node-profile.sh 'udp_relay_mode'
chk "TUIC client uses native UDP relay" $?
has scripts/apply-node-profile.sh 'ofogheamn-dns anytls enable'
chk "node profile enables AnyTLS as the fifth rung" $?
has scripts/apply-node-profile.sh 'proxy-anytls'
chk "auto client group includes AnyTLS" $?
has scripts/apply-node-profile.sh 'heartbeat'
chk "TUIC client carries a keepalive heartbeat" $?
has README.md 'apply-node-profile'
chk "README documents the node profile and ladder" $?
has scripts/gen-singbox-config.py 'ofogh-https-proxy'
chk "generator emits the TLS-wrapped HTTP proxy inbound" $?
has scripts/ofogheamn-dns 'https-proxy'
chk "CLI manages the HTTPS proxy" $?
has scripts/apply-node-profile.sh 'ofogh-https-client.json'
chk "profile emits the HTTPS proxy client" $?
has panel/panel.py 'hysteria2-gecko'
chk "panel controls the Gecko rung" $?
has panel/panel.py 'https-proxy'
chk "panel controls the HTTPS proxy" $?
has scripts/ofogh-learn-domains.sh 'ipset test'
chk "domain learner verifies candidates against the game ranges" $?
has config/smartdns.conf 'domain-set -name learned'
chk "template routes the learned set with gaming treatment" $?
has panel/panel.py '/api/client-file'
chk "panel serves client config downloads" $?
has scripts/ofogheamn-qos.sh 'for proto in udp tcp'
chk "QoS marks game ranges on both protocols, all ports" $?
has scripts/ofogheamn-qos.sh '3478'
chk "QoS covers the well-known console game ports" $?
has install.sh 'ofogh-ddns-allowlist'
chk "installer installs the DDNS allowlist keeper" $?
has scripts/ofogheamn-dns 'ddns)'
chk "CLI exposes the ddns command" $?
has systemd/ofogh-ddns.timer 'OnUnitActiveSec=5min'
chk "DDNS keeper runs every 5 minutes" $?
has scripts/apply-node-profile.sh 'OFOGH_DDNS_HOST'
chk "node profile can seed the DDNS hostname" $?
# Functional: the keeper adds the resolved IP, keeps manual
# allowlist lines, and swaps the DDNS IP when the hostname moves.
DT=$(mktemp -d); mkdir -p "$DT/bin" "$DT/etc"
printf '#!/bin/sh\necho 203.0.113.7\n' > "$DT/bin/dig"; chmod +x "$DT/bin/dig"
echo "myhome.example.com" > "$DT/etc/ddns.conf"
echo "198.51.100.9" > "$DT/etc/allowlist.txt"
PATH="$DT/bin:$PATH" OFOGH_ETC="$DT/etc" bash scripts/ofogh-ddns-allowlist.sh
grep -qx "203.0.113.7" "$DT/etc/allowlist.txt" && grep -qx "198.51.100.9" "$DT/etc/allowlist.txt"
chk "ddns keeper adds the resolved IP and keeps manual entries" $?
printf '#!/bin/sh\necho 203.0.113.8\n' > "$DT/bin/dig"
PATH="$DT/bin:$PATH" OFOGH_ETC="$DT/etc" bash scripts/ofogh-ddns-allowlist.sh
grep -qx "203.0.113.8" "$DT/etc/allowlist.txt" && ! grep -qx "203.0.113.7" "$DT/etc/allowlist.txt" && grep -qx "198.51.100.9" "$DT/etc/allowlist.txt"
chk "ddns keeper swaps the old DDNS IP for the new one" $?
has config/smartdns.conf 'domain-set:cod/ -speed-check-mode tcp:443 -response-mode fastest-response'
chk "cod set answers fastest-response for session setup" $?
rm -rf "$SD_DIR"
exit $fail

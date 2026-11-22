#!/bin/bash
# Ofogheamn node profile "iran-baku" — the owner's production
# gaming profile: a node in Azerbaijan (Baku) serving players on
# Iranian ISPs, where the measured line latency to Baku is
# ~40-65 ms (vs ~110+ to Western Europe) and the Iran-side path
# adds evening congestion and DPI pressure on the proxy leg.
#
# Run AFTER install.sh, as root, from the repo tree:
#   OFOGH_ADMIN_IP=<your public IP> \
#   OFOGH_CLIENT_SUBNET=<players' /24, e.g. 203.0.113.0/24> \
#   bash scripts/apply-node-profile.sh
#
# What it applies (every step idempotent; all of it was verified
# live on the 2026-11-21 nodes):
#   1. SmartDNS: an ECS "edge" upstream group (the players' /24 is
#      sent to upstreams for the CoD + PSN sets, so CDN/edge
#      selection sees the player, not the node), TTL floors on the
#      gaming sets, fastest-IP stays per-set (never global).
#   2. Proxy product scope: Hysteria2 with masquerade + BBR
#      conservative, port hopping on, a parallel Gecko-obfs
#      listener (udp/2083), and an EMPTY proxy user list — the
#      SOCKS5 ports authenticate by source IP (allowlist), which
#      is the product's console-friendly design.
#   3. Kernel: conntrack UDP timeouts raised for long game
#      sessions, 16 MB socket buffers, TCP Fast Open both ways.
#   4. QoS: datacenter-range refresh + DSCP EF marking for game
#      traffic (ofogheamn-qos).
#   5. Cache warmup for the WHOLE gaming sets (gaming + CoD +
#      PSN lists, A + AAAA) every 4 minutes, so every gaming
#      lookup is a cache hit (the installer's cod-warmup also
#      runs; serve-expired covers the gaps).
#   6. Tunnels OFF (final product scope is DNS + proxy only) and
#      the firewall in private mode: only the admin IP and the
#      server's own IP may reach the service ports.
#   7. The host resolver points at the node itself, last.
#   8. Ready-to-import client configs are written to /root/ —
#      single-transport files plus the combined /root/
#      ofogh-client.json whose urltest group (Gecko, Hysteria2,
#      TUIC, REALITY, AnyTLS) heals the route by itself when UDP
#      is throttled or blocked. REALITY and AnyTLS are the TCP
#      fallback rungs; the QUIC transports are the
#      better-than-SOCKS5 WAN legs for game traffic,
#      while SOCKS5 stays as the LAN-side entry point only. All clients: BBR (no fixed rates), narrow randomized
#      port hopping on Hysteria2, dual-stack TUN, and a 10-minute
#      UDP session lifetime so game sessions are never reaped
#      at the 10 s/30 s sniffed-protocol defaults.
set -eu
ETC=/etc/ofogheamn-dns
ADMIN_IP="${OFOGH_ADMIN_IP:?set OFOGH_ADMIN_IP=<your public IP>}"
CLIENT_SUBNET="${OFOGH_CLIENT_SUBNET:?set OFOGH_CLIENT_SUBNET=<players /24>}"
SERVER_IP="${OFOGH_SERVER_IP:-$(hostname -I | awk '{print $1}')}"
HOP_RANGE="${OFOGH_HOP_RANGE:-20000-40000}"
CONF="$ETC/smartdns.conf"

echo "== node profile iran-baku: admin=$ADMIN_IP subnet=$CLIENT_SUBNET server=$SERVER_IP"

# --- 1. SmartDNS edge group + floors -------------------------------------
sed -i 's#^nameserver /domain-set:cod/gaming#nameserver /domain-set:cod/edge#' "$CONF"
sed -i 's#^nameserver /domain-set:learned/gaming#nameserver /domain-set:learned/edge#' "$CONF"
grep -q 'domain-set -name learned' "$CONF" || \
  echo "domain-set -name learned -file $ETC/lists/learned.domains" >> "$CONF"
grep -q 'domain-rules /domain-set:learned/' "$CONF" || \
  echo "domain-rules /domain-set:learned/ -speed-check-mode tcp:443 -response-mode fastest-response" >> "$CONF"
grep -q 'nameserver /domain-set:learned/edge' "$CONF" || \
  echo "nameserver /domain-set:learned/edge" >> "$CONF"
touch "$ETC/lists/learned.domains"
grep -q 'domain-set -name psn' "$CONF" || \
  echo "domain-set -name psn -file $ETC/lists/psn.domains" >> "$CONF"
grep -q 'domain-rules /domain-set:psn/' "$CONF" || \
  echo "domain-rules /domain-set:psn/ -speed-check-mode tcp:443 -response-mode fastest-response -rr-ttl-min 120" >> "$CONF"
grep -q 'nameserver /domain-set:psn/edge' "$CONF" || \
  echo "nameserver /domain-set:psn/edge" >> "$CONF"
grep 'domain-rules /domain-set:gaming/' "$CONF" | grep -q 'rr-ttl-min' || \
  sed -i 's#^domain-rules /domain-set:gaming/.*#& -rr-ttl-min 60#' "$CONF"
grep 'domain-rules /domain-set:cod/' "$CONF" | grep -q 'rr-ttl-min' || \
  sed -i 's#^domain-rules /domain-set:cod/.*#& -rr-ttl-min 120#' "$CONF"
if ! grep -q 'node-profile:edge:v1' "$CONF"; then
  {
    echo "# node-profile:edge:v1 (iran-baku) — ECS edge group"
    for s in 1.1.1.1 1.0.0.1 8.8.8.8 8.8.4.4 9.9.9.9 9.9.9.11; do
      echo "server-tls $s -group edge -exclude-default-group -subnet $CLIENT_SUBNET -subnet-all-query-types"
    done
    echo "server 1.1.1.1 -group edge -exclude-default-group -subnet $CLIENT_SUBNET -subnet-all-query-types"
    echo "server-https https://cloudflare-dns.com/dns-query -group edge -exclude-default-group -subnet $CLIENT_SUBNET -subnet-all-query-types"
    echo "server-quic 1.1.1.1 -group edge -exclude-default-group -subnet $CLIENT_SUBNET -subnet-all-query-types"
    echo "server-h3 h3://1.1.1.1/dns-query -group edge -exclude-default-group -subnet $CLIENT_SUBNET -subnet-all-query-types"
  } >> "$CONF"
fi

# --- 2. Proxy features ----------------------------------------------------
[ -f "$ETC/hysteria2.json" ] || ofogheamn-dns hysteria2 enable 443
ofogheamn-dns hysteria2 hop "$HOP_RANGE" >/dev/null 2>&1 || true
python3 - <<'PY'
import json
p = "/etc/ofogheamn-dns/hysteria2.json"
cfg = json.load(open(p))
cfg["masquerade_url"] = "https://www.microsoft.com"
cfg["bbr_profile"] = "conservative"
json.dump(cfg, open(p, "w"), indent=2)
# Product scope: no-password SOCKS5, authenticated by allowlist.
json.dump([], open("/etc/ofogheamn-dns/proxy-users.json", "w"))
print("hysteria2: masquerade + bbr conservative set; proxy users emptied")
PY
[ -f "$ETC/hysteria2-gecko.json" ] || ofogheamn-dns hysteria2-gecko enable 2083 >/dev/null 2>&1 || true
[ -f "$ETC/reality.json" ] || ofogheamn-dns reality enable >/dev/null 2>&1 || true
[ -f "$ETC/tuic.json" ] || ofogheamn-dns tuic enable >/dev/null 2>&1 || true
[ -f "$ETC/anytls.json" ] || ofogheamn-dns anytls enable >/dev/null 2>&1 || true
[ -f "$ETC/https-proxy.json" ] || ofogheamn-dns https-proxy enable >/dev/null 2>&1 || true
python3 /usr/local/lib/ofogheamn-dns/gen-singbox-config.py
sing-box check -c /etc/ofogheamn-dns/singbox.json

# --- 3. Kernel ------------------------------------------------------------
cat > /etc/sysctl.d/99-ofogheamn-gaming.conf <<'EOF'
net.netfilter.nf_conntrack_udp_timeout = 120
net.netfilter.nf_conntrack_udp_timeout_stream = 300
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_fastopen = 3
EOF
sysctl -p /etc/sysctl.d/99-ofogheamn-gaming.conf >/dev/null

# --- 4. QoS ---------------------------------------------------------------
update-dc-ranges || echo "WARN: dc range refresh failed (QoS continues)"
ofogheamn-qos || echo "WARN: ofogheamn-qos failed"

# --- 5. Full-set cache warmup ----------------------------------------------
systemctl disable --now ofogh-psn-warm.timer >/dev/null 2>&1 || true
rm -f /etc/systemd/system/ofogh-psn-warm.service /etc/systemd/system/ofogh-psn-warm.timer
cat > /usr/local/bin/ofogh-warm-all.sh <<'EOF'
#!/bin/bash
# Warm the whole gaming sets (A + AAAA) so every gaming lookup is
# a cache hit; serve-expired covers the gaps between runs.
LISTS=/etc/ofogheamn-dns/lists
{ cat "$LISTS/gaming.domains" "$LISTS/cod.domains" "$LISTS/psn.domains" "$LISTS/learned.domains" 2>/dev/null; } \
  | grep -vE '^[[:space:]]*(#|$)' | sort -u \
  | xargs -P 8 -I{} sh -c 'dig @127.0.0.1 {} A >/dev/null 2>&1; dig @127.0.0.1 {} AAAA >/dev/null 2>&1'
EOF
chmod 755 /usr/local/bin/ofogh-warm-all.sh
cat > /etc/systemd/system/ofogh-warm-all.service <<'EOF'
[Unit]
Description=Ofogheamn gaming-set cache warmup
After=ofogheamn-dns.service
[Service]
Type=oneshot
ExecStart=/usr/local/bin/ofogh-warm-all.sh
EOF
cat > /etc/systemd/system/ofogh-warm-all.timer <<'EOF'
[Unit]
Description=Run the gaming-set warmup every 4 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=4min
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now ofogh-warm-all.timer >/dev/null 2>&1 || true
if [ -x /usr/local/bin/ofogh-learn-domains ]; then
cat > /etc/systemd/system/ofogh-learn.service <<'EOF'
[Unit]
Description=Learn gaming domains from the resolver log
After=ofogheamn-dns.service
[Service]
Type=oneshot
ExecStart=/usr/local/bin/ofogh-learn-domains
EOF
cat > /etc/systemd/system/ofogh-learn.timer <<'EOF'
[Unit]
Description=Run the domain learner daily
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now ofogh-learn.timer >/dev/null 2>&1 || true
fi

# --- 6. Tunnels off + firewall private ------------------------------------
systemctl disable --now wg-quick@wg0 strongswan xl2tpd ipsec \
  ofogheamn-wg ofogheamn-vpn >/dev/null 2>&1 || true
printf '%s\n%s\n' "$ADMIN_IP" "$SERVER_IP" > "$ETC/allowlist.txt"
echo "mode=private" > "$ETC/mode.conf"
bash /usr/local/bin/ofogheamn-firewall >/dev/null 2>&1 || true

# --- 7. Services + host resolver ------------------------------------------
systemctl restart ofogheamn-dns ofogheamn-proxy 2>/dev/null || true
sleep 2
printf 'nameserver 127.0.0.1\n' > /etc/resolv.conf

# --- 8. Client configs ------------------------------------------------------
SERVER_IP="$SERVER_IP" HOP_RANGE="$HOP_RANGE" python3 - <<'PY'
import json, os
etc = "/etc/ofogheamn-dns"
ip = os.environ["SERVER_IP"]
hop = os.environ["HOP_RANGE"].replace(":", "-")
hop_start = int(hop.split("-")[0])
client_hop = f"{hop_start}-{hop_start + 400}"
hy2 = json.load(open(f"{etc}/hysteria2.json"))
tls = {"enabled": True, "insecure": True, "server_name": "ofogheamn"}

def client(outbounds, final):
    # The route rule carries udp_timeout: without it, sniffed UDP
    # sessions are reaped at the 10 s/30 s protocol defaults and
    # long game sessions die mid-match (research 2026-11-21).
    return {
        "dns": {"final": "remote",
                "servers": [{"detour": final, "server": ip,
                             "tag": "remote", "type": "udp"}]},
        "inbounds": [{"address": ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
                      "auto_route": True, "mtu": 1280, "stack": "mixed",
                      "strict_route": True, "tag": "tun-in", "type": "tun"}],
        "log": {"level": "warn"},
        "outbounds": outbounds + [{"tag": "direct", "type": "direct"}],
        "route": {"auto_detect_interface": True, "final": final,
                  "rules": [{"action": "route", "outbound": final,
                             "udp_timeout": "10m"}]},
    }

main = {"type": "hysteria2", "tag": "proxy", "server": ip,
        "server_port": int(hy2.get("port", 443)),
        "password": hy2["password"], "tls": tls,
        "hop_ports": client_hop, "hop_interval": "15s", "hop_interval_max": "45s"}
json.dump(client([main], "proxy"),
          open("/root/ofogh-hy2-client.json", "w"), indent=1)
group = [dict(main, tag="proxy-hy2")]

gecko_file = f"{etc}/hysteria2-gecko.json"
if os.path.exists(gecko_file):
    g = json.load(open(gecko_file))
    gob = {"type": "hysteria2", "tag": "proxy", "server": ip,
           "server_port": int(g.get("port", 2083)),
           "password": g["password"], "tls": tls,
           "obfs": {"type": "gecko", "password": g["obfs_password"],
                    "min_packet_size": int(g.get("min_packet_size", 512)),
                    "max_packet_size": int(g.get("max_packet_size", 1200))}}
    json.dump(client([gob], "proxy"),
              open("/root/ofogh-gecko-client.json", "w"), indent=1)
    group.insert(0, dict(gob, tag="proxy-gecko"))

tuic_file = f"{etc}/tuic.json"
if os.path.exists(tuic_file):
    t = json.load(open(tuic_file))
    tob = {"type": "tuic", "tag": "proxy", "server": ip,
           "server_port": int(t.get("port", 8443)),
           "uuid": t["uuid"], "password": t["password"],
           "congestion_control": "bbr", "udp_relay_mode": "native",
           "zero_rtt_handshake": False, "heartbeat": "15s",
           "tls": {"enabled": True, "insecure": True,
                   "server_name": "ofogheamn", "alpn": ["h3"]}}
    json.dump(client([tob], "proxy"),
              open("/root/ofogh-tuic-client.json", "w"), indent=1)
    group.append(dict(tob, tag="proxy-tuic"))

rc_file = f"{etc}/reality-clients.json"
if os.path.exists(rc_file):
    rc = json.load(open(rc_file))
    if rc.get("clients"):
        rob = {"type": "vless", "tag": "proxy-reality", "server": ip,
               "server_port": int(rc.get("port", 4443)),
               "uuid": rc["clients"][0]["uuid"],
               "flow": "xtls-rprx-vision",
               "tls": {"enabled": True,
                       "server_name": rc.get("server_name",
                                             "www.microsoft.com"),
                       "utls": {"enabled": True, "fingerprint": "chrome"},
                       "reality": {"enabled": True,
                                   "public_key": rc.get("public_key", ""),
                                   "short_id": rc.get("short_id", "")}}}
        group.append(rob)

at_file = f"{etc}/anytls.json"
if os.path.exists(at_file):
    a = json.load(open(at_file))
    aob = {"type": "anytls", "tag": "proxy-anytls", "server": ip,
           "server_port": int(a.get("port", 8443)),
           "password": a["password"],
           "tls": {"enabled": True, "insecure": True,
                   "server_name": "ofogheamn", "alpn": ["h2", "http/1.1"]}}
    json.dump(client([dict(aob, tag="proxy")], "proxy"),
              open("/root/ofogh-anytls-client.json", "w"), indent=1)
    group.append(aob)

# The best HTTP option, for HTTP-only devices (browsers, the
# console's web/store path): plain HTTP proxying leaves the
# client-to-node leg readable; HTTP CONNECT over TLS encrypts
# that leg and looks like ordinary HTTPS. TCP-only by design —
# it is NOT part of the game ladder and carries no game UDP.
hp_file = f"{etc}/https-proxy.json"
if os.path.exists(hp_file):
    hp = json.load(open(hp_file))
    hob = {"type": "http", "tag": "proxy", "server": ip,
           "server_port": int(hp.get("port", 9443)),
           "tls": {"enabled": True, "insecure": True,
                   "server_name": "ofogheamn"}}
    json.dump(client([hob], "proxy"),
              open("/root/ofogh-https-client.json", "w"), indent=1)

# The combined client: an urltest group heals the route by itself
# — UDP transports first, the TCP/443 REALITY rung as the fallback
# for the hours when Iran throttles or blocks UDP outright.
auto = {"type": "urltest", "tag": "auto",
        "outbounds": [o["tag"] for o in group],
        "url": "https://www.gstatic.com/generate_204",
        "interval": "30s", "tolerance": 150}
json.dump(client([auto] + group, "auto"),
          open("/root/ofogh-client.json", "w"), indent=1)

# Console gateway variant (research 2026-11-21, checklist item 1):
# the PS5 has no SOCKS5 setting and its built-in HTTP proxy
# carries no game UDP at all — the only way console game traffic
# reaches the node is a gateway in-path running this config on a
# small Linux box between the console and the router (the same
# pattern as GearUP's HYPEREV and the LagoFast Box). LAN DNS is
# hijacked to the node resolver; everything else rides the auto
# group.
gateway = client([auto] + group, "auto")
gateway["inbounds"] = [{
    "address": ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
    "auto_redirect": True, "auto_route": True, "mtu": 1280,
    "stack": "mixed", "strict_route": True, "tag": "tun-in",
    "type": "tun"}]
gateway["route"] = {
    "auto_detect_interface": True, "final": "auto",
    "rules": [{"action": "hijack-dns", "port": 53},
              {"action": "route", "outbound": "auto",
               "udp_timeout": "10m"}]}
json.dump(gateway, open("/root/ofogh-gateway.json", "w"), indent=1)
print("client configs: /root/ofogh-client.json (auto: "
      + ", ".join(o["tag"] for o in group)
      + ") + /root/ofogh-gateway.json (console gateway)"
      + " + single-transport files")
PY

echo "== self-check"
dig @127.0.0.1 demonware.net +time=3 +tries=1 2>/dev/null | grep -q 'status: NOERROR' \
  && echo "PASS dns answers (demonware.net)" || echo "WARN dns check failed"
ss -lun 2>/dev/null | grep -q ':2083 ' \
  && echo "PASS gecko listener udp/2083" || echo "WARN gecko listener not seen"
ss -lun 2>/dev/null | grep -q ':8443 ' \
  && echo "PASS tuic listener udp/8443" || echo "WARN tuic listener not seen"
ss -tln 2>/dev/null | grep -q ':8443 ' \
  && echo "PASS anytls listener tcp/8443" || echo "WARN anytls listener not seen"
ss -tln 2>/dev/null | grep -q ':9443 ' \
  && echo "PASS https-proxy listener tcp/9443" || echo "WARN https-proxy listener not seen"
iptables -t nat -S 2>/dev/null | grep -q '20000' \
  && echo "PASS port-hopping NAT present" || echo "WARN port-hopping NAT not seen"
[ -f /root/ofogh-gecko-client.json ] \
  && echo "PASS client configs written" || echo "WARN client configs missing"
[ -f /root/ofogh-gateway.json ] \
  && echo "PASS console gateway config written" || echo "WARN gateway config missing"
ofogheamn-dns bench 2>/dev/null || true
echo "== node profile iran-baku applied"

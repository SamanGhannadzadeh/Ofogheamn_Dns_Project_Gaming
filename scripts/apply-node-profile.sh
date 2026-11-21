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
#   5. PSN cache warmup every 4 minutes (CoD warmup ships with
#      the installer).
#   6. Tunnels OFF (final product scope is DNS + proxy only) and
#      the firewall in private mode: only the admin IP and the
#      server's own IP may reach the service ports.
#   7. The host resolver points at the node itself, last.
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
grep -q 'domain-set -name psn' "$CONF" || \
  echo "domain-set -name psn -file $ETC/lists/psn.domains" >> "$CONF"
grep -q 'domain-rules /domain-set:psn/' "$CONF" || \
  echo "domain-rules /domain-set:psn/ -speed-check-mode ping,tcp:443 -response-mode fastest-ip -rr-ttl-min 120" >> "$CONF"
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
ofogheamn-dns hysteria2-gecko enable 2083 >/dev/null 2>&1 || true
python3 /usr/local/lib/ofogheamn-dns/gen-singbox-config.py
sing-box check -c /etc/ofogheamn-dns/singbox.json 2>/dev/null || \
  sing-box check -c "$(ls /etc/ofogheamn-dns/*.json | head -1)" || true

# --- 3. Kernel ------------------------------------------------------------
cat > /etc/sysctl.d/99-ofogheamn-gaming.conf <<'EOF'
net.netfilter.nf_conntrack_udp_timeout = 120
net.netfilter.nf_conntrack_udp_timeout_stream = 180
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_fastopen = 3
EOF
sysctl -p /etc/sysctl.d/99-ofogheamn-gaming.conf >/dev/null

# --- 4. QoS ---------------------------------------------------------------
update-dc-ranges || echo "WARN: dc range refresh failed (QoS continues)"
ofogheamn-qos || echo "WARN: ofogheamn-qos failed"

# --- 5. PSN warmup ---------------------------------------------------------
cat > /usr/local/bin/ofogh-psn-warm.sh <<'EOF'
#!/bin/bash
for h in ps5.np.playstation.net us.np.stun.playstation.net \
         native.np.playstation.net playstation.com playstation.net \
         auth.api.sonyentertainmentnetwork.com; do
  dig @127.0.0.1 "$h" >/dev/null 2>&1
done
EOF
chmod 755 /usr/local/bin/ofogh-psn-warm.sh
cat > /etc/systemd/system/ofogh-psn-warm.service <<'EOF'
[Unit]
Description=Ofogheamn PSN cache warmup
After=ofogheamn-dns.service
[Service]
Type=oneshot
ExecStart=/usr/local/bin/ofogh-psn-warm.sh
EOF
cat > /etc/systemd/system/ofogh-psn-warm.timer <<'EOF'
[Unit]
Description=Run PSN warmup every 4 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=4min
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now ofogh-psn-warm.timer >/dev/null 2>&1 || true

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

echo "== self-check"
dig @127.0.0.1 demonware.net +time=3 +tries=1 2>/dev/null | grep -q 'status: NOERROR' \
  && echo "PASS dns answers (demonware.net)" || echo "WARN dns check failed"
ss -lun 2>/dev/null | grep -q ':2083 ' \
  && echo "PASS gecko listener udp/2083" || echo "WARN gecko listener not seen"
iptables -t nat -S 2>/dev/null | grep -q '20000' \
  && echo "PASS port-hopping NAT present" || echo "WARN port-hopping NAT not seen"
echo "== node profile iran-baku applied"

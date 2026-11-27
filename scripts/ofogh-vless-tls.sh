#!/bin/bash
# Add a VLESS + TCP + real-TLS (Let's Encrypt) + xtls-rprx-vision
# inbound on tcp/2053 — the classic "V2Ray" flavor, mirroring what
# large Iranian panels ship. Idempotent.
set -e
ETC="${OFOGH_ETC:-/etc/ofogheamn-dns}"
PORT=2053
NAME=ofogheamn.mytunnel.org

# 1) descriptor for the firewall loop
if [ ! -f "$ETC/vless-tls.json" ]; then
  python3 - <<PYEOF
import json
reality = json.load(open("$ETC/reality-clients.json"))
uuid = reality["clients"][0]["uuid"]
json.dump({"port": $PORT, "protocol": "vless", "security": "tls",
           "server_name": "$NAME", "user": "operator", "uuid": uuid},
          open("$ETC/vless-tls.json", "w"), indent=1)
print("descriptor written")
PYEOF
fi

# 2) firewall: join the guarded spec loop
FW="${OFOGH_FW:-/usr/local/bin/ofogheamn-firewall}"
cp "$FW" "$FW.bak-vlesstls-$(date +%Y%m%d%H%M)"
if ! grep -q 'vless-tls.json' "$FW"; then
  sed -i 's|"https-proxy.json tcp HTTPS-Proxy"|"https-proxy.json tcp HTTPS-Proxy" "vless-tls.json tcp VLESS-TLS"|' "$FW"
  echo "firewall spec added"
fi

# 3) sing-box inbound
cp "$ETC/singbox.json" "$ETC/singbox.json.bak-vlesstls-$(date +%Y%m%d%H%M)"
python3 - <<'PYEOF'
import json
p = "/etc/ofogheamn-dns/singbox.json"
cfg = json.load(open(p))
if any(ib.get("tag") == "vless-tls-in" for ib in cfg.get("inbounds", [])):
    print("inbound already present")
else:
    desc = json.load(open("/etc/ofogheamn-dns/vless-tls.json"))
    cfg["inbounds"].append({
        "type": "vless", "tag": "vless-tls-in",
        "listen": "::", "listen_port": desc["port"],
        "users": [{"name": "operator", "uuid": desc["uuid"],
                   "flow": "xtls-rprx-vision"}],
        "tls": {"enabled": True, "server_name": "ofogheamn.mytunnel.org",
                "certificate_path": "/etc/ofogheamn-dns/tls/fullchain.pem",
                "key_path": "/etc/ofogheamn-dns/tls/privkey.pem"},
    })
    json.dump(cfg, open(p, "w"), indent=1)
    print("inbound added")
PYEOF

# 4) cert renewal should also refresh the proxy's TLS
if ! grep -q "ofogheamn-proxy" /usr/local/bin/ofogh-cert-sync.sh; then
  echo "systemctl restart ofogheamn-proxy.service || true" >> /usr/local/bin/ofogh-cert-sync.sh
  echo "cert-sync now restarts proxy too"
fi

# 5) apply
systemctl restart ofogheamn-firewall.service || bash "$FW"
systemctl restart ofogheamn-proxy.service
sleep 2
echo "proxy: $(systemctl is-active ofogheamn-proxy.service)"
ss -tlnp 2>/dev/null | grep 2053 | head -1
iptables -S INPUT | grep 2053 | head -1
echo VLESSTLS-DONE

#!/bin/sh
# ============================================================
#  Ofogheamn DNS — OpenWrt installer
#  OpenWrt ships SmartDNS as a native package, so the router
#  itself becomes the gaming DNS for the whole LAN.
#    sh install-openwrt.sh
#  The proxy (sing-box) is also in the OpenWrt feed on many
#  targets; the panel needs python3 (install if your flash
#  allows). DNS + hijack + lists work everywhere.
# ============================================================
set -e
REPO_RAW="https://raw.githubusercontent.com/saman-ghannadzadeh/Ofogheamn_Dns_Project_Gaming/main"
ETC=/etc/ofogheamn-dns

opkg update
opkg install smartdns curl ca-bundle openssl-util
mkdir -p "$ETC/lists" "$ETC/tls"

# mesh-upstream.conf is not optional: smartdns.conf includes it
# and SmartDNS refuses to start when an included file is missing
# (proven with the real binary; the bare-metal installer learned
# this in v1.2.1, this script missed it until v1.4).
for f in smartdns.conf hijack.conf blocklist.conf force-dns.conf mesh-upstream.conf; do
  curl -fsSL -o "$ETC/$f" "$REPO_RAW/config/$f"
done
for f in gaming.domains cod.domains; do
  curl -fsSL -o "$ETC/lists/$f" "$REPO_RAW/config/lists/$f"
done
# TLS material is not optional either: SmartDNS exits at startup
# when the bind-cert files do not exist (no auto-generation —
# proven with the real binary). Self-signed, like the other
# installers; replace with a real cert for public DoT/DoH.
if [ ! -s "$ETC/tls/fullchain.pem" ]; then
  HOSTNAME_DNS="${OFOGH_DNS_HOSTNAME:-dns.ofogheamn.ir}"
  sed -i "s/^bind-cert-san .*/bind-cert-san $HOSTNAME_DNS/" "$ETC/smartdns.conf"
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
    -keyout "$ETC/tls/privkey.pem" -out "$ETC/tls/fullchain.pem" \
    -subj "/CN=$HOSTNAME_DNS" -addext "subjectAltName=DNS:$HOSTNAME_DNS" >/dev/null 2>&1
  chmod 600 "$ETC/tls/privkey.pem"
fi
# The packaged smartdns service stays DISABLED: the project
# service below runs the packaged binary with the project config.
# Enabling both (this script used to set enabled='1') makes them
# fight over port 53 at boot (v1.4 fix).
/etc/init.d/smartdns stop 2>/dev/null || true
uci -q set smartdns.@smartdns[0].enabled='0' 2>/dev/null || true
# Run smartdns directly with the project config at boot:
cat > /etc/init.d/ofogheamn-dns <<'EOF'
#!/bin/sh /etc/rc.common
START=99
USE_PROCD=1
start_service() {
  procd_open_instance
  procd_set_param command /usr/sbin/smartdns -f -c /etc/ofogheamn-dns/smartdns.conf -p /var/run/ofogheamn.pid
  procd_set_param respawn
  procd_close_instance
}
EOF
chmod 755 /etc/init.d/ofogheamn-dns
/etc/init.d/ofogheamn-dns enable
/etc/init.d/ofogheamn-dns start

# Make the router hand THIS DNS out via DHCP and intercept
# strays (same enforcement as the gateway/ scripts). The DNS
# handed out is the router's own LAN address — hardcoding
# 192.168.1.1 here pointed clients at a dead resolver on every
# network that uses a different LAN subnet (v1.4 fix).
LAN_IP="$(uci -q get network.lan.ipaddr | cut -d/ -f1)"
[ -n "$LAN_IP" ] || LAN_IP=192.168.1.1
uci add_list dhcp.lan.dhcp_option="6,$LAN_IP" 2>/dev/null || true
uci commit dhcp 2>/dev/null || true
echo "Ofogheamn DNS running on this OpenWrt router (port 53)."
echo "Set the router LAN IP as DNS on clients, or rely on DHCP."

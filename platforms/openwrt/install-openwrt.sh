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
opkg install smartdns curl ca-bundle
mkdir -p "$ETC/lists"

for f in smartdns.conf hijack.conf blocklist.conf force-dns.conf; do
  curl -fsSL -o "$ETC/$f" "$REPO_RAW/config/$f"
done
for f in gaming.domains cod.domains; do
  curl -fsSL -o "$ETC/lists/$f" "$REPO_RAW/config/lists/$f"
done
# OpenWrt keeps its own smartdns config dir; point the packaged
# service at the project config instead of /etc/smartdns.
/etc/init.d/smartdns stop 2>/dev/null || true
uci -q set smartdns.@smartdns[0].enabled='1' 2>/dev/null || true
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
# strays (same enforcement as the gateway/ scripts):
uci add_list dhcp.lan.dhcp_option='6,192.168.1.1' 2>/dev/null || true
uci commit dhcp 2>/dev/null || true
echo "Ofogheamn DNS running on this OpenWrt router (port 53)."
echo "Set the router LAN IP as DNS on clients, or rely on DHCP."

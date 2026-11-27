#!/bin/bash
# Bring up the Ofogheamn VPN servers (L2TP/IPsec + PPTP).
# Used by ofogheamn-vpn.service. Renders the daemon credential
# files from /etc/ofogheamn-dns/vpn.conf — the ONE place VPN
# credentials live — then applies NAT for the client pools and
# starts strongSwan + xl2tpd + pptpd. Same exit model as the
# WireGuard tunnel: client -> this node (DNS + NAT) -> game.
# Static daemon configs (/etc/ipsec.conf, /etc/xl2tpd/xl2tpd.conf,
# /etc/pptpd.conf, /etc/ppp/options.*) are installed by install.sh
# from config/vpn/ in the repo.
set -u
ETC=/etc/ofogheamn-dns
CONF="$ETC/vpn.conf"
[ -r "$CONF" ] || { echo "no vpn.conf"; exit 1; }
get() { grep -E "^$1=" "$CONF" 2>/dev/null | cut -d= -f2; }
VPN_USER="$(get user)"; VPN_PASS="$(get pass)"; VPN_PSK="$(get psk)"
L2TP_POOL="$(get l2tp_pool)"; L2TP_POOL="${L2TP_POOL:-10.67.0.0/24}"
PPTP_POOL="$(get pptp_pool)"; PPTP_POOL="${PPTP_POOL:-10.68.0.0/24}"
[ -n "$VPN_USER" ] && [ -n "$VPN_PASS" ] && [ -n "$VPN_PSK" ] \
  || { echo "vpn.conf incomplete (need user, pass, psk)"; exit 1; }

# --- render credential files (edit vpn.conf, never these) ---
# Escape backslashes and quotes first (v1.33): a " in a password
# used to silently produce broken daemon credential files.
esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
printf '%s\n%s\n' "# rendered by ofogheamn-vpn-setup from $CONF" \
  "\"$(esc "$VPN_USER")\" * \"$(esc "$VPN_PASS")\" *" > /etc/ppp/chap-secrets
chmod 600 /etc/ppp/chap-secrets
printf ': PSK "%s"\n' "$(esc "$VPN_PSK")" > /etc/ipsec.secrets
chmod 600 /etc/ipsec.secrets

# Kernel helpers: MPPE for PPTP, kernel L2TP for xl2tpd.
modprobe ppp_mppe 2>/dev/null || true
modprobe l2tp_ppp 2>/dev/null || true
sysctl -qw net.ipv4.ip_forward=1

EXT="$(ip route show default | awk '{print $5; exit}')"
for pool in "$L2TP_POOL" "$PPTP_POOL"; do
  iptables -t nat -C POSTROUTING -s "$pool" -o "$EXT" -j MASQUERADE 2>/dev/null \
    || iptables -t nat -A POSTROUTING -s "$pool" -o "$EXT" -j MASQUERADE
done

# Daemon unit names differ slightly across Debian/Ubuntu releases.
systemctl start strongswan-starter 2>/dev/null \
  || systemctl start strongswan 2>/dev/null \
  || systemctl start ipsec 2>/dev/null || true
systemctl start xl2tpd 2>/dev/null || true
systemctl start pptpd 2>/dev/null || true
echo "vpn up (l2tp pool $L2TP_POOL, pptp pool $PPTP_POOL, egress: $EXT)"

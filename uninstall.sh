#!/bin/bash
# Remove Ofogheamn DNS completely (services, files, firewall chain).
set -e
[ "$(id -u)" = "0" ] || { echo "run with sudo"; exit 1; }
systemctl disable --now ofogheamn-dns ofogheamn-panel ofogheamn-proxy cod-warmup.timer ofogheamn-health.timer ofogheamn-recursive 2>/dev/null || true
# Also disable the units install.sh (or the owner, for mesh)
# enables conditionally — deleting an enabled unit's file without
# disabling it leaves a dangling wants symlink behind (v1.4 fix).
systemctl disable --now ofogheamn-vpn ofogheamn-wg ofogheamn-mesh ofogheamn-blocklist.timer 2>/dev/null || true
systemctl disable --now ofogh-sni-relay ofogh-mm-relay 2>/dev/null || true
# v1.33: the DDNS units, the boot firewall unit and the profile's
# units were installed but never disabled or removed here.
systemctl disable --now ofogh-ddns.timer ofogheamn-firewall 2>/dev/null || true
systemctl disable --now ofogh-warm-all.timer ofogh-learn.timer 2>/dev/null || true
# The distro VPN daemons were only stopped, so they returned at
# boot running the project's configs; disable them too (v1.33).
systemctl disable --now strongswan-starter xl2tpd pptpd 2>/dev/null || true
ip link del wg0 2>/dev/null || true
rm -f /etc/systemd/system/ofogheamn-dns.service /etc/systemd/system/ofogheamn-panel.service \
      /etc/systemd/system/ofogheamn-proxy.service /etc/systemd/system/cod-warmup.service \
      /etc/systemd/system/cod-warmup.timer /etc/systemd/system/ofogheamn-health.service \
      /etc/systemd/system/ofogheamn-health.timer /etc/systemd/system/ofogheamn-wg.service \
      /etc/systemd/system/ofogheamn-vpn.service \
      /etc/systemd/system/ofogheamn-mesh.service /etc/systemd/system/ofogheamn-blocklist.service \
      /etc/systemd/system/ofogheamn-blocklist.timer /etc/systemd/system/ofogheamn-recursive.service \
      /etc/systemd/system/ofogh-sni-relay.service /etc/systemd/system/ofogh-mm-relay.service \
      /etc/systemd/system/ofogh-ddns.service /etc/systemd/system/ofogh-ddns.timer \
      /etc/systemd/system/ofogheamn-firewall.service \
      /etc/systemd/system/ofogh-warm-all.service /etc/systemd/system/ofogh-warm-all.timer \
      /etc/systemd/system/ofogh-learn.service /etc/systemd/system/ofogh-learn.timer
rm -f /etc/sysctl.d/99-ofogheamn-dns.conf /etc/sysctl.d/99-ofogheamn-gaming.conf
rm -f /usr/local/bin/ofogheamn-dns /usr/local/bin/smartdns /usr/local/bin/sing-box \
      /usr/local/bin/cod-warmup /usr/local/bin/ofogheamn-firewall \
      /usr/local/bin/ofogheamn-region.py /usr/local/bin/ofogheamn-bench.py \
      /usr/local/bin/ofogheamn-health.py /usr/local/bin/ofogheamn-wg-peer \
      /usr/local/bin/ofogheamn-vpn-setup /usr/local/bin/ofogheamn-wg-setup \
      /usr/local/bin/ofogheamn-mesh.py /usr/local/bin/update-blocklist \
      /usr/local/bin/ofogh-sni-relay.py /usr/local/bin/ofogh-mm-relay.py \
      /usr/local/bin/ofogh-edge-pins \
      /usr/local/bin/ofogheamn-qos /usr/local/bin/update-dc-ranges \
      /usr/local/bin/ofogh-learn-domains /usr/local/bin/ofogh-ddns-allowlist \
      /usr/local/bin/ofogh-warm-all.sh
rm -rf /usr/local/lib/ofogheamn-dns
# --- firewall state (v1.33) ---
# The old uninstall only flushed the chain: every INPUT jump the
# firewall script inserted stayed behind, so -X failed while the
# chain was still referenced and the host kept the project's rules
# forever. Delete the jumps first (scan-and-delete by exact spec,
# both address families), then the chains, then the fixed
# non-chain rules (VPN accepts, MSS clamps, NAT hop redirect,
# MASQUERADEs, QoS ipsets).
del_jumps() { # $1 = iptables binary, $2 = chain
  local spec i
  for i in $(seq 1 80); do
    spec="$("$1" -S INPUT 2>/dev/null | grep -F -- "-j $2" | head -1 | sed 's/^-A INPUT //')"
    [ -n "$spec" ] || break
    # shellcheck disable=SC2086
    "$1" -D INPUT $spec 2>/dev/null || break
  done
}
del_jumps iptables OFOGH_DNS_IN
del_jumps ip6tables OFOGH_DNS_IN6
# Transport/console/mm jumps inserted as bare ACCEPT/DROP (ports
# come from the feature JSONs, read before /etc is removed below).
for jf in console.json hysteria2.json hysteria2-gecko.json tuic.json anytls.json reality.json https-proxy.json mm-relay.json; do
  if [ -r "/etc/ofogheamn-dns/$jf" ]; then
    p="$(python3 -c "import json;print(json.load(open('/etc/ofogheamn-dns/$jf'))['port'])" 2>/dev/null || true)"
    if [ -n "$p" ]; then
      for bin in iptables ip6tables; do
        for proto in udp tcp; do
          for tgt in ACCEPT DROP; do
            while "$bin" -C INPUT -p "$proto" --dport "$p" -j "$tgt" 2>/dev/null; do
              "$bin" -D INPUT -p "$proto" --dport "$p" -j "$tgt" || break
            done
          done
        done
      done
    fi
  fi
done
for proto in udp tcp; do
  while iptables -C INPUT -p "$proto" --dport 2080 -j DROP 2>/dev/null; do
    iptables -D INPUT -p "$proto" --dport 2080 -j DROP || break
  done
  while ip6tables -C INPUT -p "$proto" --dport 2080 -j DROP 2>/dev/null; do
    ip6tables -D INPUT -p "$proto" --dport 2080 -j DROP || break
  done
done
iptables -F OFOGH_DNS_IN 2>/dev/null || true
iptables -X OFOGH_DNS_IN 2>/dev/null || true
ip6tables -F OFOGH_DNS_IN6 2>/dev/null || true
ip6tables -X OFOGH_DNS_IN6 2>/dev/null || true
for spec in "udp 500" "udp 4500" "udp 1701" "tcp 1723"; do
  set -- $spec
  while iptables -C INPUT -p "$1" --dport "$2" -j ACCEPT 2>/dev/null; do
    iptables -D INPUT -p "$1" --dport "$2" -j ACCEPT || break
  done
done
for proto in esp gre; do
  while iptables -C INPUT -p "$proto" -j ACCEPT 2>/dev/null; do
    iptables -D INPUT -p "$proto" -j ACCEPT || break
  done
done
if [ -r /etc/ofogheamn-dns/hysteria2.json ]; then
  hop="$(python3 -c "import json;print(json.load(open('/etc/ofogheamn-dns/hysteria2.json')).get('hop_range',''))" 2>/dev/null || true)"
  hy2p="$(python3 -c "import json;print(json.load(open('/etc/ofogheamn-dns/hysteria2.json'))['port'])" 2>/dev/null || true)"
  if [ -n "$hop" ] && [ -n "$hy2p" ]; then
    iptables -t nat -D PREROUTING -p udp --dport "${hop%-*}:${hop#*-}" -j REDIRECT --to-ports "$hy2p" 2>/dev/null || true
  fi
fi
for iface in wg0 ppp+; do
  for dir in -i -o; do
    while iptables -t mangle -C FORWARD $dir "$iface" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null; do
      iptables -t mangle -D FORWARD $dir "$iface" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu || break
    done
  done
done
for subnet in 10.66.0.0/24 10.67.0.0/24; do
  spec="$(iptables -t nat -S POSTROUTING 2>/dev/null | grep -F -- "-s $subnet" | grep -F MASQUERADE | head -1 | sed 's/^-A POSTROUTING //')"
  # shellcheck disable=SC2086
  [ -n "$spec" ] && iptables -t nat -D POSTROUTING $spec 2>/dev/null || true
done
ipset destroy cod 2>/dev/null || true
ipset destroy dc 2>/dev/null || true
# --- host resolver restore (v1.33) ---
# install.sh replaced /etc/resolv.conf (keeping a backup) and
# disabled the resolved stub; undo both, or the host is left
# resolving through a SmartDNS that no longer exists.
if [ -e /etc/ofogheamn-dns/resolv.conf.bak ]; then
  rm -f /etc/resolv.conf
  cp -a /etc/ofogheamn-dns/resolv.conf.bak /etc/resolv.conf
elif grep -q '^nameserver 127.0.0.1' /etc/resolv.conf 2>/dev/null; then
  printf 'nameserver 1.1.1.1\n' > /etc/resolv.conf
  echo "WARNING: no pre-install resolv.conf backup found; wrote a 1.1.1.1 placeholder — set your resolver."
fi
rm -f /etc/systemd/resolved.conf.d/no-stub.conf
systemctl restart systemd-resolved 2>/dev/null || true
# Remove the ufw openings install.sh added (only where ufw is
# active, mirroring the installer's condition).
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  for r in 53 853 443/udp 443/tcp 2080 8080 3074/tcp 51820/udp 500/udp 4500/udp 1701/udp 1723/tcp; do
    ufw delete allow "$r" >/dev/null 2>&1 || true
  done
  ufw delete allow proto esp >/dev/null 2>&1 || true
  ufw delete allow proto gre >/dev/null 2>&1 || true
fi
# Credential files the VPN setup rendered from vpn.conf: the PSK
# file is wholly ours; chap-secrets is removed only when it
# carries our rendered header (an admin's own entries stay).
rm -f /etc/ipsec.secrets
grep -q '^# rendered by ofogheamn-vpn-setup' /etc/ppp/chap-secrets 2>/dev/null && rm -f /etc/ppp/chap-secrets
rm -rf /etc/ofogheamn-dns /var/cache/ofogheamn-dns /var/log/ofogheamn-dns
userdel ofodns 2>/dev/null || true
systemctl daemon-reload
echo "Ofogheamn DNS removed."

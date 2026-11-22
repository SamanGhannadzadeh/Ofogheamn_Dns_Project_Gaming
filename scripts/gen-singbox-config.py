#!/usr/bin/env python3
"""Generate the sing-box proxy config from the project's user store.

Single source of truth, used by install.sh, the panel and the CLI.
  users store : /etc/ofogheamn-dns/proxy-users.json  [{"user","pass"}]
  output      : /etc/ofogheamn-dns/singbox.json
The proxy is a "mixed" inbound (HTTP + SOCKS5 on one port, with
SOCKS5 UDP ASSOCIATE for game UDP) and a direct outbound.

Optional console inbound: game consoles (PS5/Xbox) offer an HTTP
proxy setting with NO username/password fields, so the
authenticated port can never work for them. When
/etc/ofogheamn-dns/console.json exists ({"port": 2081}), a second
inbound WITHOUT auth is added on that port — HTTP only, because
HTTP is the one and only proxy protocol a console implements
natively; it carries the console's TCP (web, store, downloads)
to every IP and port, and console game UDP never enters the
console's proxy setting at all. It is safe only
because ofogheamn-firewall guards the console port with the
private-mode allowlist (and drops it entirely in public mode);
never expose it any other way. Managed by:
  ofogheamn-dns console enable|disable|status
"""
import json
import os
import sys

ETC = os.environ.get("OFOGH_ETC", "/etc/ofogheamn-dns")
PORT = int(os.environ.get("OFOGH_PROXY_PORT", "2080"))


def main() -> int:
    users_file = os.path.join(ETC, "proxy-users.json")
    users = []
    if os.path.exists(users_file):
        with open(users_file, encoding="utf-8") as fh:
            users = [u for u in json.load(fh) if u.get("user") and u.get("pass")]
    inbounds = [
        {
            "type": "mixed",
            "tag": "ofogh-mixed",
            "listen": "::",
            "listen_port": PORT,
            "users": [{"username": u["user"], "password": u["pass"]} for u in users],
            "tcp_fast_open": True,
            "udp_timeout": "10m",
            "udp_fragment": True,
        }
    ]
    # Optional console inbound (see module docstring): no auth, for
    # PS5/Xbox proxy settings. HTTP only — the single proxy
    # protocol a console speaks natively.
    console_file = os.path.join(ETC, "console.json")
    console_port = None
    if os.path.exists(console_file):
        with open(console_file, encoding="utf-8") as fh:
            console_port = int(json.load(fh).get("port", 2081))
        inbounds.append({
            "type": "http",
            "tag": "ofogh-console",
            "listen": "::",
            "listen_port": console_port,
            "tcp_fast_open": True,
        })
    # Optional VLESS+REALITY inbound (transport fallback ladder, top
    # rung for filtered paths — enabled via `ofogheamn-dns reality
    # enable`, which writes /etc/ofogheamn-dns/reality.json). The
    # mixed proxy stays as the always-on baseline.
    reality_file = os.path.join(ETC, "reality.json")
    if os.path.exists(reality_file):
        import uuid as uuidlib
        with open(reality_file, encoding="utf-8") as fh:
            r = json.load(fh)
        # VLESS needs UUIDs; the proxy store has user/pass. Derive a
        # stable per-user UUID (uuid5) so REALITY clients map 1:1 to
        # proxy users, and publish them for the operator.
        clients = []
        vless_users = []
        for u in users:
            uid = str(uuidlib.uuid5(uuidlib.NAMESPACE_URL, "ofogheamn:" + u["user"]))
            vless_users.append({"uuid": uid, "flow": "xtls-rprx-vision"})
            clients.append({"user": u["user"], "uuid": uid})
        if not clients:
            # No-auth SOCKS product scope (empty user store): the
            # REALITY rung still needs one client or it accepts
            # nobody — emit a single operator client.
            uid = str(uuidlib.uuid5(uuidlib.NAMESPACE_URL,
                                    "ofogheamn:operator"))
            vless_users.append({"uuid": uid, "flow": "xtls-rprx-vision"})
            clients.append({"user": "operator", "uuid": uid})
        with open(os.path.join(ETC, "reality-clients.json"), "w", encoding="utf-8") as fh:
            json.dump({"server_name": r.get("server_name", "www.microsoft.com"),
                       "port": int(r.get("port", 443)),
                       "public_key": r.get("public_key", ""),
                       "short_id": r.get("short_id", ""),
                       "clients": clients}, fh, indent=2)
        os.chmod(os.path.join(ETC, "reality-clients.json"), 0o600)
        inbounds.append({
            "type": "vless",
            "tag": "ofogh-reality",
            "listen": "::",
            "listen_port": int(r.get("port", 443)),
            "users": vless_users,
            "tls": {
                "enabled": True,
                "server_name": r.get("server_name", "www.microsoft.com"),
                "reality": {
                    "enabled": True,
                    "handshake": {"server": r.get("server_name", "www.microsoft.com"),
                                  "server_port": 443},
                    "private_key": r["private_key"],
                    "short_id": [r.get("short_id", "")],
                },
            },
        })
    # Optional Hysteria2 inbound (transport ladder rung 2: QUIC +
    # Brutal congestion control — holds speed on lossy paths where
    # WireGuard collapses; enabled via `ofogheamn-dns hysteria2
    # enable`, which writes /etc/ofogheamn-dns/hysteria2.json).
    # Uses the node's own TLS cert (same pair as DoT/DoH).
    hy2_file = os.path.join(ETC, "hysteria2.json")
    hy2_port = None
    if os.path.exists(hy2_file):
        with open(hy2_file, encoding="utf-8") as fh:
            h = json.load(fh)
        hy2_port = int(h.get("port", 443))
        hy2 = {
            "type": "hysteria2",
            "tag": "ofogh-hysteria2",
            "listen": "::",
            "listen_port": hy2_port,
            "users": [{"password": h["password"]}],
            "bbr_profile": h.get("bbr_profile", "conservative"),
            "tls": {
                "enabled": True,
                "certificate_path": os.path.join(ETC, "tls", "fullchain.pem"),
                "key_path": os.path.join(ETC, "tls", "privkey.pem"),
            },
        }
        if h.get("obfs_password"):
            # Gecko (sing-box >= 1.14) randomises packet sizes;
            # Salamander is the v1.7 default and stays the
            # fallback when no obfs type is named.
            hy2["obfs"] = {"type": h.get("obfs", "salamander"),
                           "password": h["obfs_password"]}
        if h.get("masquerade_url"):
            # Active-probe resistance: probing the UDP port is
            # answered by a real website's QUIC stack. Flat form —
            # sing-box rejects a nested "proxy" object here.
            hy2["masquerade"] = {"type": "proxy",
                                 "url": h["masquerade_url"],
                                 "rewrite_host": True}
        inbounds.append(hy2)
    # Optional PARALLEL Hysteria2+Gecko inbound (v1.17, from the
    # 2026 Iran-DPI research): a second hy2 listener whose obfs is
    # Gecko — Salamander scrambling PLUS fragmentation of the QUIC
    # long-header (handshake) packets, which breaks the ~1200-byte
    # Initial size clustering plain Salamander leaves behind. It
    # runs alongside the main inbound so existing clients keep
    # working untouched. On this listener obfs REPLACES the
    # masquerade: a prober without the obfs password gets silence.
    gecko_file = os.path.join(ETC, "hysteria2-gecko.json")
    gecko_port = None
    if os.path.exists(gecko_file):
        with open(gecko_file, encoding="utf-8") as fh:
            g = json.load(fh)
        gecko_port = int(g.get("port", 2083))
        inbounds.append({
            "type": "hysteria2",
            "tag": "ofogh-hysteria2-gecko",
            "listen": "::",
            "listen_port": gecko_port,
            "users": [{"password": g["password"]}],
            "bbr_profile": g.get("bbr_profile", "conservative"),
            "obfs": {"type": "gecko",
                     "password": g["obfs_password"],
                     "min_packet_size": int(g.get("min_packet_size", 512)),
                     "max_packet_size": int(g.get("max_packet_size", 1200))},
            "tls": {
                "enabled": True,
                "certificate_path": os.path.join(ETC, "tls", "fullchain.pem"),
                "key_path": os.path.join(ETC, "tls", "privkey.pem"),
            },
        })
    # Optional TUIC v5 inbound (the other QUIC rung: gentler
    # congestion control than Hysteria2's Brutal — BBR here;
    # 0-RTT stays OFF (replay risk, per sing-box docs);
    # enabled via `ofogheamn-dns tuic enable`,
    # which writes /etc/ofogheamn-dns/tuic.json).
    tuic_file = os.path.join(ETC, "tuic.json")
    tuic_port = None
    if os.path.exists(tuic_file):
        with open(tuic_file, encoding="utf-8") as fh:
            t = json.load(fh)
        tuic_port = int(t.get("port", 8443))
        inbounds.append({
            "type": "tuic",
            "tag": "ofogh-tuic",
            "listen": "::",
            "listen_port": tuic_port,
            "users": [{"uuid": t["uuid"], "password": t["password"]}],
            "congestion_control": "bbr",
            "zero_rtt_handshake": False,
            "tls": {
                "enabled": True,
                "certificate_path": os.path.join(ETC, "tls", "fullchain.pem"),
                "key_path": os.path.join(ETC, "tls", "privkey.pem"),
            },
        })
    # Optional AnyTLS inbound (targets the TLS-in-TLS
    # fingerprint of nested tunnels; enabled via
    # `ofogheamn-dns anytls enable`, which writes
    # /etc/ofogheamn-dns/anytls.json).
    anytls_file = os.path.join(ETC, "anytls.json")
    anytls_port = None
    if os.path.exists(anytls_file):
        with open(anytls_file, encoding="utf-8") as fh:
            a = json.load(fh)
        anytls_port = int(a.get("port", 8443))
        inbounds.append({
            "type": "anytls",
            "tag": "ofogh-anytls",
            "listen": "::",
            "listen_port": anytls_port,
            "users": [{"name": "ofogh", "password": a["password"]}],
            "tls": {
                "enabled": True,
                "certificate_path": os.path.join(ETC, "tls", "fullchain.pem"),
                "key_path": os.path.join(ETC, "tls", "privkey.pem"),
            },
        })
    hp_file = os.path.join(ETC, "https-proxy.json")
    if os.path.exists(hp_file):
        with open(hp_file) as fh:
            hp = json.load(fh)
        inbounds.append({
            "type": "http",
            "tag": "ofogh-https-proxy",
            "listen": "::",
            "listen_port": int(hp.get("port", 9443)),
            "tls": {
                "enabled": True,
                "certificate_path": os.path.join(ETC, "tls", "fullchain.pem"),
                "key_path": os.path.join(ETC, "tls", "privkey.pem"),
            },
        })
    # Port-collision guard (v1.12): two inbounds sharing a
    # transport+port only fail when sing-box STARTS — after the
    # operator already restarted the service. Refuse here, with
    # the tags named, while the old config is still on disk.
    transports = {"mixed": ("tcp", "udp"), "hysteria2": ("udp",),
                  "tuic": ("udp",), "anytls": ("tcp",), "vless": ("tcp",)}
    seen = {}
    for ib in inbounds:
        for proto in transports.get(ib.get("type"), ("tcp",)):
            key = (proto, ib.get("listen_port"))
            if key in seen:
                print(f"error: port collision — {seen[key]} and "
                      f"{ib.get('tag')} both want {proto}/{ib.get('listen_port')}; "
                      "change one port and retry", file=sys.stderr)
                return 1
            seen[key] = ib.get("tag")
    cfg = {
        "log": {
            "level": "info",
            "output": "/var/log/ofogheamn-dns/singbox.log",
            "timestamp": True,
        },
        "inbounds": inbounds,
        "outbounds": [{"type": "direct", "tag": "direct",
                       "tcp_fast_open": True}],
        "route": {"final": "direct",
                  # One catch-all rule whose only job is the UDP
                  # session lifetime: without it, sing-box reaps
                  # sniffed UDP sessions at the protocol defaults
                  # (10 s for dns/ntp/stun, 30 s for quic/dtls) —
                  # the classic "disconnects mid-match, ping was
                  # fine" failure (research 2026-11-21).
                  "rules": [{"action": "route", "outbound": "direct",
                             "udp_timeout": "10m"}]},
    }
    out = os.path.join(ETC, "singbox.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.chmod(out, 0o600)
    print(f"singbox.json written: {len(users)} user(s), port {PORT}"
          + (f", console port {console_port} (no auth, firewall-guarded)"
             if console_port else "")
          + (f", hysteria2 port {hy2_port}" if hy2_port else "")
          + (f", hysteria2-gecko port {gecko_port}" if gecko_port else "")
          + (f", tuic port {tuic_port}" if tuic_port else "")
          + (f", anytls port {anytls_port}" if anytls_port else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

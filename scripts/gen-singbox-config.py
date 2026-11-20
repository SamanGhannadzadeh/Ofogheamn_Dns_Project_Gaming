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
mixed inbound WITHOUT auth is added on that port. It is safe only
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
            "udp_fragment": True,
        }
    ]
    # Optional console inbound (see module docstring): no auth, for
    # PS5/Xbox proxy settings. The firewall guards this port.
    console_file = os.path.join(ETC, "console.json")
    console_port = None
    if os.path.exists(console_file):
        with open(console_file, encoding="utf-8") as fh:
            console_port = int(json.load(fh).get("port", 2081))
        inbounds.append({
            "type": "mixed",
            "tag": "ofogh-console",
            "listen": "::",
            "listen_port": console_port,
            "udp_fragment": True,
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
            "tls": {
                "enabled": True,
                "certificate_path": os.path.join(ETC, "tls", "fullchain.pem"),
                "key_path": os.path.join(ETC, "tls", "privkey.pem"),
            },
        }
        if h.get("obfs_password"):
            hy2["obfs"] = {"type": "salamander",
                           "password": h["obfs_password"]}
        inbounds.append(hy2)
    cfg = {
        "log": {
            "level": "info",
            "output": "/var/log/ofogheamn-dns/singbox.log",
            "timestamp": True,
        },
        "inbounds": inbounds,
        "outbounds": [{"type": "direct", "tag": "direct"}],
        "route": {"final": "direct"},
    }
    out = os.path.join(ETC, "singbox.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.chmod(out, 0o600)
    print(f"singbox.json written: {len(users)} user(s), port {PORT}"
          + (f", console port {console_port} (no auth, firewall-guarded)"
             if console_port else "")
          + (f", hysteria2 port {hy2_port}" if hy2_port else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

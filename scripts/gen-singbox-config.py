#!/usr/bin/env python3
"""Generate the sing-box proxy config from the project's user store.

Single source of truth, used by install.sh, the panel and the CLI.
  users store : /etc/ofogheamn-dns/proxy-users.json  [{"user","pass"}]
  output      : /etc/ofogheamn-dns/singbox.json
The proxy is a "mixed" inbound (HTTP + SOCKS5 on one port, with
SOCKS5 UDP ASSOCIATE for game UDP) and a direct outbound.
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
    cfg = {
        "log": {
            "level": "info",
            "output": "/var/log/ofogheamn-dns/singbox.log",
            "timestamp": True,
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "ofogh-mixed",
                "listen": "::",
                "listen_port": PORT,
                "users": [{"username": u["user"], "password": u["pass"]} for u in users],
                "udp_fragment": True,
            }
        ],
        "outbounds": [{"type": "direct", "tag": "direct"}],
        "route": {"final": "direct"},
    }
    out = os.path.join(ETC, "singbox.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.chmod(out, 0o600)
    print(f"singbox.json written: {len(users)} user(s), port {PORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

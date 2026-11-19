#!/usr/bin/env python3
"""WireGuard peer manager for the Ofogheamn gaming tunnel.

  ofogheamn-wg-peer add <name> [--print]   create a peer, print its client config
  ofogheamn-wg-peer list
  ofogheamn-wg-peer remove <name>

State: /etc/ofogheamn-dns/wg-peers.json + wg0.conf (rewritten).
The server's public endpoint comes from wg-server.conf
(endpoint=..., port=..., server_pubkey derived from the key file).
Client configs route EVERYTHING (0.0.0.0/0) through the server and
use the server itself as DNS — one path for lookups and gameplay.
"""
import json
import os
import subprocess
import sys

ETC = os.environ.get("OFOGH_ETC", "/etc/ofogheamn-dns")
PEERS_FILE = os.path.join(ETC, "wg-peers.json")
CONF = os.path.join(ETC, "wg0.conf")
SERVER_CONF = os.path.join(ETC, "wg-server.conf")


def wg(*args):
    return subprocess.run(["wg"] + list(args), capture_output=True, text=True).stdout.strip()


def load_peers():
    try:
        with open(PEERS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def save_peers(peers):
    with open(PEERS_FILE, "w", encoding="utf-8") as fh:
        json.dump(peers, fh, indent=1)
    os.chmod(PEERS_FILE, 0o600)


def server_cfg():
    cfg = {"port": "51820", "endpoint": "", "address": "10.66.0.1/24"}
    try:
        for line in open(SERVER_CONF, encoding="utf-8"):
            if "=" in line:
                k, v = line.strip().split("=", 1)
                cfg[k.strip()] = v.strip()
    except OSError:
        pass
    key_file = os.path.join(ETC, "wg-server.key")
    priv = open(key_file, encoding="utf-8").read().strip() if os.path.exists(key_file) else ""
    return cfg, priv


def write_conf(peers):
    cfg, priv = server_cfg()
    lines = ["[Interface]",
             f"PrivateKey = {priv}",
             f"ListenPort = {cfg['port']}", ""]
    for p in peers:
        lines += ["[Peer]",
                  f"# {p['name']}",
                  f"PublicKey = {p['pubkey']}",
                  f"AllowedIPs = {p['ip']}/32", ""]
    with open(CONF, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    os.chmod(CONF, 0o600)


def next_ip(peers):
    used = {p["ip"] for p in peers}
    n = 2
    while f"10.66.0.{n}" in used:
        n += 1
    return f"10.66.0.{n}"


def client_config(peer, server_pub):
    cfg, _ = server_cfg()
    endpoint = cfg["endpoint"] or "<server-ip>"
    return f"""[Interface]
PrivateKey = {peer['privkey']}
Address = {peer['ip']}/32
DNS = 10.66.0.1
# MTU hygiene (research 2026-11-19): 1380 is safe for PPPoE home
# lines; on mobile data or double-encapsulated paths drop to 1280.
# A too-large MTU silently fragments game UDP and adds jitter.
MTU = 1380

[Peer]
PublicKey = {server_pub}
Endpoint = {endpoint}:{cfg['port']}
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
"""


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 64
    cmd = sys.argv[1]
    peers = load_peers()
    if cmd == "list":
        for p in peers:
            print(f"{p['name']:20s} {p['ip']}")
        return 0
    if cmd == "add":
        name = sys.argv[2]
        peers = [p for p in peers if p["name"] != name]
        priv = wg("genkey")
        peer = {"name": name, "privkey": priv,
                "pubkey": subprocess.run(["wg", "pubkey"], input=priv,
                                         capture_output=True, text=True).stdout.strip(),
                "ip": next_ip(peers)}
        peers.append(peer)
        save_peers(peers)
        write_conf(peers)
        _cfg, spriv = server_cfg()
        spub = subprocess.run(["wg", "pubkey"], input=spriv,
                              capture_output=True, text=True).stdout.strip()
        print(client_config(peer, spub))
        return 0
    if cmd == "remove":
        name = sys.argv[2]
        peers = [p for p in peers if p["name"] != name]
        save_peers(peers)
        write_conf(peers)
        print(f"removed: {name}")
        return 0
    print(__doc__)
    return 64


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# Ofogheamn Mesh — opt-in node-to-node peering for the lowest total ping.
#
# Model (per the project owner): nodes that BOTH enable mesh measure
#   * their own RTT to a fixed set of game-backend targets, and
#   * their RTT to each other,
# and a node exits through a peer when
#     RTT(node -> peer) + RTT(peer -> targets)  <  RTT(node -> targets)
# The winner becomes the exit for chained DNS (game lists) and,
# optionally, for the WireGuard clients' egress. Re-evaluated every
# minute with 5 ms hysteresis so the exit does not flap.
#
# State:  /etc/ofogheamn-dns/mesh.json     (config, written by the CLI/panel)
#         /run/ofogheamn-mesh-state.json   (live decision, read by the panel)
import json, os, re, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlrequest

CONF = "/etc/ofogheamn-dns/mesh.json"
STATE = "/run/ofogheamn-mesh-state.json"
UPSTREAM_CONF = "/etc/ofogheamn-dns/mesh-upstream.conf"
WG_MESH_CONF = "/etc/ofogheamn-dns/wg-mesh.conf"
LISTS = ["/etc/ofogheamn-dns/lists/cod.domains",
         "/etc/ofogheamn-dns/lists/gaming.domains"]
DEFAULT_TARGETS = ["185.60.112.157", "185.60.114.166", "1.1.1.1", "8.8.8.8"]
HYSTERESIS_MS = 5.0
INTERVAL = 60

def load_conf():
    try:
        with open(CONF) as f:
            c = json.load(f)
    except Exception:
        c = {}
    c.setdefault("enabled", False)
    c.setdefault("key", "")
    c.setdefault("port", 51821)
    c.setdefault("wg_port", 51822)
    c.setdefault("peers", [])
    c.setdefault("targets", DEFAULT_TARGETS)
    c.setdefault("egress", True)
    return c

def ping_ms(host, count=3):
    try:
        out = subprocess.run(["ping", "-c", str(count), "-W", "1", "-q", host],
                             capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"min/avg/max/[^=]*=\s*[\d.]+/([\d.]+)/", out)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    # TCP fallback (ICMP blocked somewhere): time a connect to 443/53.
    import socket
    for port in (443, 53):
        try:
            t0 = time.time()
            s = socket.create_connection((host, port), timeout=2)
            s.close()
            return (time.time() - t0) * 1000.0
        except Exception:
            continue
    return None

def measure(targets):
    out = {}
    for t in targets:
        v = ping_ms(t)
        if v is not None:
            out[t] = round(v, 1)
    return out

def mean(d):
    return sum(d.values()) / len(d) if d else None

def host_of(endpoint):
    return endpoint.rsplit(":", 1)[0].strip("[]")

def fetch_peer_report(peer, conf):
    url = "http://%s:%d/mesh/report" % (host_of(peer["endpoint"]), conf["port"])
    req = urlrequest.Request(url, headers={"X-Mesh-Key": conf["key"]})
    with urlrequest.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())

def decide(my_rtt, peer_infos):
    """peer_infos: {name: {"to_peer": ms|None, "targets": {t: ms}}}.
    Returns (best_name_or_'direct', {name: score})."""
    direct = mean(my_rtt)
    scores = {}
    if direct is not None:
        scores["direct"] = round(direct, 1)
    for name, info in peer_infos.items():
        pt = mean(info.get("targets") or {})
        tp = info.get("to_peer")
        if pt is not None and tp is not None:
            scores[name] = round(tp + pt, 1)
    if not scores:
        return "direct", scores
    best = min(scores, key=scores.get)
    return best, scores

# ---------------------------------------------------------------- apply
def sh(*args):
    subprocess.run(list(args), capture_output=True, text=True, timeout=30)

def apply_dns(best, peers_by_name):
    lines = []
    if best != "direct" and best in peers_by_name:
        p = peers_by_name[best]
        lines.append("# Ofogheamn Mesh: game lists chained via peer %s" % best)
        lines.append("server %s -group mesh" % p["mesh_ip"])
        for lf in LISTS:
            try:
                for raw in open(lf):
                    d = raw.strip()
                    if d and not d.startswith("#"):
                        lines.append("domain-rules /%s/ -nameserver mesh" % d)
            except FileNotFoundError:
                pass
    new = "\n".join(lines) + ("\n" if lines else "")
    old = ""
    try:
        old = open(UPSTREAM_CONF).read()
    except Exception:
        pass
    if new != old:
        with open(UPSTREAM_CONF, "w") as f:
            f.write(new)
        sh("systemctl", "restart", "ofogheamn-dns")

def wg_mesh_up(peer, conf):
    priv = ""
    try:
        priv = open("/etc/ofogheamn-dns/mesh.key").read().strip()
    except Exception:
        pass
    if not priv:
        priv = subprocess.run(["wg", "genkey"], capture_output=True,
                              text=True).stdout.strip()
        with open("/etc/ofogheamn-dns/mesh.key", "w") as f:
            f.write(priv + "\n")
        os.chmod("/etc/ofogheamn-dns/mesh.key", 0o600)
    my_ip = conf.get("mesh_ip", "10.99.0.1")
    conf_txt = ("[Interface]\nPrivateKey = %s\nListenPort = %d\n\n"
                "[Peer]\nPublicKey = %s\nEndpoint = %s\n"
                "AllowedIPs = 0.0.0.0/0\nPersistentKeepalive = 25\n"
                % (priv, conf["wg_port"], peer["pubkey"], peer["endpoint"]))
    with open(WG_MESH_CONF, "w") as f:
        f.write(conf_txt)
    os.chmod(WG_MESH_CONF, 0o600)
    sh("ip", "link", "del", "wg-mesh")
    sh("ip", "link", "add", "wg-mesh", "type", "wireguard")
    sh("wg", "setconf", "wg-mesh", WG_MESH_CONF)
    sh("ip", "address", "add", my_ip + "/24", "dev", "wg-mesh")
    sh("ip", "link", "set", "wg-mesh", "up")
    # client subnets (WireGuard gamers) exit via the mesh when it wins
    sh("ip", "rule", "del", "from", "10.66.0.0/24", "table", "66")
    sh("ip", "rule", "add", "from", "10.66.0.0/24", "table", "66")
    sh("ip", "route", "replace", "default", "dev", "wg-mesh", "table", "66")
    sh("iptables", "-t", "nat", "-C", "POSTROUTING", "-o", "wg-mesh",
       "-j", "MASQUERADE")
    r = subprocess.run(["iptables", "-t", "nat", "-C", "POSTROUTING", "-o",
                        "wg-mesh", "-j", "MASQUERADE"], capture_output=True)
    if r.returncode != 0:
        sh("iptables", "-t", "nat", "-A", "POSTROUTING", "-o", "wg-mesh",
           "-j", "MASQUERADE")

def wg_mesh_down():
    sh("ip", "rule", "del", "from", "10.66.0.0/24", "table", "66")
    sh("ip", "link", "del", "wg-mesh")
    sh("iptables", "-t", "nat", "-D", "POSTROUTING", "-o", "wg-mesh",
       "-j", "MASQUERADE")

# ---------------------------------------------------------------- report server
class ReportHandler(BaseHTTPRequestHandler):
    latest = {}
    conf = {}
    def do_GET(self):
        if self.path != "/mesh/report":
            self.send_response(404); self.end_headers(); return
        if self.headers.get("X-Mesh-Key", "") != self.conf.get("key", ""):
            self.send_response(403); self.end_headers(); return
        body = json.dumps({"node": self.conf.get("node_name", ""),
                           "ts": int(time.time()),
                           "targets": self.latest}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass

def serve_reports(conf):
    ReportHandler.conf = conf
    srv = ThreadingHTTPServer(("0.0.0.0", conf["port"]), ReportHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

# ---------------------------------------------------------------- main loop
def run():
    conf = load_conf()
    if not conf["enabled"]:
        print("mesh disabled in %s" % CONF)
        return
    serve_reports(conf)
    current = "direct"
    while True:
        conf = load_conf()
        if not conf["enabled"]:
            apply_dns("direct", {})
            wg_mesh_down()
            print("mesh disabled; exiting")
            return
        my_rtt = measure(conf["targets"])
        ReportHandler.latest = my_rtt
        peer_infos = {}
        peers_by_name = {}
        for p in conf["peers"]:
            peers_by_name[p["name"]] = p
            to_peer = ping_ms(host_of(p["endpoint"]))
            targets = {}
            try:
                rep = fetch_peer_report(p, conf)
                targets = rep.get("targets") or {}
            except Exception:
                targets = {}
            peer_infos[p["name"]] = {"to_peer": to_peer, "targets": targets}
        best, scores = decide(my_rtt, peer_infos)
        # hysteresis: keep the current exit unless the challenger is
        # at least HYSTERESIS_MS better
        if best != current and current in scores and best in scores:
            if scores[best] > scores[current] - HYSTERESIS_MS:
                best = current
        if best != current:
            apply_dns(best, peers_by_name)
            if conf.get("egress", True):
                if best == "direct":
                    wg_mesh_down()
                else:
                    wg_mesh_up(peers_by_name[best], conf)
            current = best
        state = {"best": current, "scores": scores, "my_rtt": my_rtt,
                 "peers": {k: {"to_peer": v["to_peer"],
                               "targets": v["targets"]}
                           for k, v in peer_infos.items()},
                 "ts": int(time.time())}
        try:
            with open(STATE, "w") as f:
                json.dump(state, f)
        except Exception:
            pass
        time.sleep(INTERVAL)

def selftest():
    my = {"t1": 80.0, "t2": 84.0}                      # direct mean 82
    peers = {"far-but-close-to-game": {"to_peer": 20.0,
             "targets": {"t1": 28.0, "t2": 32.0}},     # via = 20+30 = 50
             "near-but-far-from-game": {"to_peer": 5.0,
             "targets": {"t1": 90.0, "t2": 94.0}}}     # via = 5+92 = 97
    best, scores = decide(my, peers)
    print("scores:", scores)
    print("best:", best)
    assert best == "far-but-close-to-game", best
    assert scores["direct"] == 82.0 and scores["far-but-close-to-game"] == 50.0
    print("MESH_SELFTEST_OK")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        run()

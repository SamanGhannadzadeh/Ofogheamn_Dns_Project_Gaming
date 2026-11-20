#!/usr/bin/env python3
"""Ofogheamn node health check — is this node actually healthy?

Checks, in order:
  1. The DNS service answers a real query on 127.0.0.1:53.
  2. Core services are active (dns / proxy / panel / wg / mesh).
  3. The TLS certificate (DoT/DoH) is not expired or near expiry.
  4. Disk and load are sane.
  5. Every configured upstream still answers (a silently dead
     upstream — a stale mesh peer, a filtered provider — used to
     cost each cold lookup a full timeout before anyone noticed;
     live-node incident, 2026-11-20). QUIC/H3 upstreams are
     counted but not probed (no plain-DNS probe exists for them).

With --fix, a failed query check restarts the DNS service once.
Exit code 0 = healthy, 1 = something needs attention.
"""
import json
import os
import socket
import ssl
import struct
import subprocess
import sys
import time

SERVICES = {
    "dns": "ofogheamn-dns",
    "proxy": "ofogheamn-proxy",
    "panel": "ofogheamn-panel",
    "wg": "ofogheamn-wg",
    "mesh": "ofogheamn-mesh",
    "vpn": "ofogheamn-vpn",
}
CERT = "/etc/ofogheamn-dns/tls/fullchain.pem"


def raw_a_query(host, timeout=3.0):
    """Send one raw A query for example.com to host:53 (UDP)."""
    tid = 0x0F0A
    pkt = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    for part in b"example.com".split(b"."):
        pkt += bytes([len(part)]) + part
    pkt += b"\x00" + struct.pack(">HH", 1, 1)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        t0 = time.time()
        s.sendto(pkt, (host, 53))
        data, _ = s.recvfrom(4096)
        ms = (time.time() - t0) * 1000
        rid, flags, qd, an = struct.unpack(">HHHH", data[:8])
        return rid == tid and an >= 1, round(ms, 1)
    except OSError:
        return False, None


def dns_query_ok(timeout=3.0):
    return raw_a_query("127.0.0.1", timeout)


def tcp_open(host, port, timeout=2.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def upstream_probe(conf="/etc/ofogheamn-dns/smartdns.conf", timeout=2.0):
    """Probe every upstream in smartdns.conf; return (dead, probed).

    plain server  -> real UDP query; server-tls -> TCP :853;
    server-https  -> TCP :443 to the URL host. QUIC/H3 upstreams
    are skipped (no plain probe exists). Report-only: a dead
    upstream is flagged, never auto-removed.
    """
    dead, probed = [], 0
    try:
        lines = open(conf, encoding="utf-8").read().splitlines()
    except OSError:
        return dead, probed
    for line in lines:
        parts = line.split()
        if len(parts) < 2 or line.lstrip().startswith("#"):
            continue
        kind, target = parts[0], parts[1]
        if kind == "server":
            probed += 1
            if not raw_a_query(target, timeout)[0]:
                dead.append(target)
        elif kind == "server-tls":
            probed += 1
            if not tcp_open(target, 853, timeout):
                dead.append(target + ":853")
        elif kind == "server-https":
            host = target.split("/")[2] if "://" in target else target
            probed += 1
            if not tcp_open(host, 443, timeout):
                dead.append(host + ":443")
    return list(dict.fromkeys(dead)), probed


def svc_state(unit):
    r = subprocess.run(["systemctl", "is-active", unit],
                       capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def cert_days():
    if not os.path.exists(CERT):
        return None
    try:
        import datetime
        info = ssl._ssl._test_decode_cert(CERT)
        exp = datetime.datetime.strptime(
            info["notAfter"], "%b %d %H:%M:%S %Y %Z")
        return (exp - datetime.datetime.utcnow()).days
    except Exception:
        return None


def main():
    fix = "--fix" in sys.argv
    as_json = "--json" in sys.argv
    problems = []

    ok, ms = dns_query_ok()
    if not ok and fix:
        subprocess.run(["systemctl", "restart", SERVICES["dns"]])
        time.sleep(2)
        ok, ms = dns_query_ok()
    if not ok:
        problems.append("dns-no-answer")

    states = {k: svc_state(v) for k, v in SERVICES.items()}
    # mesh/wg may legitimately be off (opt-in features); only the
    # core services are health-critical. The core set is adaptive:
    # a Lite node has no panel (no panel.conf) and a node whose
    # sing-box download failed has no proxy — both used to report
    # permanently "unhealthy" for a service that was never meant
    # to run there (v1.4 fix).
    core = ["dns"]
    if os.path.exists("/usr/local/bin/sing-box"):
        core.append("proxy")
    if os.path.exists("/etc/ofogheamn-dns/panel.conf"):
        core.append("panel")
    for name in core:
        if states[name] not in ("active",):
            problems.append(f"{name}-{states[name]}")

    days = cert_days()
    if days is not None and days < 14:
        problems.append(f"cert-{days}d")

    try:
        st = os.statvfs("/")
        disk_free_gb = round(st.f_bavail * st.f_frsize / 1e9, 1)
        if disk_free_gb < 1:
            problems.append("disk-low")
    except OSError:
        disk_free_gb = None
    load1 = round(os.getloadavg()[0], 2)

    dead_upstreams, probed_upstreams = upstream_probe()
    for target in dead_upstreams:
        problems.append(f"upstream-dead-{target}")

    # Local listeners: a service can report "active" while its
    # port is wedged or taken. Adaptive like the core set above —
    # only ports this node is configured to serve are checked.
    listen_ports = [853, 443]
    if os.path.exists("/usr/local/bin/sing-box"):
        listen_ports.append(2080)
    if os.path.exists("/etc/ofogheamn-dns/panel.conf"):
        listen_ports.append(8080)
    console_file = "/etc/ofogheamn-dns/console.json"
    if os.path.exists(console_file):
        try:
            with open(console_file) as fh:
                listen_ports.append(int(json.load(fh)["port"]))
        except (OSError, ValueError, KeyError):
            problems.append("console-config-bad")
    # AnyTLS is the only opt-in TCP transport; TUIC and Hysteria2
    # are UDP and cannot be probed this way (the proxy unit state
    # above covers them).
    anytls_file = "/etc/ofogheamn-dns/anytls.json"
    if os.path.exists(anytls_file):
        try:
            with open(anytls_file) as fh:
                listen_ports.append(int(json.load(fh)["port"]))
        except (OSError, ValueError, KeyError):
            problems.append("anytls-config-bad")
    for port in listen_ports:
        if not tcp_open("127.0.0.1", port, timeout=1.0):
            problems.append(f"port-closed-{port}")

    healthy = not problems
    report = {
        "healthy": healthy,
        "problems": problems,
        "dns_answer_ms": ms,
        "services": states,
        "cert_days_left": days,
        "disk_free_gb": disk_free_gb,
        "load1": load1,
        "upstreams_dead": dead_upstreams,
        "upstreams_probed": probed_upstreams,
    }
    if as_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print("وضعیت نود افق امن")
        print(f"  پاسخ DNS: {'سالم' if ok else 'بی‌پاسخ'}"
              + (f' ({ms} ms)' if ms is not None else ''))
        for k, v in states.items():
            print(f"  سرویس {k}: {v}")
        if days is not None:
            print(f"  گواهی TLS: {days} روز مانده")
        print(f"  دیسک آزاد: {disk_free_gb} GB · بار: {load1}")
        if dead_upstreams:
            print("  آپ‌استریم‌های مرده: " + ", ".join(dead_upstreams))
        else:
            print(f"  آپ‌استریم‌ها: هر {probed_upstreams} مورد زنده")
        print("نتیجه: " + ("سالم ✓" if healthy
                            else "نیازمند توجه: " + ", ".join(problems)))
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())

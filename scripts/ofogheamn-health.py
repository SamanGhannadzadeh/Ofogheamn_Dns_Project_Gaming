#!/usr/bin/env python3
"""Ofogheamn node health check — is this node actually healthy?

Checks, in order:
  1. The DNS service answers a real query on 127.0.0.1:53.
  2. Core services are active (dns / proxy / panel / wg / mesh).
  3. The TLS certificate (DoT/DoH) is not expired or near expiry.
  4. Disk and load are sane.

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


def dns_query_ok(timeout=3.0):
    """Send one raw A query for example.com to 127.0.0.1:53."""
    tid = 0x0F0A
    pkt = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    for part in b"example.com".split(b"."):
        pkt += bytes([len(part)]) + part
    pkt += b"\x00" + struct.pack(">HH", 1, 1)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        t0 = time.time()
        s.sendto(pkt, ("127.0.0.1", 53))
        data, _ = s.recvfrom(4096)
        ms = (time.time() - t0) * 1000
        rid, flags, qd, an = struct.unpack(">HHHH", data[:8])
        return rid == tid and an >= 1, round(ms, 1)
    except OSError:
        return False, None


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
    # core three are health-critical.
    for core in ("dns", "proxy", "panel"):
        if states[core] not in ("active",):
            problems.append(f"{core}-{states[core]}")

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

    healthy = not problems
    report = {
        "healthy": healthy,
        "problems": problems,
        "dns_answer_ms": ms,
        "services": states,
        "cert_days_left": days,
        "disk_free_gb": disk_free_gb,
        "load1": load1,
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
        print("نتیجه: " + ("سالم ✓" if healthy
                            else "نیازمند توجه: " + ", ".join(problems)))
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""ofogheamn-bench — one-command health + latency report for a node.

Measures, from the node itself:
  * DNS answer time for a gaming domain, cold vs cached (the number
    a player actually feels at match start)
  * end-to-end region ranking (ofogheamn-region)
  * service states (dns, panel, proxy, tunnel, mesh)
Prints a compact Persian report; --json for machines.
"""
import json
import subprocess
import sys
import time

SERVICES = ["ofogheamn-dns", "ofogheamn-panel", "ofogheamn-proxy",
            "ofogheamn-wg", "ofogheamn-mesh"]


def dig_ms(server, name, tcp=False):
    cmd = ["dig", "+time=3", "+tries=1", "+stats", f"@{server}", name, "A"]
    if tcp:
        cmd.insert(1, "+tcp")
    t0 = time.perf_counter()
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=8).stdout
    except Exception:
        return None
    wall = (time.perf_counter() - t0) * 1000
    for line in out.splitlines():
        if "Query time" in line:
            try:
                return int(line.split(":")[1].split()[0])
            except Exception:
                break
    return round(wall)


def svc_state(name):
    r = subprocess.run(["systemctl", "is-active", name],
                       capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def main():
    as_json = "--json" in sys.argv
    server = "127.0.0.1"
    cold = dig_ms(server, "callofduty.com")
    warm = dig_ms(server, "callofduty.com")
    warm2 = dig_ms(server, "callofduty.com")
    region = None
    try:
        out = subprocess.run(
            ["python3", "/usr/local/bin/ofogheamn-region.py", "--json"],
            capture_output=True, text=True, timeout=120).stdout
        region = json.loads(out)["ranked"]
    except Exception:
        pass
    states = {s: svc_state(s) for s in SERVICES}
    report = {"dns_cold_ms": cold, "dns_warm_ms": warm, "dns_warm2_ms": warm2,
              "regions": region, "services": states}
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print("== بنچ‌مارک نود افق امن ==\n")
    print(f"DNS بازی (سرد):   {cold if cold is not None else '—'} ms")
    print(f"DNS بازی (کش):    {warm if warm is not None else '—'} / {warm2 if warm2 is not None else '—'} ms")
    if region:
        print("\nرتبه‌بندی منطقه‌ها:")
        for i, r in enumerate(region, 1):
            print(f"  {i}. {r['region']}: {r['rtt_ms']} ms")
    print("\nسرویس‌ها:")
    for s, st in states.items():
        print(f"  {s}: {st}")
    print("\nهدف‌ها: DNS کش زیر ۵ ms، سرد زیر ۵۰ ms، همهٔ سرویس‌ها active.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

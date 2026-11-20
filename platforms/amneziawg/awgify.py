#!/usr/bin/env python3
"""awgify — convert a WireGuard config into an AmneziaWG one.

AmneziaWG hides WireGuard's fixed packet signature (the thing
DPI fingerprints in one packet) behind junk packets before the
handshake and randomised magic header values. The parameters
below MUST be identical on both ends of the tunnel or nothing
connects — so generate them once, save them, and apply the
same set to the peer config:

    awgify.py server.conf --write-params awg-params.json > awg0.conf
    awgify.py client.conf --params awg-params.json > client-awg.conf

Experimental: see README.fa.md in this folder for the status
and the kernel/tools requirements. Spec: AmneziaWG 2.0
(Jc/Jmin/Jmax junk packets, S1/S2 padding, H1-H4 magic header
ranges).
"""
import argparse
import json
import random
import sys

DEFAULTS = {"Jc": 4, "Jmin": 40, "Jmax": 70, "S1": 15, "S2": 18}
KEYS = list(DEFAULTS) + ["H1", "H2", "H3", "H4"]


def gen_params(rng):
    params = dict(DEFAULTS)
    lo = rng.randrange(1000, 900_000)
    for i in range(1, 5):
        hi = lo + rng.randrange(1000, 100_000)
        params[f"H{i}"] = f"{lo}-{hi}"
        lo = hi + rng.randrange(1000, 100_000)
    return params


def apply_params(text, params):
    out = []
    in_iface = False
    inserted = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            if in_iface and not inserted:
                out.extend(f"{k} = {params[k]}" for k in KEYS)
                inserted = True
            in_iface = stripped.lower() == "[interface]"
            out.append(line)
            continue
        if in_iface and any(
            stripped.startswith(k + " ") or stripped.startswith(k + "=")
            for k in KEYS
        ):
            continue  # stale managed field; the block is re-added
        out.append(line)
    if in_iface and not inserted:
        out.extend(f"{k} = {params[k]}" for k in KEYS)
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description="WireGuard -> AmneziaWG config converter")
    ap.add_argument("config", help="input WireGuard .conf")
    ap.add_argument("--params", help="reuse a saved parameter set (JSON)")
    ap.add_argument("--write-params", help="save the generated parameter set (JSON)")
    args = ap.parse_args()

    if args.params:
        with open(args.params, encoding="utf-8") as fh:
            params = json.load(fh)
    else:
        params = gen_params(random.SystemRandom())
        if args.write_params:
            with open(args.write_params, "w", encoding="utf-8") as fh:
                json.dump(params, fh, indent=2)
    with open(args.config, encoding="utf-8") as fh:
        text = fh.read()
    sys.stdout.write(apply_params(text, params))
    print("awgify: both ends MUST use identical parameters — "
          "share the params file, not just the idea.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

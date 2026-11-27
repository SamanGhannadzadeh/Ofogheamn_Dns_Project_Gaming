#!/usr/bin/env python3
"""Admin CLI for the IP registration panel.

  ofogh-reg-admin.py add LABEL      -> prints a fresh code
  ofogh-reg-admin.py list           -> labels, codes' state, IPs
  ofogh-reg-admin.py revoke LABEL   -> drops the code and its IP
"""
import hashlib
import json
import os
import secrets
import string
import subprocess
import sys
import time

ETC = "/etc/ofogheamn-dns"
CODES = os.path.join(ETC, "reg-codes.json")
STATE = os.path.join(ETC, "reg-state.json")
ALLOW = os.path.join(ETC, "allowlist.txt")
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no look-alikes


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def apply_firewall():
    subprocess.run(["systemctl", "restart", "ofogheamn-firewall.service"],
                   timeout=30, capture_output=True)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    codes = load(CODES)
    state = load(STATE)
    if cmd == "add" and len(argv) == 3:
        label = argv[2]
        code = "".join(secrets.choice(ALPHABET) for _ in range(10))
        codes[hashlib.sha256(code.encode()).hexdigest()] = {
            "label": label, "created": int(time.time())}
        save(CODES, codes)
        print(code)
        return 0
    if cmd == "list":
        for h, v in sorted(codes.items(), key=lambda kv: kv[1].get("label", "")):
            cur = (state.get(h) or {}).get("ip", "-")
            print("%-24s ip=%s" % (v.get("label", "?"), cur))
        return 0
    if cmd == "revoke" and len(argv) == 3:
        label = argv[2]
        hit = [h for h, v in codes.items() if v.get("label") == label]
        if not hit:
            print("no such label", file=sys.stderr)
            return 1
        for h in hit:
            ip = (state.pop(h, None) or {}).get("ip")
            codes.pop(h, None)
            if ip and os.path.exists(ALLOW):
                with open(ALLOW) as f:
                    lines = [ln.strip() for ln in f if ln.strip()]
                if ip in lines:
                    lines.remove(ip)
                    with open(ALLOW, "w") as f:
                        f.write("\n".join(lines) + "\n")
        save(CODES, codes)
        save(STATE, state)
        apply_firewall()
        print("revoked", label)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

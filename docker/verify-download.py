#!/usr/bin/env python3
"""Build-time download integrity for the Docker image.

Same policy as install.sh's verify_digest: compare the file's
SHA-256 with the digest GitHub records for the release asset.
API unreachable -> warn and continue; a KNOWN mismatch -> exit 1.

Usage: verify-download.py <owner/repo> <tag> <asset> <file>
"""
import hashlib
import json
import sys
import urllib.request

repo, tag, asset, path = sys.argv[1:5]
want = ""
try:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
        headers={"User-Agent": "ofogheamn-docker-build"})
    with urllib.request.urlopen(req, timeout=30) as fh:
        rel = json.load(fh)
    for a in rel.get("assets", []):
        if a.get("name") == asset:
            want = (a.get("digest") or "").replace("sha256:", "")
            break
except Exception:
    want = ""
if not want:
    print(f"WARNING: could not fetch the official digest for {asset}; "
          "building unverified")
    sys.exit(0)
got = hashlib.sha256(open(path, "rb").read()).hexdigest()
if got != want:
    print(f"SECURITY ABORT: sha256 mismatch for {asset} "
          f"(got {got}, want {want})", file=sys.stderr)
    sys.exit(1)
print(f"digest verified: {asset}")

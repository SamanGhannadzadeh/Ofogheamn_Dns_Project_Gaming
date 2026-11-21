#!/usr/bin/env python3
"""update-dc-ranges — rebuild lists/datacenter-ranges.txt from the
official AWS + Google Cloud + Microsoft Azure IP feeds, aggregated
to the smallest CIDR set. Used by ofogheamn-qos for DSCP marking of
game-backend traffic (PSN rides AWS, Xbox rides Azure, CoD rides
both). Refuses to overwrite the file when the feeds look broken
(<1000 prefixes collected)."""
import ipaddress
import json
import re
import sys
import urllib.request

OUT = "/etc/ofogheamn-dns/lists/datacenter-ranges.txt"


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "ofogheamn-dns"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def main():
    nets = []
    try:
        d = json.loads(fetch("https://ip-ranges.amazonaws.com/ip-ranges.json"))
        nets += [p["ip_prefix"] for p in d["prefixes"]]
        print("aws ok")
    except Exception as e:  # noqa: BLE001
        print("aws fail:", e)
    try:
        d = json.loads(fetch("https://www.gstatic.com/ipranges/cloud.json"))
        nets += [p["ipv4Prefix"] for p in d["prefixes"] if "ipv4Prefix" in p]
        print("gcp ok")
    except Exception as e:  # noqa: BLE001
        print("gcp fail:", e)
    try:
        html = fetch(
            "https://www.microsoft.com/en-us/download/details.aspx?id=56519"
        ).decode()
        m = re.search(
            r"https://download\.microsoft\.com/download/[^\"]*ServiceTags_Public_\d+\.json",
            html,
        )
        d = json.loads(fetch(m.group(0)))
        for v in d["values"]:
            nets += [
                p
                for p in v["properties"].get("addressPrefixes", [])
                if ":" not in p
            ]
        print("azure ok")
    except Exception as e:  # noqa: BLE001
        print("azure fail:", e)
    if len(nets) < 1000:
        print(f"only {len(nets)} prefixes collected — keeping old file")
        return 1
    agg = list(
        ipaddress.collapse_addresses(
            [ipaddress.ip_network(n, strict=False) for n in nets]
        )
    )
    with open(OUT, "w") as fh:
        fh.write("# aggregated official AWS+GCP+Azure feeds\n")
        fh.write("\n".join(str(a) for a in agg) + "\n")
    print(f"wrote {len(agg)} ranges to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

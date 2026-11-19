#!/usr/bin/env python3
"""ofogheamn-region — end-to-end region probe + per-title advisory.

The single biggest latency lever for Iranian gamers (research,
2026-11-19) is choosing the right region by measuring the FULL path
— node -> game server — not just client -> node. This tool runs ON
the node: it measures TCP RTT to representative regional endpoints,
ranks the regions, and prints per-title advice.

Endpoints are *representative* (public AWS regional service
endpoints), not the game servers themselves; matchmaking placement
is server-side and no probe can move it. Use the ranking to pick
where to rent/point a node, and which in-game region to select.

  ofogheamn-region.py           human table + advice
  ofogheamn-region.py --json    machine-readable (panel/mesh)
"""
import json
import socket
import statistics
import sys
import time

REGIONS = [
    # (region, representative endpoint, note)
    ("فرانکفورت (EU-Central)", "dynamodb.eu-central-1.amazonaws.com",
     "هاب اصلی ترانزیت ایران؛ بیشتر سرورهای بازی اروپا هم اینجایند"),
    ("ایرلند (EU-West)", "dynamodb.eu-west-1.amazonaws.com",
     "معمولاً چند میلی‌ثانیه بدتر از فرانکفورت برای ایران"),
    ("بحرین (ME-South)", "dynamodb.me-south-1.amazonaws.com",
     "میزبان تاریخی کالاف و والورانت خاورمیانه"),
    ("امارات (ME-Central)", "dynamodb.me-central-1.amazonaws.com",
     "نزدیک‌ترین از نظر جغرافیا؛ فقط وقتی خوب است که مسیر ترومبون نشود"),
]

TITLES = [
    ("CS2", "سرویس SDR خاورمیانه (دوبی/فجیره) را امتحان کن؛ اگر پینگش از فرانکفورت بدتر بود، اروپا (فرانکفورت) را انتخاب کن — از داخل ایران هر دو را باید اندازه گرفت."),
    ("Valorant", "شارد اروپا: بحرین و استانبول گزینه‌های خاورمیانه‌اند؛ انتخاب را با پینگ داخل بازی بسنج، نه با فاصلهٔ روی نقشه."),
    ("Call of Duty / Warzone", "مچ‌میکینگ سرورساید است (Delta Ping) و DNS جابه‌جایش نمی‌کند؛ منطقه‌ای را انتخاب کن که این ابزار کمترین پینگ دوسویه را برایش نشان می‌دهد (تاریخی: بحرین)."),
    ("Apex / Fortnite / Rocket League", "سرورهای خاورمیانه (بحرین/امارات) روی کاغذ نزدیک‌ترند، ولی مسیر ایران گاهی از فرانکفورت رد می‌شود؛ رتبه‌بندی بالا ملاک است."),
]


def probe(host, port=443, tries=3):
    samples = []
    for _ in range(tries):
        t0 = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=3):
                samples.append((time.perf_counter() - t0) * 1000)
        except OSError:
            pass
        time.sleep(0.15)
    return round(statistics.median(samples), 1) if samples else None


def main():
    as_json = "--json" in sys.argv
    results = []
    for name, host, note in REGIONS:
        results.append({"region": name, "endpoint": host,
                        "rtt_ms": probe(host), "note": note})
    results.sort(key=lambda r: (r["rtt_ms"] is None, r["rtt_ms"] or 1e9))
    if as_json:
        print(json.dumps({"ranked": results,
                          "titles": [{"title": t, "advice": a} for t, a in TITLES]},
                         ensure_ascii=False, indent=2))
        return 0
    print("رتبه‌بندی منطقه‌ها از این نود (پینگ دوسویه تا نقطهٔ نماینده):\n")
    for i, r in enumerate(results, 1):
        rtt = f"{r['rtt_ms']} ms" if r["rtt_ms"] is not None else "نرسید"
        print(f"  {i}. {r['region']}: {rtt}")
        print(f"     {r['note']}")
    best = results[0]
    if best["rtt_ms"] is not None:
        print(f"\nپیشنهاد این نود: {best['region']}")
    print("\nمشاوره بر اساس بازی:")
    for t, a in TITLES:
        print(f"  • {t}: {a}")
    print("\nیادآوری رک: این اعداد نقطهٔ نماینده‌اند، نه سرور بازی؛ "
          "و وسط مسابقه هیچ DNSای پینگ را عوض نمی‌کند.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

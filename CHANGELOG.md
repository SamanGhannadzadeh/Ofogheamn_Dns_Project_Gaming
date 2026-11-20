## v1.3 — 2026-11-20 (L2TP/IPsec + PPTP VPN servers)

- **L2TP/IPsec server** (strongSwan IKEv1/PSK + xl2tpd + ppp) and
  **PPTP server** (pptpd, MPPE-128 required) on every node — for
  devices with no WireGuard app: native clients on Windows,
  Android, iOS/macOS (L2TP) and routers. Same exit model as the
  WireGuard tunnel: clients are NATed out of the node and get the
  node's own SmartDNS pushed over PPP (pools 10.67.0.0/24 and
  10.68.0.0/24).
- Credentials live in ONE place, `/etc/ofogheamn-dns/vpn.conf`;
  `ofogheamn-vpn-setup` renders chap-secrets + ipsec.secrets from
  it on every start. Shipped defaults (ofogh / ofogh1234 /
  PSK ofogheamn) are public — the installer banner, the panel VPN
  tab and docs/VPN.fa.md all warn loudly to change them
  (`ofogheamn-dns vpn set-user / set-pass / set-psk`).
- Firewall: UDP 500/4500/1701 + ESP for IPsec, TCP 1723 + GRE for
  PPTP in `ofogheamn-firewall` (+ ufw when active); MSS clamping
  extended from wg0 to ppp+ interfaces.
- Panel: new VPN tab (service state, PSK/user/ports, restart) and a
  dashboard card; health report now includes the VPN service.

## v1.2.1 — 2026-11-20 (startup robustness)

- Ship `config/mesh-upstream.conf` (comment-only placeholder) and
  install it explicitly: `smartdns.conf` includes this file and
  SmartDNS refuses to start when an included file is missing.
  Found by running the real SmartDNS binary against the full
  production config — it now parses and runs clean end-to-end.

## v1.2 — 2026-11-19 (health + operator tooling)

- **Node health watchdog**: `ofogheamn-dns health`
  (`ofogheamn-health.py`) — real DNS answer probe, service states,
  TLS expiry, disk/load; a systemd timer runs it every 5 minutes
  and restarts the DNS service once if it stops answering.
- **Panel parity**: the dashboard now shows node health, local
  DNS answer time and TLS days left (`/api/health`, cached 60 s).
- **Backup / restore**: `ofogheamn-dns backup` writes a 0600
  tarball of the whole node config to /var/backups;
  `restore <file>` brings it back.
- **Operator checklist**: docs/OPERATOR.fa.md.

# تغییرات

## ۱٫۱ — ۱۹ نوامبر ۲۰۲۶ (ارتقای پژوهشی)

بر پایهٔ پژوهش عمیق «قابلیت‌های کاهش پینگ برای اینترنت ایران» —
هر ۱۱ یافته پیاده شد:

- **سنجش دوسویهٔ منطقه** (`ofogheamn-dns region`): نود پینگ خودش تا
  منطقه‌های بازی را رتبه‌بندی می‌کند + مشاوره بر اساس بازی.
- **نردبان ترنسپورت**: ورودی VLESS+REALITY روی نود
  (`ofogheamn-dns reality enable`) + قالب کلاینت sing-box با انتخاب
  خودکار (REALITY ← Hysteria2 ← WireGuard) — docs/LADDER.fa.md
- **بنچ‌مارک یک‌دستوری** (`ofogheamn-dns bench`): DNS سرد/کش،
  رتبه‌بندی منطقه، وضعیت سرویس‌ها.
- **یکپارچگی دانلود**: باینری‌های SmartDNS و sing-box پیش از نصب با
  دیجست رسمی SHA-256 گیت‌هاب تطبیق داده می‌شوند؛ مغایرت = توقف نصب.
- **راهنمای SQM/CAKE** روتر خانه (docs/SQM.fa.md) — بزرگ‌ترین کاهش
  پینگ سمت خانه.
- **بهداشت MTU/MSS**: MTU ‏۱۳۸۰ در کانفیگ پییرهای WireGuard +
  کلمپ MSS روی فوروارد تونل.
- **DoQ/DoH3** به گروه پیش‌فرض آپ‌استریم اضافه شد (از نودِ خارجی
  سالم است و زیر اتلاف برنده است؛ همیشه کنار DoT/DoH مسابقه می‌دهد).
- **راهنمای انتخاب VPS** با روش اندازه‌گیری (docs/VPS.fa.md).
- طرح split-ECS به‌صورت نقشهٔ اختیاریِ خاموش
  (config/ecs-split.conf.example) و سند صادقانهٔ «چرا رلهٔ داخلی
  نساختیم» (docs/RELAY-EXPERIMENTAL.fa.md).

## ۱٫۰ — ۱۹ نوامبر ۲۰۲۶

انتشار عمومی نخست: هستهٔ SmartDNS با انتخاب سریع‌ترین IP و کش
Match-Ready کالاف، پنل فارسی، پروکسی sing-box، تونل WireGuard،
مش نودها، حالت عمومی/خصوصی با اجبار عبور DNS، نسخه‌های
ویندوز/مک (AdGuard Home) و Lite.

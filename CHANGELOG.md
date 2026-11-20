## v1.5 — 2026-11-20 (verification hardening)

A fresh audit of every installer and entry point, hunting the
same bug classes the v1.4 round fixed. Two real findings, both
in download-digest verification; everything else re-checked
clean (install/uninstall file symmetry is exact, VPN defaults
printed by the installer match `config/vpn.conf`, the OpenWrt /
Docker / Windows installers hold all their v1.4 fixes).

### Fixes
- **A failed digest lookup could kill the installer.**
  `verify_digest` fetches the official SHA-256 from the GitHub
  API; when the API is unreachable or rate-limited (HTTP 403 is
  routine for unauthenticated calls), `curl -f` fails — and
  under `set -e` + `pipefail` that failure propagated out of
  the `want=$(...)` assignment and terminated the install
  silently, instead of reaching the documented "warn loudly
  and continue" path. Proven by isolation test (exit 22, no
  output). The lookup is now failure-tolerant (`|| true`) in
  all three bash copies — `install.sh`, the macOS installer
  and the `ofogheamn-dns` CLI updater — and all three outcomes
  are test-proven: API failure → warning + install continues;
  digest match → verified; digest mismatch → SECURITY ABORT.
  (The Windows `Test-Digest` and Docker `verify-download.py`
  already handled this correctly in their own idioms.)
- **macOS installer verified nothing.** It downloaded
  AdGuard Home and sing-box with no digest check at all —
  the last installer still outside the project policy that
  every fetched binary is verified (Linux/Windows/Docker
  since v1.4). It now runs the same `verify_digest` as the
  Linux installer (via the macOS-native `shasum -a 256`).

### Tests
- `tests/static-test.sh`: 52 → **57 checks**, all passing.
  New: macOS verifies both downloads; all three bash
  `verify_digest` copies tolerate API failure.

## v1.4 — 2026-11-20 (debug + polish round)

Every installer and entry point audited as a first-time user
hits it; bugs proven against the real SmartDNS binary where
possible; a regression suite added so this bug class stays
fixed (`tests/static-test.sh`, 52 checks, incl. running the
shipped config on the real core). (v1.3.1/v1.3.2 were the two
Windows first-run fixes, shipped the same day.)

### Critical fixes (first-run killers)
- **install.sh crashed mid-install on fresh servers.**
  `PUBIP` was first computed *after* the WireGuard block that
  uses it — under `set -u` the install died with "PUBIP:
  unbound variable" on any machine with WireGuard available.
  The public IP is now resolved once, before first use.
- **The managed blocklist blocked nothing.** The generator
  emitted `address /domain/` (empty answer form); proven
  against the real SmartDNS binary: the empty form is parsed
  but never answered locally, so ~90k rules were a no-op. The
  generator now emits `address /domain/#`, the only form that
  answers locally (NXDOMAIN, zero answers). Existing nodes pick
  this up on the next blocklist update.
- **Public-mode firewall rule was inverted.** The hashlimit
  rule targeted DROP; `--hashlimit` matches traffic *at or
  below* the limit, so the node dropped every well-behaved
  client and passed floods. Under-limit traffic now RETURNs
  and only the excess is dropped.
- **Docker nodes could never start.** `smartdns.conf` includes
  `mesh-upstream.conf`; a missing include is fatal (proven),
  and the entrypoint never seeded it. It does now. The image
  build also verifies both binary downloads against GitHub's
  recorded SHA-256 digests now, like every other installer.
- **OpenWrt nodes could never start.** The installer never
  downloaded `mesh-upstream.conf` (same fatal include) and
  never created the TLS certificates (missing certs are also
  fatal — SmartDNS does not auto-generate them). Both are now
  provided; the stock `smartdns` UCI service is disabled so it
  stops fighting the project instance for port 53, and the
  DHCP-advertised DNS is the router's real LAN address instead
  of a hardcoded 192.168.1.1.
- **gateway/redirect-53.sh added no rules at all.** Its `add`
  helper ran the existence-check argv on the append path (no
  `-A`), so every rule failed and the script died under
  `set -e`. Fixed and verified with a stub iptables.
- **macOS installer looked for its templates one directory too
  high** (`REPO_ROOT` `../../..` — the Windows v1.3.1 bug,
  twin copy) and died on first run. Now `../..`.
- **Windows installer printed a proxy password that did not
  work.** Every run minted a new password but only wrote
  `proxy.json` when missing — a re-run printed a password that
  was not the stored one. The password is now generated and
  printed only when the file is created, like the Linux
  installer. Also: TLS 1.2 is pinned for downloads (PS 5.1 on
  older .NET failed every GitHub download), generated
  JSON/YAML is written BOM-free (PS 5.1's UTF8 BOM breaks Go
  parsers), downloads are digest-verified like the Linux
  installer, and a missing project template fails with a clear
  message instead of a raw `Get-Content` crash.
  `uninstall.ps1` no longer errors when the install folder is
  already gone.

### First-run feedback (installers verify themselves)
- **Linux install.sh** replaces the bare `dig` probe with a
  per-service PASS/FAIL self-test, a real DNS answer check,
  and an explicit `SELF-TEST: PASS/FAIL` verdict; the banner
  no longer claims "is up" when the test failed, and the
  common port-53 cause (systemd-resolved) is hinted.
- **Windows and macOS installers** gained the same treatment:
  service state, a live DNS answer, and the proxy port are
  checked and reported instead of an unconditional "DONE".

### Panel / CLI / health
- **Panel proxy edits silently dropped REALITY.** Saving proxy
  settings from the panel rewrote `singbox.json` by hand and
  lost the VLESS+REALITY inbound enabled via the CLI. The
  panel now regenerates through `gen-singbox-config.py`, the
  documented single source of truth.
- **Panel hijack API** misclassified IPv6 targets starting with
  a hex letter (or `::`) as hostnames and wrote corrupt cname
  rules; classification now parses the target as an IP.
- **CLI `update`** downloaded the amd64 sing-box build on ARM
  nodes (now arch-aware, like install.sh), verified no
  digests (now verified, like install.sh), and could proceed
  with an empty release tag. `logs proxy` tailed a log file
  that never exists (now `singbox.log`). Status output no
  longer prints `unknown` under `inactive` or `0\n0` counts.
  Missing arguments to `panel-password`, `proxy add/del-user`
  and `wg add/del-peer` print usage instead of a raw
  "unbound variable" crash.
- **Health check** no longer counts the panel (or proxy) as
  core on nodes that never had one — Lite installs showed a
  permanently "unhealthy" panel and the watchdog restarted
  healthy services every 5 minutes.
- **cod-warmup** could print `0\n0` as the gaming-domain total
  on an all-comments list file.

### Uninstall completeness (Linux)
- Removes two orphans: `update-blocklist` (never removed) and
  `ofogheamn-wg-peer` (the list used a `.py` name that was
  never installed). Disables `ofogheamn-wg`, `ofogheamn-mesh`
  and `ofogheamn-blocklist.timer` before deleting their units
  (dangling wants symlinks), drops the `wg0` interface, removes
  the ufw openings the installer added, and removes the
  rendered VPN credential files (`/etc/ipsec.secrets`, and
  `chap-secrets` only when it carries our rendered header).

### Docs aligned with the code
- Root README: Prefetch is off by design (the CoD warmer is
  the prefetch) and ECS is off by default — both bullets said
  the opposite of the shipped config.
- Windows/macOS READMEs + macOS banner claimed "DoT on 853";
  the AdGuard Home editions serve no DoT until a certificate
  is configured in AGH's Encryption settings. macOS README's
  uninstall path pointed at a nonexistent `server/` folder.
- `config/blocklist.conf`'s comment now states the verified
  `#` semantics; `smartdns.conf`'s comment no longer claims
  missing certs are auto-generated (they are fatal).
- MikroTik script creates the container env list before the
  container that references it.

### platforms/saman-os
- Audited: it vendors no stack copy — it delegates to the root
  installer, so it already carries the current stack (VPN
  included). Nothing to sync.

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

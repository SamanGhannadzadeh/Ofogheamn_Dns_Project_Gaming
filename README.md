# Ofogheamn DNS Project — Gaming Edition

**سرور DNS و Smart DNS مخصوص گیمرها** — با هستهٔ SmartDNS، انتخاب سریع‌ترین IP سرور بازی از بین همهٔ پاسخ‌ها، پشتیبانی از جدیدترین پروتکل‌های DNS، قوانین هایجک (Smart DNS) و بهینه‌سازی ویژهٔ **Call of Duty / Warzone**.

A gaming Smart-DNS server (SmartDNS core): fastest-IP answer selection, DNS hijacking rules, all modern DNS transports, and a dedicated Call of Duty / Warzone optimisation pack. One-command install on any Debian/Ubuntu server.

## نصب سریع | Quick install

```sh
curl -fsSL https://raw.githubusercontent.com/saman-ghannadzadeh/Ofogheamn_Dns_Project_Gaming/main/install.sh | sudo bash
```

یا از روی کلون:

```sh
git clone https://github.com/saman-ghannadzadeh/Ofogheamn_Dns_Project_Gaming
cd Ofogheamn_Dns_Project_Gaming && sudo bash install.sh
```

نام عمومی سرور برای DoT/DoH را می‌توانی موقع نصب بدهی:
`OFOGH_DNS_HOSTNAME=dns.yourdomain.com`

## پروتکل‌ها | Client transports

| پروتکل | پورت | کاربرد |
|---|---|---|
| DNS معمولی UDP/TCP | 53 | پلی‌استیشن، ایکس‌باکس، روتر، همهٔ دستگاه‌ها |
| DoT (DNS-over-TLS, RFC 7858) | 853 | Private DNS اندروید |
| DoH (DNS-over-HTTPS, RFC 8484) | 443 — `https://HOST/dns-query` | مرورگرها، iOS |
| DoQ / DoH3 به‌سمت آپ‌استریم (RFC 9250 / RFC 9114) | — | سریع‌ترین مسیر به Cloudflare |

آپ‌استریم‌ها: Cloudflare و Google و Quad9 روی DoH + DoT + DoQ + H3 + UDP — هرکدام زودتر و سالم‌تر جواب بدهد برنده است.

## چرا برای گیمر؟ | Why it helps gaming

- **انتخاب سریع‌ترین IP:** برای هر دامنه، همهٔ IPهای کاندید با پینگ و اتصال TCP سنجیده می‌شوند و فقط سریع‌ترین به دستگاه می‌رسد (`speed-check-mode ping,tcp:443` + `response-mode fastest-response`). انتخاب سرور بازی در بیشتر بازی‌ها از همین‌جا شروع می‌شود.
- **کش همیشه‌گرم (روش Match-Ready این پروژه):** تایمر `cod-warmup` هر ۴ دقیقه دامنه‌های بازی را دوباره حل می‌کند؛ نه‌تنها جواب در کش تازه می‌ماند، بلکه سنجش سریع‌ترین IP هم مدام به‌روز می‌شود. وقتی بازی را باز می‌کنی، DNS صفر میلی‌ثانیه طول می‌کشد.
- **Serve-Stale در طول مسابقه:** اگر وسط بازی TTL تمام شود یا آپ‌استریم لحظه‌ای قطع شود، جواب قبلی فوراً داده می‌شود و در پس‌زمینه تازه‌سازی می‌شود (`serve-expired`). سشن بازی هرگز معطل DNS نمی‌ماند.
- **Prefetch:** دامنه‌های پرتکرار قبل از انقضا خودکار تازه می‌شوند.
- **ECS:** زیردامنهٔ شبکهٔ مشترک (`/24`) به آپ‌استریم می‌رسد تا CDN و لبه‌های بازی نزدیک‌ترین نود را بدهند.
- **تنظیم کرنل:** بافرهای UDP بزرگ، backlog بالا و `ping_group_range` برای سنجش پینگ سرویس (در `systemd/99-ofogheamn-dns.conf`).

**صداقت فنی:** DNS «سرور بازی» و «نزدیک‌ترین لبه» را انتخاب می‌کند و زمان لوک‌اپ را به صفر می‌رساند؛ پینگ داخل مسابقه بعد از انتخاب سرور، به مسیر اینترنت و ISP بستگی دارد و هیچ DNSای به‌تنهایی آن را جادویی کم نمی‌کند. این پروژه دقیقاً همان بخشی را بهینه می‌کند که دست DNS است — و کامل بهینه‌اش می‌کند.

## ویژهٔ Call of Duty / Warzone

بک‌اند کالاف روی **Demonware** است و انتخاب ریجن/لبه‌اش با DNS انجام می‌شود. این پروژه برای دامنه‌های کالاف (لیست `config/lists/cod.domains`: ‏`demonware.net`، `callofduty.com`، `battle.net`، `activision.com` و...) سخت‌گیرانه‌ترین رفتار را دارد: سنجش پینگ+TCP:443، انتخاب fastest-response، گروه آپ‌استریم گیمینگ و گرم‌کنندهٔ کش اختصاصی.

تست زندهٔ وضعیت کالاف روی سرور:

```sh
ofogheamn-dns cod-test
```

## هایجک / Smart DNS

سرور برای هر دامنه‌ای که بگویی خودش جواب می‌دهد — آی‌پی ثابت، CNAME یا آپ‌استریم ویژه:

```sh
ofogheamn-dns add-hijack api.example.com 203.0.113.10
ofogheamn-dns list-hijack
ofogheamn-dns remove-hijack api.example.com
```

قوانین در `/etc/ofogheamn-dns/hijack.conf` نگه داشته می‌شوند (سینتکس کامل SmartDNS آن‌جا کامنت شده).

## همهٔ درخواست‌های DNS مشترک از همین سرور رد می‌شود

سه لایهٔ اجرایی، هر سه در پروژه هست و با هم یعنی هیچ درخواست DNSای دور نمی‌زند:

1. **DHCP فقط همین سرور را می‌دهد** (option 6) — دستگاه‌های معمولی مستقیم از همین DNS می‌گیرند.
2. **ریدایرکت اجباری در گیت‌وی:** تمام ترافیک پورت ۵۳ شبکه (UDP و TCP، به هر مقصدی — حتی 8.8.8.8 دستی) با DNAT به این سرور برمی‌گردد و خروجی مستقیم ۸۵۳ (DoT/DoQ) بسته است. اسکریپت‌های آمادهٔ Linux و MikroTik و OpenWrt در پوشهٔ `gateway/`.
3. **بستن DNS رمزنگاری‌شدهٔ عمومی با IP:** اتصال 443/853 به IPهای ریزالورهای عمومی (Cloudflare/Google/Quad9/AdGuard/OpenDNS/ControlD و...) در گیت‌وی دراپ می‌شود (`gateway/block-doh-ips.sh`)؛ کلاینت‌های DoH سرسخت fail می‌شوند و برمی‌گردند روی DNS سیستم — یعنی همین سرور. روی خود سرور هم Canary استاندارد (`use-application-dns.net` بدون رکورد آدرس) ارتقای خودکار مرورگرها به DoH را خاموش می‌کند.

مرز صداقت: اگر مشترکی VPN کامل بزند، ترافیکش داخل تونل می‌رود و هیچ DNSای نمی‌تواند آن را ببیند؛ این بخش دست DNS نیست.

## پنل مدیریت وب | Web panel

بعد از نصب: `http://<server-ip>:8080` — رمز مدیر موقع نصب یک بار چاپ می‌شود (تغییر: `ofogheamn-dns panel-password <new>`).

از پنل می‌شود: وضعیت هر سه سرویس را دید و ری‌استارت کرد، قوانین هایجک را ساخت و حذف کرد، لیست‌های گیمینگ/کالاف را ویرایش کرد، **حالت عمومی/خصوصی** را عوض کرد و لیست شبکه‌های مجاز را نوشت، کاربران پروکسی را مدیریت کرد، لاگ‌ها و پرتکرارترین دامنه‌ها را دید و تست زندهٔ کالاف گرفت.

## پروکسی اختصاصی | Built-in proxy

هستهٔ پروکسی sing-box است: ورودی **Mixed** روی پورت **2080** — HTTP و SOCKS5 با هم، با **UDP** برای بازی، و احراز هویت کاربری. کاربر پیش‌فرض `ofogh` موقع نصب ساخته و رمزش یک بار چاپ می‌شود؛ کاربران بیشتر از پنل یا CLI:

```sh
ofogheamn-dns proxy add-user ali pass1234
ofogheamn-dns proxy users
```

## تونل گیمینگ — دستگاه ← سرور تو ← بازی | Gaming tunnel

DNS به‌تنهایی ترافیک بازی را حمل نمی‌کند؛ برای این‌که بازی واقعاً از سرور تو رد شود، پروژه یک **تونل WireGuard** هم دارد:

- مسیر کامل: دستگاه ← تونل ← سرور تو (همان‌جا DNS هم جواب می‌گیرد و NAT می‌شود) ← سرور بازی.
- ساخت کانفیگ هر دستگاه از پنل (تب «تونل گیمینگ») یا CLI: `ofogheamn-dns wg add-peer ps5-home` — کانفیگ آمادهٔ اپ WireGuard چاپ می‌شود.
- **کنسول (PS5):** خود کنسول تونل ندارد؛ تونل را روی روتر خانه (OpenWrt/MikroTik هر دو WireGuard بومی دارند) ببند تا کل شبکه — از جمله کنسول — از همین مسیر برود.
- صداقت فنی: تونل فقط وقتی پینگ را بهتر می‌کند که مسیر سرور تو از مسیر مستقیم ISP تمیزتر/کوتاه‌تر باشد؛ اگر سرور دور باشد، یک پرش اضافه می‌شود. DNS سریع + تونلِ مسیر خوب، ترکیب درست است.

## حالت عمومی / خصوصی | Public / Private

- **عمومی:** هر کسی می‌تواند از DNS استفاده کند (مناسب سرویس عمومی مشترکین).
- **خصوصی:** فقط IP/CIDRهای لیست مجاز — بقیه با فایروال روی پورت‌های DNS دراپ می‌شوند.

از پنل (تب «حالت عمومی/خصوصی») یا CLI: `ofogheamn-dns mode private` و `ofogheamn-dns allow add 192.168.1.0/24`.

## همهٔ سیستم‌عامل‌ها | Platforms

نصب برای Debian/Ubuntu، **Saman OS** (و نسخهٔ Server آن از پیش نصب)، Docker روی هر سیستم، Windows، OpenWrt و **MikroTik RouterOS** در پوشهٔ `platforms/` است — جدول کامل: [platforms/README.md](platforms/README.md).

## مدیریت | Manage

```sh
ofogheamn-dns            # منوی تعاملی
ofogheamn-dns status | mode | proxy | cod-test | logs | test
ofogheamn-dns add-game  newgame.com      # افزودن دامنه به لیست گیمینگ
ofogheamn-dns update                     # به‌روزرسانی هسته‌ها (SmartDNS + sing-box)
sudo bash uninstall.sh                   # حذف کامل
```

## تنظیم روی دستگاه‌ها

- **PS5:** ‏Settings → Network → Settings → Set Up Internet Connection → Advanced → DNS Settings: Manual → Primary DNS = آی‌پی سرور.
- **Android:** ‏Private DNS → هاست‌نیم سرور (DoT).
- **Windows:** ‏DNS دستی روی کارت شبکه، یا DoH با آدرس `https://HOST/dns-query`.
- **روتر:** ‏DHCP option 6 = آی‌پی سرور، تا همهٔ دستگاه‌های خانه خودکار از همین DNS بگیرند.

## ساختار پروژه

```
install.sh            نصب یک‌دستوره (آخرین SmartDNS + کانفیگ + سرویس)
config/smartdns.conf  کانفیگ اصلی: شنونده‌ها، آپ‌استریم‌ها، موتور سرعت
config/lists/         gaming.domains + cod.domains
config/hijack.conf    قوانین هایجک/Smart DNS
config/force-dns.conf ضد دورزدن (canary + لیست اختیاری)
gateway/              ریدایرکت ۵۳ و بستن ۸۵۳ (Linux / MikroTik / OpenWrt)
scripts/              ofogheamn-dns (مدیریت) + cod-warmup (گرم‌کنندهٔ کش)
systemd/              سرویس + تایمرها + تیونینگ کرنل
tests/smoke-test.sh   تست دود بعد از نصب
```

## نکتهٔ TLS

نصاب برای DoT/DoH یک گواهی self-signed می‌سازد تا همه‌چیز از همان اول کار کند. برای سرویس عمومی، فایل‌های `/etc/ofogheamn-dns/tls/{fullchain,privkey}.pem` را با گواهی واقعی دامنه‌ات عوض و سرویس را ری‌استارت کن.

## لایسنس

کدهای این پروژه MIT. هستهٔ SmartDNS (پروژهٔ pymumu/smartdns) تحت GPL است و موقع نصب از انتشار رسمی خودش دانلود می‌شود؛ داخل این مخزن کپی نشده است.

ساخته‌شده برای «افق امن ایرانیان» — Ofogheamn.

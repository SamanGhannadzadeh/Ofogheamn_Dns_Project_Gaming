# انتشار برای همهٔ سیستم‌عامل‌ها | All platforms

| سیستم | مسیر نصب | وضعیت |
|---|---|---|
| Debian / Ubuntu (سرور) | `install.sh` در ریشهٔ پروژه | کامل: DNS + پروکسی + پنل + CLI |
| **Saman OS** | `platforms/saman-os/install-saman-os.sh` | کامل + لانچر دسکتاپ پنل — و **نسخهٔ Server سامان او‌اس** همه را از پیش نصب دارد |
| Docker (Linux/Windows/macOS/NAS) | `docker/docker-compose.yml` | کامل، تک‌کانتینر |
| Windows | `platforms/windows/install.ps1` | نود بومی: هستهٔ AdGuard Home (مسابقهٔ موازی آپ‌استریم‌ها) + پروکسی sing-box + فایروال؛ پنل AGH |
| OpenWrt | `platforms/openwrt/install-openwrt.sh` | DNS بومی روتر (پکیج رسمی SmartDNS) + لیست‌ها و هایجک |
| MikroTik RouterOS 7 | `platforms/mikrotik/container.rsc` | اجرای سرور داخل کانتینر RouterOS (CHR و بردهای ARM/x86 با پکیج container) |
| macOS | `platforms/macos/install.sh` | نود بومی (Apple Silicon و Intel): هستهٔ AdGuard Home + پروکسی sing-box با launchd؛ یا Docker |
| گیت‌وی شبکه (هر روتر) | پوشهٔ `gateway/` | فقط لایهٔ اجبار: ریدایرکت ۵۳ + بستن دورزدن |
| AmneziaWG (تونل آزمایشی) | `platforms/amneziawg/` | آزمایشی: وایرگاردِ پنهان‌شده در برابر فینگرپرینت + مبدل کانفیگ awgify |

نکته‌ها:

- **MikroTik بدون کانتینر:** اگر روترت کانتینر ندارد، سرور را روی هر دستگاه دیگری نصب کن و از `gateway/mikrotik.rsc` برای مجبورکردن کل شبکه به همان سرور استفاده کن.
- **OpenWrt:** هستهٔ SmartDNS همان پکیج رسمی فید OpenWrt است؛ کانفیگ و لیست‌های این پروژه رویش می‌نشیند.
- **Windows و macOS:** هستهٔ SmartDNS باینری ویندوز/مک ندارد؛ روی این دو سیستم همان مدل با هستهٔ بومی AdGuard Home اجرا می‌شود (نصب‌کنندهٔ قبلی ویندوز که دنبال باینری ویندوزی SmartDNS می‌گشت حذف شد — چنین فایلی در انتشارهای SmartDNS وجود ندارد). پنل فارسی و تونل سروری فعلاً لینوکسی‌اند؛ جزئیات در README هر پوشه.

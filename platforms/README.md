# انتشار برای همهٔ سیستم‌عامل‌ها | All platforms

| سیستم | مسیر نصب | وضعیت |
|---|---|---|
| Debian / Ubuntu (سرور) | `install.sh` در ریشهٔ پروژه | کامل: DNS + پروکسی + پنل + CLI |
| **Saman OS** | `platforms/saman-os/install-saman-os.sh` | کامل + لانچر دسکتاپ پنل — و **نسخهٔ Server سامان او‌اس** همه را از پیش نصب دارد |
| Docker (Linux/Windows/macOS/NAS) | `docker/docker-compose.yml` | کامل، تک‌کانتینر |
| Windows | `platforms/windows/install.ps1` | DNS + پروکسی به‌صورت سرویس (NSSM)؛ پنل با Python |
| OpenWrt | `platforms/openwrt/install-openwrt.sh` | DNS بومی روتر (پکیج رسمی SmartDNS) + لیست‌ها و هایجک |
| MikroTik RouterOS 7 | `platforms/mikrotik/container.rsc` | اجرای سرور داخل کانتینر RouterOS (CHR و بردهای ARM/x86 با پکیج container) |
| macOS | Docker Desktop + همان compose | کامل از راه داکر |
| گیت‌وی شبکه (هر روتر) | پوشهٔ `gateway/` | فقط لایهٔ اجبار: ریدایرکت ۵۳ + بستن دورزدن |

نکته‌ها:

- **MikroTik بدون کانتینر:** اگر روترت کانتینر ندارد، سرور را روی هر دستگاه دیگری نصب کن و از `gateway/mikrotik.rsc` برای مجبورکردن کل شبکه به همان سرور استفاده کن.
- **OpenWrt:** هستهٔ SmartDNS همان پکیج رسمی فید OpenWrt است؛ کانفیگ و لیست‌های این پروژه رویش می‌نشیند.
- **Windows:** اسکریپت باید Administrator باشد؛ اگر Python نباشد فقط پنل نصب نمی‌شود و بقیه کامل کار می‌کند.

# نسخهٔ Lite — بدون پنل گرافیکی

نسخهٔ Lite همان موتور کامل DNS و پروکسی و تونل و مش است، **بدون هیچ پنل وبی**: سبک‌تر، سطح حمله کمتر، و مدیریت فقط از خط فرمان و فایل کانفیگ. برای سرورهایی که قرار نیست کسی تویشان بچرخد، یا دستگاه‌های ضعیف.

## چه چیزی هست و چه چیزی نیست

| | کامل | Lite |
|---|---|---|
| DNS (سریع‌ترین IP، کش، DoH/DoT) | ✓ | ✓ |
| پروکسی sing-box | ✓ | ✓ |
| تونل WireGuard و مش | ✓ | ✓ |
| گرم‌کن کش کالاف و لیست مسدودی | ✓ | ✓ |
| پنل وب فارسی (لینوکس) / داشبورد AGH (ویندوز و مک) | ✓ | ✗ |

## نصب Lite روی هر سیستم

**لینوکس (و Saman OS):**
```bash
sudo bash install.sh --lite        # یا: OFOGH_LITE=1 sudo bash install.sh
```
مدیریت: `ofogheamn-dns` (منوی تعاملی و همهٔ زیرفرمان‌ها).

**Docker (هرجا داکر هست):**
```bash
docker compose -f docker/docker-compose.lite.yml up -d
```

**ویندوز:**
```powershell
.\install.ps1 -Lite
```
داشبورد AdGuard Home فقط روی خود دستگاه (localhost:3000) می‌ماند و از شبکه دیده نمی‌شود.

**مک:**
```bash
OFOGH_LITE=1 bash platforms/macos/install.sh
```

**OpenWrt و MikroTik** ذاتاً Lite هستند: پنل وبی جدا ندارند و با کانفیگ و دستور مدیریت می‌شوند.

## از Lite به کامل و برعکس

- Lite → کامل (لینوکس): نصب را بدون `--lite` دوباره اجرا کن؛ پنل و رمزش ساخته می‌شود و بقیهٔ تنظیماتت دست نمی‌خورد.
- کامل → Lite (لینوکس): `sudo systemctl disable --now ofogheamn-panel` کافی است.

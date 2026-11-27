# کیت کلاینت افق امن — راهنمای همهٔ پلتفرم‌ها

نود: `180.149.45.237` — نام عمومی: `ofogheamn.mytunnel.org`
DNS روی UDP/TCP پورت ۵۳، ‏DoT روی ۸۵۳، ‏DoH روی
`https://ofogheamn.mytunnel.org/dns-query`
گواهی TLS نود عمومی و معتبر است (Let's Encrypt، تمدید خودکار).

## ماتریس پلتفرم (وضعیت واقعی، آبان ۲۰۲۶)

| پلتفرم | روش | وضعیت |
|---|---|---|
| پلی‌استیشن / ایکس‌باکس / سوییچ | DNS دستی = IP نود (هر دو خانه) | ✅ آماده |
| ویندوز | اسکریپت `windows/Set-OfoghDns.ps1` (DNS + DoH) | ✅ آماده |
| اندروید | Private DNS: `ofogheamn.mytunnel.org` | ✅ آماده |
| اندروید | برنامهٔ sing-box + کانفیگ نردبان پروژه | ✅ آماده |
| آیفون | پروفایل `ios/OfoghDns.mobileconfig` (DoH) | ✅ آماده |
| لینوکس | دراپ‌این systemd-resolved در `linux/` (ساده یا DoT) | ✅ آماده |

## پوشه‌ها

- `console/` — تنظیم کنسول‌ها قدم‌به‌قدم
- `windows/` — اسکریپت تنظیم DNS و DoH ویندوز (با سوییچ بازگشت به DHCP)
- `android/` — راهنمای اندروید: Private DNS و برنامهٔ sing-box
- `ios/` — پروفایل DoH آیفون + راهنما
- `linux/` — دراپ‌این resolved و راهنمای DoT

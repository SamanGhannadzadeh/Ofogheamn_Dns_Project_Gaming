# اندروید

## مسیر سبک (آماده): Private DNS خود اندروید

Settings ← Network & internet ← Private DNS ←
Private DNS provider hostname:

```
ofogheamn.duckdns.org
```

تمام. DNS کل گوشی رمزنگاری‌شده (DoT) از نود رد می‌شود و گواهی نود
عمومی و معتبر است، پس تنظیم دیگری لازم نیست.

## مسیر کامل (تونل + DNS): برنامهٔ sing-box

۱. برنامهٔ رسمی sing-box (SagerNet) را نصب کنید.
۲. کانفیگ نردبان پروژه (`ofogh-client.json`) را Import کنید.
۳. این کانفیگ DNS را هم از داخل تونل به نود می‌فرستد.

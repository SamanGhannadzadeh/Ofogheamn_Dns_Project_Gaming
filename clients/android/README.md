# اندروید

## مسیر آماده (امروز): برنامهٔ sing-box

۱. برنامهٔ رسمی sing-box (SagerNet) را نصب کنید.
۲. کانفیگ نردبان پروژه (`ofogh-client.json`) را Import کنید.
۳. همین کانفیگ، DNS را هم از داخل تونل به نود می‌فرستد؛ تنظیم جدا لازم نیست.

## مسیر سبک (پس از فعال‌سازی دامنه): Private DNS خود اندروید

Settings ← Network & internet ← Private DNS ←
Private DNS provider hostname: `dns.ofogheamn.ir`

این مسیر فقط وقتی کار می‌کند که نام `dns.ofogheamn.ir` در DNS عمومی به
IP نود اشاره کند و گواهی عمومی روی نود نشسته باشد (به ماتریس `../README.md`
نگاه کنید). تا آن موقع از مسیر sing-box استفاده کنید؛ Private DNS با IP
قابل تنظیم نیست (خود اندروید فقط نام میزبان می‌پذیرد).

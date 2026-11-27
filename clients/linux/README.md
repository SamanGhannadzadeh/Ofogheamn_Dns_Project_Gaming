# لینوکس

## نصب

```sh
sudo mkdir -p /etc/systemd/resolved.conf.d
sudo cp ofogh-resolved.conf /etc/systemd/resolved.conf.d/ofogh.conf
sudo systemctl restart systemd-resolved
```

برای DoT رمزنگاری‌شده، داخل همان فایل بلوک DoT را جایگزین کنید
(گواهی نود عمومی است و CA اضافه نمی‌خواهد).

راستی‌آزمایی:

```sh
resolvectl status | grep -i "dns servers"
dig example.com   # باید از 180.149.45.237 جواب بیاید
```

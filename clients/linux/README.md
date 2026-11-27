# لینوکس

## DNS ساده (آماده)

```sh
sudo mkdir -p /etc/systemd/resolved.conf.d
sudo cp ofogh-resolved.conf /etc/systemd/resolved.conf.d/ofogh.conf
sudo systemctl restart systemd-resolved
```

## DoT رمزنگاری‌شده با CA نود (آماده، مخصوص لینوکس)

لینوکس می‌تواند به گواهی خودامضای نود اعتماد کند، پس DoT همین امروز هم
شدنی است:

```sh
sudo cp ofogh-ca.pem /usr/local/share/ca-certificates/ofogh-ca.crt
sudo update-ca-certificates
```

بعد در `ofogh-resolved.conf` بلوک DoT را (داخل همان فایل توضیح داده شده)
جایگزین بلوک ساده کنید و سرویس را ری‌استارت کنید. راستی‌آزمایی:

```sh
resolvectl status | grep -i "dns servers"
dig example.com   # باید از 180.149.45.237 جواب بیاید
```

#!/usr/bin/env python3
"""Ofogheamn IP registration panel.

Self-service page for node users whose egress IP keeps changing
(CGNAT): open the page, type the personal registration code,
and the visitor's *current* IP replaces their previous one in
the node allowlist (one active IP per code; the firewall is
re-applied after every change). A status view shows the IP a
code currently holds, and an admin view (separate admin code)
lists every user, their IP and their last change.

State files (all under /etc/ofogheamn-dns):
  reg-codes.json  {sha256(code): {"label": str, "created": ts}}
  reg-state.json  {sha256(code): {"ip": str, "updated": ts}}
  reg-admin.json  {"hash": sha256(admin_code)}
  allowlist.txt   plain IPs; only IPs present in reg-state
                  are ever added/removed by this service.
"""
import hashlib
import hmac
import html
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

ETC = "/etc/ofogheamn-dns"
CODES = os.path.join(ETC, "reg-codes.json")
STATE = os.path.join(ETC, "reg-state.json")
ADMIN = os.path.join(ETC, "reg-admin.json")
ALLOW = os.path.join(ETC, "allowlist.txt")
PORT = 8081
NODE_IP = "180.149.45.237"

_hits = {}
_changes = {}

FA_NUM = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_num(x):
    return str(x).translate(FA_NUM)


def rel_time(ts):
    if not ts:
        return "—"
    d = int(time.time()) - int(ts)
    if d < 90:
        return "همین حالا"
    if d < 3600:
        return "%s دقیقه پیش" % fa_num(d // 60)
    if d < 86400:
        return "%s ساعت پیش" % fa_num(d // 3600)
    return "%s روز پیش" % fa_num(d // 86400)


def _limited(bucket, key, limit, window=3600):
    now = time.time()
    lst = [t for t in bucket.get(key, []) if now - t < window]
    if len(lst) >= limit:
        bucket[key] = lst
        return True
    lst.append(now)
    bucket[key] = lst
    return False


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _apply_firewall():
    subprocess.run(["systemctl", "restart", "ofogheamn-firewall.service"],
                   timeout=30, capture_output=True)


def _is_tunnel_ip(ip):
    return ip == NODE_IP or ip.startswith("10.66.66.") or ip.startswith("127.")


def _find_code(codes, code):
    chash = hashlib.sha256(code.strip().encode()).hexdigest()
    for k, v in codes.items():
        if hmac.compare_digest(k, chash):
            return chash, v
    return None, None


def register(code, src_ip):
    """Returns (ok, message, old_ip)."""
    if _is_tunnel_ip(src_ip):
        return False, ("شما از داخل تونل/VPN وصل شده‌اید و IP واقعی‌تان دیده نمی‌شود. "
                       "تونل را خاموش کنید و دوباره ثبت کنید."), None
    codes = _load(CODES, {})
    chash, entry = _find_code(codes, code)
    if entry is None:
        return False, "کد ثبت معتبر نیست.", None
    if _limited(_changes, chash, 20):
        return False, "تعداد تغییر IP برای این کد در یک ساعت پر شده است؛ بعداً تلاش کنید.", None
    state = _load(STATE, {})
    old_ip = (state.get(chash) or {}).get("ip")
    if old_ip != src_ip:
        lines = []
        if os.path.exists(ALLOW):
            with open(ALLOW) as f:
                lines = [ln.strip() for ln in f if ln.strip()]
        if old_ip and old_ip in lines:
            lines.remove(old_ip)
        if src_ip not in lines:
            lines.append(src_ip)
        with open(ALLOW, "w") as f:
            f.write("\n".join(lines) + "\n")
        state[chash] = {"ip": src_ip, "updated": int(time.time()),
                        "label": entry.get("label", "")}
        _save(STATE, state)
        _apply_firewall()
    return True, src_ip, old_ip


def code_status(code):
    codes = _load(CODES, {})
    chash, entry = _find_code(codes, code)
    if entry is None:
        return None
    state = _load(STATE, {})
    cur = state.get(chash) or {}
    return {"label": entry.get("label", ""), "ip": cur.get("ip"),
            "updated": cur.get("updated")}


def is_admin(code):
    adm = _load(ADMIN, {})
    want = adm.get("hash")
    if not want:
        return False
    got = hashlib.sha256(code.strip().encode()).hexdigest()
    return hmac.compare_digest(want, got)


CSS = """
*{box-sizing:border-box}
body{font-family:Vazirmatn,Tahoma,sans-serif;margin:0;min-height:100vh;color:#e8eef7;
background:
radial-gradient(60rem 40rem at 85% -10%,rgba(21,94,117,.85) 0,transparent 55%),
radial-gradient(50rem 36rem at 8% 110%,rgba(76,29,149,.8) 0,transparent 55%),
linear-gradient(160deg,#0b1220,#0f172a 55%,#111827);
display:flex;align-items:center;justify-content:center;padding:20px;overflow-x:hidden}
body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.35;
background-image:linear-gradient(rgba(148,163,184,.06) 1px,transparent 1px),
linear-gradient(90deg,rgba(148,163,184,.06) 1px,transparent 1px);
background-size:44px 44px;
mask-image:radial-gradient(70% 60% at 50% 40%,#000 30%,transparent 100%)}
.card{position:relative;width:100%;max-width:440px;padding:32px 26px 28px;border-radius:26px;
background:linear-gradient(180deg,rgba(255,255,255,.09),rgba(255,255,255,.045));
border:1px solid rgba(255,255,255,.16);
backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
box-shadow:0 30px 70px rgba(0,0,0,.5),inset 0 1px 0 rgba(255,255,255,.15);
animation:in .55s cubic-bezier(.2,.8,.25,1) both}
.card:before{content:"";position:absolute;inset:-1px;border-radius:26px;padding:1px;
background:linear-gradient(140deg,rgba(34,211,238,.55),transparent 35%,transparent 65%,rgba(167,139,250,.5));
-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);
-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none}
@keyframes in{from{opacity:0;transform:translateY(16px) scale(.985)}to{opacity:1;transform:none}}
.brand{display:flex;align-items:center;gap:11px;color:#e0f2fe;font-weight:800;font-size:16px}
.brand small{display:block;color:#7dd3fc;font-weight:400;font-size:11px;margin-top:2px}
.logo{width:42px;height:42px;flex:0 0 42px;border-radius:13px;display:grid;place-items:center;
background:linear-gradient(145deg,rgba(34,211,238,.25),rgba(2,132,199,.12));
border:1px solid rgba(34,211,238,.4);box-shadow:0 6px 18px rgba(34,211,238,.25)}
.pulse{width:8px;height:8px;border-radius:50%;background:#34d399;margin-inline-start:auto;
box-shadow:0 0 10px #34d399;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.4);opacity:.6}}
h1{font-size:25px;margin:18px 0 6px}
.sub{color:#9fb0c7;line-height:2;font-size:14px;margin:0}
.steps{display:flex;gap:8px;margin:18px 0 2px}
.step{flex:1;display:flex;align-items:center;gap:8px;padding:9px 12px;border-radius:12px;
background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);
font-size:12px;color:#cbd5e1}
.step b{width:20px;height:20px;flex:0 0 20px;border-radius:50%;display:grid;place-items:center;
background:rgba(34,211,238,.18);color:#7dd3fc;font-size:12px}
.ipbox{margin:16px 0 6px;padding:16px;border-radius:16px;text-align:center;position:relative;
background:linear-gradient(180deg,rgba(34,211,238,.12),rgba(34,211,238,.05));
border:1px solid rgba(34,211,238,.4)}
.ipbox .lbl{font-size:12px;color:#7dd3fc;margin-bottom:6px}
.iprow{display:flex;align-items:center;justify-content:center;gap:10px;direction:ltr}
.ip{font-size:27px;font-weight:800;letter-spacing:1px;color:#f0f9ff}
.copy{border:1px solid rgba(125,211,252,.4);background:rgba(2,132,199,.18);color:#bae6fd;
border-radius:10px;padding:6px 9px;cursor:pointer;font-family:inherit;font-size:12px;transition:.2s}
.copy:hover{background:rgba(2,132,199,.35)}
label{display:block;margin:18px 0 8px;font-size:14px;color:#cbd5e1}
input{width:100%;padding:14px 16px;border-radius:14px;border:1px solid rgba(255,255,255,.18);
background:rgba(15,23,42,.65);color:#fff;font-size:16px;outline:none;transition:.2s;direction:ltr;text-align:left}
input:focus{border-color:#22d3ee;box-shadow:0 0 0 4px rgba(34,211,238,.18)}
button{width:100%;padding:14px;margin-top:16px;border:0;border-radius:14px;cursor:pointer;
background:linear-gradient(90deg,#0284c7,#22d3ee);color:#06202e;font-size:17px;font-weight:800;
transition:.2s;box-shadow:0 10px 26px rgba(2,132,199,.35)}
button:hover{transform:translateY(-1px)} button:active{transform:scale(.99)}
button.ghost{background:rgba(255,255,255,.07);color:#bae6fd;box-shadow:none;
border:1px solid rgba(125,211,252,.35);font-size:15px}
.msg{margin-top:18px;padding:13px 14px;border-radius:14px;text-align:center;line-height:2;
font-size:14px;border:1px solid rgba(255,255,255,.14)}
.ok{background:rgba(34,197,94,.14)} .err{background:rgba(239,68,68,.16)}
.foot{margin-top:18px;text-align:center;color:#64748b;font-size:12px;line-height:1.9}
table{width:100%;border-collapse:collapse;margin-top:14px;font-size:13px}
th,td{padding:9px 6px;border-bottom:1px solid rgba(255,255,255,.09);text-align:right}
td.ipc{direction:ltr;text-align:left;font-weight:700;color:#e0f2fe}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11px;
background:rgba(34,197,94,.18);color:#86efac}
.chip.off{background:rgba(148,163,184,.15);color:#94a3b8}
a{color:#7dd3fc;text-decoration:none}
/* ---- motion ---- */
@keyframes drift{from{transform:translate3d(-2%,-1%,0) scale(1)}to{transform:translate3d(2%,2%,0) scale(1.12)}}
body::before{animation:drift 26s ease-in-out infinite alternate}
@keyframes sheen{0%{background-position:200% 0}55%,100%{background-position:-120% 0}}
.card::before{background:linear-gradient(90deg,#0ea5e9,#22d3ee,#a78bfa,#0ea5e9);
background-size:220% 100%;animation:sheen 7s ease-in-out infinite}
@keyframes riseIn{from{opacity:0;transform:translateY(14px) scale(.985)}to{opacity:1;transform:none}}
.card>*{animation:riseIn .6s cubic-bezier(.22,.9,.3,1.2) both}
.card>*:nth-child(2){animation-delay:.05s}.card>*:nth-child(3){animation-delay:.1s}
.card>*:nth-child(4){animation-delay:.15s}.card>*:nth-child(5){animation-delay:.2s}
.card>*:nth-child(6){animation-delay:.25s}.card>*:nth-child(7){animation-delay:.3s}
@keyframes floaty{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}
.logo{animation:floaty 5s ease-in-out infinite}
button{transition:transform .16s ease,box-shadow .16s ease,filter .16s ease}
button:hover{transform:translateY(-1px);filter:brightness(1.07)}
button:active{transform:scale(.975)}
input{transition:border-color .2s ease,box-shadow .2s ease,background .2s ease}
@keyframes msgIn{0%{opacity:0;transform:translateY(8px) scale(.97)}60%{transform:translateY(-1px) scale(1.01)}100%{opacity:1;transform:none}}
.msg{animation:msgIn .45s cubic-bezier(.22,.9,.3,1.25) both}
.msg b{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;
border-radius:50%;background:rgba(255,255,255,.18);margin-inline-end:2px}
@keyframes ipGlow{0%,100%{box-shadow:inset 0 0 0 1px rgba(125,211,252,.12)}50%{box-shadow:inset 0 0 22px rgba(34,211,238,.13)}}
.ipbox{animation:ipGlow 4.5s ease-in-out infinite}
.step{transition:transform .2s ease,background .2s ease}
.step:hover{transform:translateY(-2px)}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

HEAD = """<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="theme-color" content="#0f172a">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="ثبت IP افق امن">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='38' fill='%2322d3ee'/></svg>">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css">
<style>""" + CSS + """</style></head><body><div class="card">
<div class="brand"><span class="logo"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M3 17.5h18" stroke="#7dd3fc" stroke-width="1.8" stroke-linecap="round"/><path d="M6.5 17.5a5.5 5.5 0 0 1 11 0" stroke="#22d3ee" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17.5" r="2.1" fill="#22d3ee"/><path d="M12 4v3M4.9 7.9l2.1 2.1M19.1 7.9L17 10" stroke="#7dd3fc" stroke-width="1.8" stroke-linecap="round"/></svg></span><span>افق امن ایرانیان<small>سامانهٔ ثبت IP کاربران</small></span><span class="pulse"></span></div>
"""

FOOT = """
<div class="foot">با ثبت تازه، IP قبلی شما خودکار حذف می‌شود.<br>هنگام ثبت، VPN یا تونل روشن نباشد.</div>
</div></body></html>"""


def page_user(ip, msg="", kind="ok"):
    icon = "✓" if kind == "ok" else "!"
    m = ('<div class="msg %s"><b>%s</b> %s</div>' % (kind, icon, html.escape(msg))) if msg else ""
    return (HEAD.replace("__TITLE__", "ثبت IP — افق امن ایرانیان")
            + "<h1>ثبت IP شما</h1>"
            + '<p class="sub">هر وقت IP اینترنت‌تان عوض شد، کدتان را بزنید تا دسترسی‌تان بدون وقفه ادامه پیدا کند.</p>'
            + '<div class="steps"><div class="step"><b>۱</b> کدتان را وارد کنید</div>'
            + '<div class="step"><b>۲</b> دکمهٔ ثبت را بزنید</div></div>'
            + '<div class="ipbox"><div class="lbl">IP فعلی شما</div>'
            + '<div class="iprow"><span class="ip" id="myip">%s</span>'
            % html.escape(ip)
            + '<button class="copy" type="button" onclick="cp(this)">کپی</button></div></div>'
            + '<form method="post" action="/register" onsubmit="this.querySelector(\'button\').textContent=\'در حال ثبت…\'">'
            + '<label for="code">کد ثبت شما</label>'
            + '<input id="code" name="code" placeholder="saman_ghannadzadeh" autocomplete="off" required>'
            + '<button type="submit">ثبت این IP</button></form>'
            + '<form method="post" action="/status">'
            + '<input type="hidden" name="code" id="code2">'
            + '<button class="ghost" type="submit" onclick="document.getElementById(\'code2\').value=document.getElementById(\'code\').value">وضعیت کد من</button></form>'
            + m
            + '<button class="ghost" type="button" id="installBtn" style="display:none">افزودن به صفحهٔ اصلی</button>'
            + '<div class="msg" id="iosHint" style="display:none">برای افزودن به صفحهٔ اصلی: دکمهٔ اشتراک‌گذاری (Share) را بزنید و «Add to Home Screen» را انتخاب کنید.</div>'
            + '<script>function cp(b){var t=document.getElementById("myip").textContent;'
            + 'if(navigator.clipboard){navigator.clipboard.writeText(t)}'
            + 'b.textContent="کپی شد";setTimeout(function(){b.textContent="کپی"},1600)}'
            + 'var dp=null,ib=document.getElementById("installBtn");'
            + 'window.addEventListener("beforeinstallprompt",function(e){e.preventDefault();dp=e;ib.style.display="block"});'
            + 'ib.addEventListener("click",function(){if(dp){dp.prompt();dp.userChoice.then(function(){dp=null;ib.style.display="none"})}else{document.getElementById("iosHint").style.display="block"}});'
            + 'var ios=/iphone|ipad|ipod/i.test(navigator.userAgent)&&!window.MSStream;'
            + 'var standalone=window.matchMedia("(display-mode: standalone)").matches||window.navigator.standalone;'
            + 'if(ios&&!standalone){ib.style.display="block"}</script>'
            + FOOT)


def page_status(ip, st, visitor_ip):
    rows = ""
    if st["ip"]:
        same = st["ip"] == visitor_ip
        rows = ("<tr><td>IP ثبت‌شده</td><td class='ipc'>%s</td></tr>"
                "<tr><td>آخرین تغییر</td><td>%s</td></tr>"
                "<tr><td>وضعیت</td><td>%s</td></tr>"
                % (html.escape(st["ip"]), rel_time(st["updated"]),
                   '<span class="chip">همین IP فعلی شماست</span>' if same
                   else '<span class="chip off">با IP فعلی شما فرق دارد</span>'))
    else:
        rows = "<tr><td>هنوز IPای برای این کد ثبت نشده است.</td></tr>"
    return (HEAD.replace("__TITLE__", "وضعیت کد — افق امن ایرانیان")
            + "<h1>وضعیت کد %s</h1>" % html.escape(st["label"])
            + "<table>%s</table>" % rows
            + '<p class="sub" style="margin-top:14px"><a href="/">بازگشت به ثبت IP</a></p>'
            + FOOT)


def page_admin(rows_html, msg="", kind="ok"):
    m = ('<div class="msg %s">%s</div>' % (kind, html.escape(msg))) if msg else ""
    table = ""
    if rows_html:
        table = ("<table><tr><th>کاربر</th><th>IP فعلی</th><th>آخرین تغییر</th></tr>"
                 + rows_html + "</table>")
    return (HEAD.replace("__TITLE__", "مدیریت — افق امن ایرانیان")
            + "<h1>پنل مدیریت</h1>"
            + '<form method="post" action="/admin">'
            + '<label for="code">کد مدیریت</label>'
            + '<input id="code" name="code" autocomplete="off" required>'
            + '<button type="submit">مشاهدهٔ کاربران</button></form>'
            + m + table + FOOT)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.client_address[0], fmt % args))

    def _send(self, body):
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _form(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 4096:
            return None
        return parse_qs(self.rfile.read(length).decode("utf-8", "replace"))

    def do_GET(self):
        ip = self.client_address[0]
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if self.path == "/manifest.webmanifest":
            manifest = {
                "name": "افق امن ایرانیان — ثبت IP",
                "short_name": "ثبت IP افق امن",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "dir": "rtl",
                "lang": "fa",
                "background_color": "#0f172a",
                "theme_color": "#0f172a",
                "icons": [
                    {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
                    {"src": "/icon-maskable-512.png", "sizes": "512x512",
                     "type": "image/png", "purpose": "maskable"},
                ],
            }
            data = json.dumps(manifest, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path in ("/icon-192.png", "/icon-512.png",
                         "/icon-maskable-512.png", "/apple-touch-icon.png"):
            fpath = os.path.join("/usr/local/share/ofogh-ipreg",
                                 os.path.basename(self.path))
            try:
                with open(fpath, "rb") as f:
                    data = f.read()
            except OSError:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/admin":
            self._send(page_admin(""))
            return
        if self.path not in ("/", "/index.html"):
            self.send_response(404)
            self.end_headers()
            return
        if _is_tunnel_ip(ip):
            self._send(page_user(ip, "هشدار: شما از داخل تونل وصل شده‌اید و این IP، IP واقعی شما نیست. "
                                     "تونل/VPN را خاموش کنید و صفحه را دوباره باز کنید.", "err"))
            return
        self._send(page_user(ip))

    def do_POST(self):
        src = self.client_address[0]
        form = self._form()
        if form is None:
            self._send(page_user(src, "درخواست نامعتبر است.", "err"))
            return
        code = (form.get("code") or [""])[0]
        if self.path == "/register":
            if _limited(_hits, src, 30):
                self._send(page_user(src, "درخواست‌های شما زیاد شده است؛ کمی صبر کنید.", "err"))
                return
            ok, result, old_ip = register(code, src)
            if ok:
                msg = "انجام شد — IP %s برای شما فعال شد." % result
                if old_ip and old_ip != result:
                    msg += " (IP قبلی %s حذف شد.)" % old_ip
                self._send(page_user(src, msg))
            else:
                self._send(page_user(src, result, "err"))
            return
        if self.path == "/status":
            st = code_status(code)
            if st is None:
                self._send(page_user(src, "کد ثبت معتبر نیست.", "err"))
            else:
                self._send(page_status(src, st, src))
            return
        if self.path == "/admin":
            if not is_admin(code):
                self._send(page_admin("", "کد مدیریت معتبر نیست.", "err"))
                return
            codes = _load(CODES, {})
            state = _load(STATE, {})
            rows = ""
            for h, v in sorted(codes.items(), key=lambda kv: kv[1].get("label", "")):
                cur = state.get(h) or {}
                rows += ("<tr><td>%s</td><td class='ipc'>%s</td><td>%s</td></tr>"
                         % (html.escape(v.get("label", "?")),
                            html.escape(cur.get("ip") or "—"),
                            rel_time(cur.get("updated"))))
            self._send(page_admin(rows, "فهرست کاربران به‌روز است."))
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

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
background:radial-gradient(60rem 40rem at 85% -10%,#155e75 0,transparent 55%),
radial-gradient(50rem 36rem at 8% 110%,#4c1d95 0,transparent 55%),
linear-gradient(160deg,#0b1220,#0f172a 55%,#111827);
display:flex;align-items:center;justify-content:center;padding:20px}
.card{width:100%;max-width:440px;padding:30px 26px;border-radius:24px;
background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);
backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
box-shadow:0 24px 60px rgba(0,0,0,.45);animation:in .5s ease both}
@keyframes in{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
.brand{display:flex;align-items:center;gap:10px;color:#7dd3fc;font-weight:700;font-size:15px}
.brand .dot{width:11px;height:11px;border-radius:50%;background:#22d3ee;
box-shadow:0 0 14px #22d3ee;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.35)}}
h1{font-size:24px;margin:14px 0 6px}
.sub{color:#9fb0c7;line-height:2;font-size:14px;margin:0}
.ipbox{margin:20px 0 6px;padding:16px;border-radius:16px;text-align:center;
background:rgba(34,211,238,.08);border:1px dashed rgba(34,211,238,.45)}
.ipbox .lbl{font-size:12px;color:#7dd3fc;margin-bottom:6px}
.ip{font-size:26px;font-weight:800;letter-spacing:1px;direction:ltr;color:#f0f9ff}
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
"""

HEAD = """<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='38' fill='%2322d3ee'/></svg>">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css">
<style>""" + CSS + """</style></head><body><div class="card">
<div class="brand"><span class="dot"></span> افق امن ایرانیان</div>
"""

FOOT = """
<div class="foot">با ثبت تازه، IP قبلی شما خودکار حذف می‌شود.<br>هنگام ثبت، VPN یا تونل روشن نباشد.</div>
</div></body></html>"""


def page_user(ip, msg="", kind="ok"):
    m = ('<div class="msg %s">%s</div>' % (kind, html.escape(msg))) if msg else ""
    return (HEAD.replace("__TITLE__", "ثبت IP — افق امن ایرانیان")
            + "<h1>ثبت IP شما</h1>"
            + '<p class="sub">هر وقت IP اینترنت‌تان عوض شد، کدتان را بزنید تا دسترسی‌تان بدون وقفه ادامه پیدا کند.</p>'
            + '<div class="ipbox"><div class="lbl">IP فعلی شما</div><div class="ip">%s</div></div>'
            % html.escape(ip)
            + '<form method="post" action="/register">'
            + '<label for="code">کد ثبت شما</label>'
            + '<input id="code" name="code" placeholder="saman_ghannadzadeh" autocomplete="off" required>'
            + '<button type="submit">ثبت این IP</button></form>'
            + '<form method="post" action="/status">'
            + '<input type="hidden" name="code" id="code2">'
            + '<button class="ghost" type="submit" onclick="document.getElementById(\'code2\').value=document.getElementById(\'code\').value">وضعیت کد من</button></form>'
            + m + FOOT)


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

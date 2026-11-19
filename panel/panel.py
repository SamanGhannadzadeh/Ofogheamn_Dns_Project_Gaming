#!/usr/bin/env python3
"""Ofogheamn DNS — web management panel (Python stdlib only).

Serves a Persian RTL admin UI + a small JSON API for:
  * service status (DNS / proxy / panel), restart actions
  * public/private mode switch + source allowlist (iptables)
  * Smart-DNS hijack rules (hijack.conf)
  * gaming / CoD domain lists
  * proxy user accounts (sing-box config is regenerated)
  * log tails and the CoD endpoint test

Config: /etc/ofogheamn-dns/panel.conf  (port, bind, password_hash)
The password itself is never stored — only its SHA-256.
"""
import hashlib
import ipaddress
import json
import os
import re
import secrets
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ETC = os.environ.get("OFOGH_ETC", "/etc/ofogheamn-dns")
LOGDIR = "/var/log/ofogheamn-dns"
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$")
USER_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def conf_get(key, default=""):
    try:
        with open(os.path.join(ETC, "panel.conf"), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith(key + "="):
                    return line.strip().split("=", 1)[1]
    except OSError:
        pass
    return default


PORT = int(conf_get("port", "8080") or "8080")
BIND = conf_get("bind", "0.0.0.0") or "0.0.0.0"
PROXY_PORT = int(os.environ.get("OFOGH_PROXY_PORT", "2080"))
SESSIONS = {}
LOGIN_FAILS = {}


def svc_state(name):
    try:
        out = subprocess.run(["systemctl", "is-active", name],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def svc_do(action, name):
    try:
        out = subprocess.run(["systemctl", action, name],
                             capture_output=True, text=True, timeout=30)
        return out.returncode == 0, (out.stdout + out.stderr).strip()[-400:]
    except Exception as exc:  # systemctl absent (dev/test)
        return False, str(exc)


def read_lines(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def write_lines(path, lines):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------- hijack rules ----------------
def hijack_list():
    rules = []
    for line in read_lines(os.path.join(ETC, "hijack.conf")):
        m = re.match(r"^(address|cname)\s+/([^/]+)/(.+)$", line.strip())
        if m:
            rules.append({"type": m.group(1), "domain": m.group(2), "target": m.group(3)})
    return rules


def hijack_save(rules):
    path = os.path.join(ETC, "hijack.conf")
    kept = [ln for ln in read_lines(path)
            if not re.match(r"^(address|cname)\s+/", ln.strip())]
    kept += [f"{r['type']} /{r['domain']}/{r['target']}" for r in rules]
    write_lines(path, kept)


# ---------------- domain lists ----------------
def domains_get(name):
    return [ln.strip() for ln in read_lines(os.path.join(ETC, "lists", f"{name}.domains"))
            if ln.strip() and not ln.strip().startswith("#")]


def domains_save(name, doms):
    path = os.path.join(ETC, "lists", f"{name}.domains")
    kept = [ln for ln in read_lines(path) if ln.strip().startswith("#")]
    write_lines(path, kept + sorted(set(doms)))


# ---------------- mode / allowlist ----------------
def mode_get():
    mode = "public"
    for ln in read_lines(os.path.join(ETC, "mode.conf")):
        if ln.startswith("mode="):
            mode = ln.split("=", 1)[1].strip()
    allow = [ln.strip() for ln in read_lines(os.path.join(ETC, "allowlist.txt"))
             if ln.strip() and not ln.strip().startswith("#")]
    return mode, allow


def mode_set(mode, allow):
    write_lines(os.path.join(ETC, "mode.conf"), [f"mode={mode}"])
    write_lines(os.path.join(ETC, "allowlist.txt"), allow)
    script = "/usr/local/bin/ofogheamn-firewall"
    if os.path.exists(script):
        out = subprocess.run(["bash", script], capture_output=True, text=True, timeout=30)
        return out.returncode == 0, (out.stdout + out.stderr).strip()[-300:]
    return True, "mode saved (firewall script not installed; applied at install)"


# ---------------- proxy users ----------------
def proxy_users():
    try:
        with open(os.path.join(ETC, "proxy-users.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def proxy_save(users):
    path = os.path.join(ETC, "proxy-users.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(users, fh, indent=1)
    os.chmod(path, 0o600)
    cfg = {
        "log": {"level": "info", "output": f"{LOGDIR}/singbox.log", "timestamp": True},
        "inbounds": [{
            "type": "mixed", "tag": "ofogh-mixed", "listen": "::",
            "listen_port": PROXY_PORT, "udp_fragment": True,
            "users": [{"username": u["user"], "password": u["pass"]} for u in users],
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}],
        "route": {"final": "direct"},
    }
    out = os.path.join(ETC, "singbox.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.chmod(out, 0o600)


def _wg_peers():
    try:
        with open(os.path.join(ETC, "wg-peers.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def top_domains(n=12):
    path = os.path.join(LOGDIR, "smartdns.log")
    counts = {}
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 2_000_000))
            text = fh.read().decode("utf-8", "replace")
        for m in re.finditer(r"request: ([a-zA-Z0-9.-]+), qtype", text):
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    except OSError:
        pass
    return sorted(counts.items(), key=lambda kv: -kv[1])[:n]


def status():
    mode, allow = mode_get()
    ver = ""
    try:
        out = subprocess.run(["/usr/local/bin/smartdns", "-v"],
                             capture_output=True, text=True, timeout=5)
        ver = (out.stdout + out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else ""
    except Exception:
        pass
    return {
        "dns": svc_state("ofogheamn-dns"),
        "proxy": svc_state("ofogheamn-proxy"),
        "wg": svc_state("ofogheamn-wg"),
        "wg_peers": [p.get("name") for p in _wg_peers()],
        "warmup_timer": svc_state("cod-warmup.timer"),
        "mode": mode, "allowlist": allow,
        "smartdns_version": ver,
        "proxy_port": PROXY_PORT, "panel_port": PORT,
        "hijack_count": len(hijack_list()),
        "blocklist_count": sum(1 for ln in read_lines(os.path.join(ETC, "blocklist.conf"))
                               if ln.startswith("address /")),
        "cod_count": len(domains_get("cod")), "gaming_count": len(domains_get("gaming")),
        "proxy_users": [u["user"] for u in proxy_users()],
        "top_domains": top_domains(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "OfogheamnPanel/1.0"

    def log_message(self, *args):
        pass

    # ---------- plumbing ----------
    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def _authed(self):
        tok = ""
        for part in (self.headers.get("Cookie") or "").split(";"):
            if part.strip().startswith("ofogh_session="):
                tok = part.strip().split("=", 1)[1]
        exp = SESSIONS.get(tok, 0)
        if exp and exp > time.time():
            return True
        SESSIONS.pop(tok, None)
        return False

    # ---------- routes ----------
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not path.startswith("/api/"):
            return self._json(404, {"error": "not found"})
        if not self._authed():
            return self._json(401, {"error": "login required"})
        qs = parse_qs(urlparse(self.path).query)
        if path == "/api/status":
            return self._json(200, status())
        if path == "/api/hijack":
            return self._json(200, {"rules": hijack_list()})
        if path == "/api/domains":
            name = (qs.get("list") or ["gaming"])[0]
            if name not in ("gaming", "cod"):
                return self._json(400, {"error": "bad list"})
            return self._json(200, {"domains": domains_get(name)})
        if path == "/api/logs":
            svc = (qs.get("svc") or ["dns"])[0]
            fn = "smartdns.log" if svc == "dns" else "singbox.log"
            lines = read_lines(os.path.join(LOGDIR, fn))[-120:]
            return self._json(200, {"lines": lines})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        data = self._body()
        if path == "/api/login":
            ip = self.client_address[0]
            fails, last = LOGIN_FAILS.get(ip, (0, 0))
            if fails >= 5 and time.time() - last < 30:
                return self._json(429, {"error": "too many attempts, wait 30s"})
            want = conf_get("password_hash")
            got = hashlib.sha256(str(data.get("password", "")).encode()).hexdigest()
            if want and secrets.compare_digest(got, want):
                LOGIN_FAILS.pop(ip, None)
                tok = secrets.token_hex(24)
                SESSIONS[tok] = time.time() + 12 * 3600
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie",
                                 f"ofogh_session={tok}; HttpOnly; SameSite=Lax; Path=/")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            LOGIN_FAILS[ip] = (fails + 1, time.time())
            return self._json(403, {"error": "wrong password"})
        if not self._authed():
            return self._json(401, {"error": "login required"})
        if self.headers.get("X-Requested-With") != "fetch":
            return self._json(400, {"error": "missing X-Requested-With"})

        if path == "/api/logout":
            return self._json(200, {"ok": True})

        if path == "/api/action":
            act = data.get("action", "")
            if act == "restart-dns":
                ok, out = svc_do("restart", "ofogheamn-dns")
                return self._json(200, {"ok": ok, "out": out})
            if act == "restart-proxy":
                ok, out = svc_do("restart", "ofogheamn-proxy")
                return self._json(200, {"ok": ok, "out": out})
            if act == "cod-test":
                try:
                    out = subprocess.run(["ofogheamn-dns", "cod-test"],
                                         capture_output=True, text=True, timeout=60)
                    return self._json(200, {"ok": True, "out": (out.stdout + out.stderr)[-2000:]})
                except Exception as exc:
                    return self._json(200, {"ok": False, "out": str(exc)})
            if act == "warmup":
                ok, out = svc_do("start", "cod-warmup.service")
                return self._json(200, {"ok": ok, "out": out})
            if act == "update-blocklist":
                try:
                    out = subprocess.run(["update-blocklist"],
                                         capture_output=True, text=True, timeout=180)
                    return self._json(200, {"ok": out.returncode == 0,
                                            "out": (out.stdout + out.stderr)[-800:]})
                except Exception as exc:
                    return self._json(200, {"ok": False, "out": str(exc)})
            return self._json(400, {"error": "bad action"})

        if path == "/api/hijack":
            dom, tgt = str(data.get("domain", "")).lower(), str(data.get("target", ""))
            if not DOMAIN_RE.match(dom):
                return self._json(400, {"error": "bad domain"})
            try:
                ipaddress.ip_address(tgt)
            except ValueError:
                if not DOMAIN_RE.match(tgt):
                    return self._json(400, {"error": "target must be an IP or a domain (cname)"})
            rules = [r for r in hijack_list() if r["domain"] != dom]
            rules.append({"type": "address" if tgt[0].isdigit() else "cname",
                          "domain": dom, "target": tgt})
            hijack_save(rules)
            ok, out = svc_do("restart", "ofogheamn-dns")
            return self._json(200, {"ok": ok, "out": out, "rules": rules})

        if path == "/api/hijack/delete":
            dom = str(data.get("domain", "")).lower()
            rules = [r for r in hijack_list() if r["domain"] != dom]
            hijack_save(rules)
            ok, out = svc_do("restart", "ofogheamn-dns")
            return self._json(200, {"ok": ok, "out": out, "rules": rules})

        if path == "/api/domains":
            name, dom, op = data.get("list"), str(data.get("domain", "")).lower(), data.get("op")
            if name not in ("gaming", "cod") or not DOMAIN_RE.match(dom):
                return self._json(400, {"error": "bad input"})
            doms = domains_get(name)
            if op == "add" and dom not in doms:
                doms.append(dom)
            elif op == "del":
                doms = [d for d in doms if d != dom]
            else:
                return self._json(400, {"error": "bad op"})
            domains_save(name, doms)
            ok, out = svc_do("restart", "ofogheamn-dns")
            return self._json(200, {"ok": ok, "out": out, "domains": domains_get(name)})

        if path == "/api/mode":
            mode = data.get("mode")
            allow = data.get("allowlist", [])
            if mode not in ("public", "private") or not isinstance(allow, list):
                return self._json(400, {"error": "bad mode"})
            clean = []
            for net in allow:
                try:
                    clean.append(str(ipaddress.ip_network(str(net).strip(), strict=False)))
                except ValueError:
                    return self._json(400, {"error": f"bad network: {net}"})
            ok, out = mode_set(mode, clean)
            return self._json(200, {"ok": ok, "out": out, "mode": mode, "allowlist": clean})

        if path == "/api/wg":
            op, name = data.get("op"), str(data.get("name", ""))
            if not USER_RE.match(name):
                return self._json(400, {"error": "bad name"})
            tool = "/usr/local/bin/ofogheamn-wg-peer"
            try:
                if op == "add":
                    out = subprocess.run([tool, "add", name],
                                         capture_output=True, text=True, timeout=20)
                    svc_do("restart", "ofogheamn-wg")
                    return self._json(200, {"ok": out.returncode == 0,
                                            "config": out.stdout,
                                            "peers": [p.get("name") for p in _wg_peers()]})
                if op == "del":
                    out = subprocess.run([tool, "remove", name],
                                         capture_output=True, text=True, timeout=20)
                    svc_do("restart", "ofogheamn-wg")
                    return self._json(200, {"ok": out.returncode == 0,
                                            "peers": [p.get("name") for p in _wg_peers()]})
            except Exception as exc:
                return self._json(200, {"ok": False, "out": str(exc)})
            return self._json(400, {"error": "bad op"})

        if path == "/api/proxy/users":
            op, user = data.get("op"), str(data.get("user", ""))
            users = proxy_users()
            if op == "add":
                pw = str(data.get("pass", ""))
                if not USER_RE.match(user) or len(pw) < 4:
                    return self._json(400, {"error": "bad user or short password"})
                users = [u for u in users if u["user"] != user]
                users.append({"user": user, "pass": pw})
            elif op == "del":
                users = [u for u in users if u["user"] != user]
            else:
                return self._json(400, {"error": "bad op"})
            proxy_save(users)
            ok, out = svc_do("restart", "ofogheamn-proxy")
            return self._json(200, {"ok": ok, "out": out,
                                    "users": [u["user"] for u in users]})
        return self._json(404, {"error": "not found"})


def main():
    if not conf_get("password_hash"):
        print("panel.conf has no password_hash — run install.sh or "
              "'ofogheamn-dns panel-password <new>' first")
        return 1
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"Ofogheamn panel on http://{BIND}:{PORT}")
    srv.serve_forever()
    return 0


PAGE = r"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>پنل مدیریت Ofogheamn DNS</title>
<style>
:root{--bg:#0b1220;--card:#131c2e;--line:#22314d;--txt:#e8eef7;--mut:#8fa3bf;--acc:#22c55e;--acc2:#38bdf8;--bad:#f87171}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font-family:Tahoma,'Segoe UI',sans-serif}
header{padding:14px 20px;background:var(--card);border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}
h1{font-size:18px;margin:0}.sub{color:var(--mut);font-size:12px}
main{max-width:980px;margin:0 auto;padding:16px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.card b{font-size:20px;display:block}.ok{color:var(--acc)}.bad{color:(--bad)}.bad{color:var(--bad)}
nav{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0}
nav button{background:var(--card);color:var(--txt);border:1px solid var(--line);border-radius:9px;padding:8px 14px;cursor:pointer}
nav button.on{border-color:var(--acc2);color:var(--acc2)}
section{display:none;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
section.on{display:block}
input,textarea,select{background:#0b1220;color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:8px;width:100%;margin:4px 0 10px}
button.act{background:var(--acc);color:#04150a;border:0;border-radius:8px;padding:9px 16px;cursor:pointer;font-weight:bold}
button.ghost{background:transparent;color:var(--mut);border:1px solid var(--line);border-radius:8px;padding:6px 10px;cursor:pointer}
table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid var(--line);padding:7px;text-align:right;font-size:13px}
pre{background:#0b1220;border:1px solid var(--line);border-radius:8px;padding:10px;overflow:auto;max-height:300px;font-size:11px;direction:ltr;text-align:left}
.row{display:flex;gap:8px}.row>*{flex:1}
#login{max-width:360px;margin:60px auto;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px}
.hide{display:none}.msg{color:var(--acc2);min-height:18px;font-size:13px}
</style></head><body>
<div id="login">
  <h1>🌐 Ofogheamn DNS</h1><p class="sub">پنل مدیریت سرور DNS و پروکسی گیمینگ</p>
  <label>رمز عبور مدیر</label>
  <input type="password" id="pw" autocomplete="current-password">
  <button class="act" style="width:100%" onclick="login()">ورود</button>
  <p class="msg" id="lmsg"></p>
</div>
<div id="app" class="hide">
<header><div><h1>🌐 Ofogheamn DNS — پنل مدیریت</h1><span class="sub" id="ver"></span></div>
<button class="ghost" onclick="logout()">خروج</button></header>
<main>
  <div class="cards" id="cards"></div>
  <nav>
    <button data-t="dash" class="on">داشبورد</button>
    <button data-t="hijack">هایجک / Smart DNS</button>
    <button data-t="domains">دامنه‌های گیمینگ</button>
    <button data-t="mode">حالت عمومی / خصوصی</button>
    <button data-t="proxy">پروکسی</button>
    <button data-t="wg">تونل گیمینگ (WireGuard)</button>
    <button data-t="logs">لاگ‌ها</button>
  </nav>
  <p class="msg" id="msg"></p>

  <section id="s-dash" class="on">
    <div class="row">
      <button class="act" onclick="act('restart-dns')">ری‌استارت DNS</button>
      <button class="act" onclick="act('restart-proxy')">ری‌استارت پروکسی</button>
      <button class="act" onclick="act('warmup')">گرم‌کردن کش کالاف</button>
      <button class="act" onclick="act('cod-test')">تست زندهٔ کالاف</button>
      <button class="act" onclick="act('update-blocklist')">به‌روزرسانی لیست مسدودی</button>
    </div>
    <h3>پرتکرارترین دامنه‌ها (از لاگ)</h3><div id="tops"></div>
    <pre id="out"></pre>
  </section>

  <section id="s-hijack">
    <div class="row"><input id="h-dom" placeholder="domain.com"><input id="h-tgt" placeholder="IP یا دامنهٔ مقصد"></div>
    <button class="act" onclick="hijackAdd()">افزودن قانون</button>
    <table id="h-table"></table>
  </section>

  <section id="s-domains">
    <label>لیست</label>
    <select id="d-list"><option value="cod">Call of Duty / Warzone</option><option value="gaming">گیمینگ عمومی</option></select>
    <div class="row"><input id="d-dom" placeholder="new-domain.com"><button class="act" onclick="domAdd()">افزودن</button></div>
    <table id="d-table"></table>
  </section>

  <section id="s-mode">
    <label>حالت DNS</label>
    <select id="m-mode"><option value="public">عمومی — همه می‌توانند کوئری بزنند</option>
    <option value="private">خصوصی — فقط شبکه‌های مجاز</option></select>
    <label>شبکه‌های مجاز (هر خط یک IP یا CIDR) — فقط در حالت خصوصی</label>
    <textarea id="m-allow" rows="5" placeholder="192.168.1.0/24&#10;203.0.113.7"></textarea>
    <button class="act" onclick="modeSave()">ذخیره و اعمال</button>
    <p class="sub">در حالت خصوصی، پورت‌های DNS (53 و 853 و 443) با فایروال فقط برای شبکه‌های بالا باز می‌ماند.</p>
  </section>

  <section id="s-proxy">
    <p id="p-info"></p>
    <div class="row"><input id="p-user" placeholder="نام کاربری"><input id="p-pass" placeholder="رمز"></div>
    <button class="act" onclick="proxyAdd()">افزودن / به‌روزرسانی کاربر</button>
    <table id="p-table"></table>
    <p class="sub">پروکسی از نوع Mixed است: HTTP و SOCKS5 روی یک پورت، با UDP برای بازی. در کلاینت‌ها: آدرس سرور + پورت + همین نام کاربری و رمز.</p>
  </section>

  <section id="s-wg">
    <p class="sub">مسیر کامل: دستگاه ← تونل ← این سرور (DNS + NAT) ← سرور بازی. کانفیگ ساخته‌شده را در اپ WireGuard گوشی/کامپیوتر وارد کن؛ برای کنسول، تونل را روی روتر (OpenWrt/MikroTik) ببند تا کل شبکه از همین مسیر برود.</p>
    <div class="row"><input id="w-name" placeholder="نام دستگاه، مثل ps5-home"><button class="act" onclick="wgAdd()">ساخت کانفیگ دستگاه</button></div>
    <table id="w-table"></table>
    <pre id="w-conf"></pre>
  </section>

  <section id="s-logs">
    <div class="row">
      <button class="ghost" onclick="loadLogs('dns')">لاگ DNS</button>
      <button class="ghost" onclick="loadLogs('proxy')">لاگ پروکسی</button>
    </div>
    <pre id="logbox"></pre>
  </section>
</main></div>
<script>
const $=id=>document.getElementById(id);
async function api(path,opt={}){opt.headers={'X-Requested-With':'fetch','Content-Type':'application/json'};const r=await fetch(path,opt);if(r.status===401){showLogin();throw 'unauth'}return r.json()}
function showLogin(){$('app').classList.add('hide');$('login').classList.remove('hide')}
function showApp(){$('login').classList.add('hide');$('app').classList.remove('hide');refresh()}
async function login(){const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:$('pw').value})});if(r.ok)showApp();else $('lmsg').textContent='رمز اشتباه است'}
async function logout(){await api('/api/logout',{method:'POST',body:'{}'});location.reload()}
function msg(t){$('msg').textContent=t||''}
async function refresh(){try{const s=await api('/api/status');
 $('ver').textContent=s.smartdns_version||'';
 const dot=v=>v==='active'?'<span class="ok">فعال</span>':'<span class="bad">'+v+'</span>';
 $('cards').innerHTML=
  '<div class="card">سرویس DNS<b>'+dot(s.dns)+'</b></div>'+
  '<div class="card">پروکسی (پورت '+s.proxy_port+')<b>'+dot(s.proxy)+'</b></div>'+
  '<div class="card">حالت<b>'+(s.mode==='public'?'عمومی':'خصوصی')+'</b></div>'+
  '<div class="card">قوانین هایجک<b>'+s.hijack_count+'</b></div>'+
  '<div class="card">دامنهٔ کالاف<b>'+s.cod_count+'</b></div>'+
  '<div class="card">دامنهٔ گیمینگ<b>'+s.gaming_count+'</b></div>'+
  '<div class="card">دامنهٔ مسدود<b>'+(s.blocklist_count||0)+'</b></div>';
 $('tops').innerHTML='<table>'+(s.top_domains||[]).map(x=>'<tr><td>'+x[0]+'</td><td>'+x[1]+'</td></tr>').join('')+'</table>';
 $('m-mode').value=s.mode;$('m-allow').value=(s.allowlist||[]).join('\n');
 $('p-info').textContent='کاربران فعلی: '+(s.proxy_users||[]).join('، ');
 $('p-table').innerHTML=(s.proxy_users||[]).map(u=>'<tr><td>'+u+'</td><td><button class="ghost" onclick="proxyDel(\''+u+'\')">حذف</button></td></tr>').join('');
 $('w-table').innerHTML=(s.wg_peers||[]).map(u=>'<tr><td>'+u+'</td><td><button class="ghost" onclick="wgDel(\''+u+'\')">حذف</button></td></tr>').join('');
 loadHijack();loadDomains();
}catch(e){}}
async function act(a){msg('در حال اجرا...');const r=await api('/api/action',{method:'POST',body:JSON.stringify({action:a})});$('out').textContent=r.out||'';msg(r.ok?'انجام شد':'خطا');refresh()}
async function loadHijack(){const r=await api('/api/hijack');$('h-table').innerHTML=r.rules.map(x=>'<tr><td>'+x.domain+'</td><td>'+x.target+'</td><td><button class="ghost" onclick="hijackDel(\''+x.domain+'\')">حذف</button></td></tr>').join('')}
async function hijackAdd(){const r=await api('/api/hijack',{method:'POST',body:JSON.stringify({domain:$('h-dom').value,target:$('h-tgt').value})});msg(r.error||'ذخیره شد');loadHijack();refresh()}
async function hijackDel(d){const r=await api('/api/hijack/delete',{method:'POST',body:JSON.stringify({domain:d})});loadHijack();refresh()}
async function loadDomains(){const l=$('d-list').value;const r=await api('/api/domains?list='+l);$('d-table').innerHTML=r.domains.map(d=>'<tr><td>'+d+'</td><td><button class="ghost" onclick="domDel(\''+d+'\')">حذف</button></td></tr>').join('')}
async function domAdd(){const r=await api('/api/domains',{method:'POST',body:JSON.stringify({list:$('d-list').value,domain:$('d-dom').value,op:'add'})});msg(r.error||'افزوده شد');loadDomains();refresh()}
async function domDel(d){await api('/api/domains',{method:'POST',body:JSON.stringify({list:$('d-list').value,domain:d,op:'del'})});loadDomains();refresh()}
$('d-list').addEventListener('change',loadDomains);
async function modeSave(){const allow=$('m-allow').value.split('\n').map(x=>x.trim()).filter(Boolean);const r=await api('/api/mode',{method:'POST',body:JSON.stringify({mode:$('m-mode').value,allowlist:allow})});msg(r.error||('اعمال شد: '+(r.out||'')));refresh()}
async function proxyAdd(){const r=await api('/api/proxy/users',{method:'POST',body:JSON.stringify({op:'add',user:$('p-user').value,pass:$('p-pass').value})});msg(r.error||'ذخیره شد');refresh()}
async function proxyDel(u){await api('/api/proxy/users',{method:'POST',body:JSON.stringify({op:'del',user:u})});refresh()}
async function wgAdd(){const r=await api('/api/wg',{method:'POST',body:JSON.stringify({op:'add',name:$('w-name').value})});if(r.config)$('w-conf').textContent=r.config;msg(r.error||'ساخته شد');refresh()}
async function wgDel(n){await api('/api/wg',{method:'POST',body:JSON.stringify({op:'del',name:n})});refresh()}
async function loadLogs(s){const r=await api('/api/logs?svc='+s);$('logbox').textContent=(r.lines||[]).join('\n')}
document.querySelectorAll('nav button').forEach(b=>b.addEventListener('click',()=>{
 document.querySelectorAll('nav button').forEach(x=>x.classList.remove('on'));b.classList.add('on');
 document.querySelectorAll('section').forEach(x=>x.classList.remove('on'));$('s-'+b.dataset.t).classList.add('on');}));
api('/api/status').then(()=>showApp()).catch(()=>showLogin());
</script></body></html>
"""


if __name__ == "__main__":
    raise SystemExit(main())

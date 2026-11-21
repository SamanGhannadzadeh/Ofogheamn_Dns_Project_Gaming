#!/usr/bin/env python3
"""Ofogheamn DNS — web management panel (Python stdlib only).

Serves a Persian RTL admin UI + a small JSON API for:
  * service status (DNS / proxy / panel / VPN), restart actions
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
# Since v1.9 a hijack rule is a PAIR of lines (the A answer and
# an AAAA answer — without the second line, dual-stack clients
# leak past the rule). The panel pairs them back into one rule:
# target = IPv4 (or cname target), target6 = real IPv6 or ""
# with v6_blocked=True when the AAAA line is the "::" plug.
def hijack_list():
    by, order = {}, []
    for line in read_lines(os.path.join(ETC, "hijack.conf")):
        m = re.match(r"^(address|cname)\s+/([^/]+)/(.+)$", line.strip())
        if not m:
            continue
        typ, dom, tgt = m.groups()
        if dom not in by:
            by[dom] = {"type": typ, "domain": dom, "target": "",
                       "target6": "", "v6_blocked": False}
            order.append(dom)
        rule = by[dom]
        if typ == "cname":
            rule["type"] = "cname"
            rule["target"] = tgt
            continue
        try:
            is6 = ipaddress.ip_address(tgt).version == 6
        except ValueError:
            is6 = False
        if is6:
            if tgt == "::":
                rule["v6_blocked"] = True
            else:
                rule["target6"] = tgt
        else:
            rule["target"] = tgt
    return [by[d] for d in order]


def hijack_save(rules):
    path = os.path.join(ETC, "hijack.conf")
    kept = [ln for ln in read_lines(path)
            if not re.match(r"^(address|cname)\s+/", ln.strip())]
    for r in rules:
        if r["type"] == "cname":
            kept.append(f"cname /{r['domain']}/{r['target']}")
            continue
        if r.get("target"):
            kept.append(f"address /{r['domain']}/{r['target']}")
        t6 = r.get("target6") or ("::" if r.get("target") or r.get("v6_blocked") else "")
        if t6:
            kept.append(f"address /{r['domain']}/{t6}")
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


# ---------------- VPN (L2TP/IPsec + PPTP) ----------------
def vpn_get():
    cfg = {}
    try:
        with open(os.path.join(ETC, "vpn.conf"), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    cfg[k] = v
    except OSError:
        pass
    return {
        "service": svc_state("ofogheamn-vpn"),
        "user": cfg.get("user", ""),
        "pass": cfg.get("pass", ""),
        "psk": cfg.get("psk", ""),
        "l2tp_pool": cfg.get("l2tp_pool", "10.67.0.0/24"),
        "pptp_pool": cfg.get("pptp_pool", "10.68.0.0/24"),
    }


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
    # singbox.json is generated by gen-singbox-config.py — the
    # single source of truth the CLI and the installer also use.
    # This function used to hand-write a second, divergent config:
    # same users, but it silently dropped the VLESS+REALITY inbound
    # whenever anyone edited proxy users in the panel after
    # enabling REALITY from the CLI (v1.4 fix). The inline writer
    # below remains only as a fallback for dev checkouts where the
    # generator is not installed.
    gen = "/usr/local/lib/ofogheamn-dns/gen-singbox-config.py"
    if os.path.exists(gen):
        env = dict(os.environ, OFOGH_ETC=ETC)
        subprocess.run(["python3", gen], env=env,
                       capture_output=True, text=True, timeout=20)
        return
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


MESH_CONF = os.path.join(ETC, "mesh.json")
MESH_STATE = "/run/ofogheamn-mesh-state.json"


def mesh_get():
    try:
        with open(MESH_CONF, encoding="utf-8") as fh:
            c = json.load(fh)
    except Exception:
        c = {}
    c.setdefault("enabled", False)
    c.setdefault("peers", [])
    c.setdefault("key", "")
    st = {}
    try:
        with open(MESH_STATE, encoding="utf-8") as fh:
            st = json.load(fh)
    except Exception:
        pass
    return {
        "enabled": bool(c["enabled"]),
        "key": c.get("key", ""),
        "mesh_ip": c.get("mesh_ip", ""),
        "port": c.get("port", 51821),
        "wg_port": c.get("wg_port", 51822),
        "peers": c["peers"],
        "service": svc_state("ofogheamn-mesh"),
        "state": st,
    }


def mesh_save(c):
    with open(MESH_CONF, "w", encoding="utf-8") as fh:
        json.dump(c, fh, indent=1)


def mesh_load_raw():
    try:
        with open(MESH_CONF, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


# ---------------- transports (v1.13: full panel parity) ----------------
def _json_file(name):
    try:
        with open(os.path.join(ETC, name), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def transports_get():
    """Read-only state of every optional transport, mirroring
    the JSON state files the CLI writes. Toggling happens
    through the CLI itself (see /api/feature) — one source of
    truth, no second implementation to drift."""
    t = {}
    c = _json_file("console.json")
    t["console"] = {"on": bool(c), "port": (c or {}).get("port", 2081)}
    h = _json_file("hysteria2.json")
    t["hysteria2"] = {"on": bool(h), "port": (h or {}).get("port", 443),
                      "obfs": (h or {}).get("obfs", ""),
                      "hop_range": (h or {}).get("hop_range", "")}
    u = _json_file("tuic.json")
    t["tuic"] = {"on": bool(u), "port": (u or {}).get("port", 8443)}
    a = _json_file("anytls.json")
    t["anytls"] = {"on": bool(a), "port": (a or {}).get("port", 8443)}
    r = _json_file("reality.json")
    rc = _json_file("reality-clients.json") or {}
    t["reality"] = {"on": bool(r), "port": (r or {}).get("port", 443),
                    "server_name": (r or {}).get("server_name", ""),
                    "public_key": rc.get("public_key", ""),
                    "short_id": rc.get("short_id", ""),
                    "clients": rc.get("clients", [])}
    rec = any(ln.startswith("server ")
              for ln in read_lines(os.path.join(ETC, "recursive.conf")))
    t["recursive"] = {"on": rec, "port": 5335}
    return t


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


_health_cache = {"t": 0, "data": None}


def health_get():
    import time as _t
    now = _t.time()
    if _health_cache["data"] is not None and now - _health_cache["t"] < 60:
        return _health_cache["data"]
    data = {"healthy": None, "problems": ["health-script-missing"]}
    try:
        out = subprocess.run(
            ["python3", "/usr/local/bin/ofogheamn-health.py", "--json"],
            capture_output=True, text=True, timeout=15)
        data = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        pass
    _health_cache.update(t=now, data=data)
    return data


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
        "vpn": vpn_get(),
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
        "mesh_enabled": mesh_get()["enabled"],
        "mesh_best": (mesh_get()["state"] or {}).get("best", ""),
        "mesh_service": svc_state("ofogheamn-mesh"),
        "transports": transports_get(),
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
        if path == "/api/health":
            return self._json(200, health_get())
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
        if path == "/api/mesh":
            return self._json(200, mesh_get())
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
            if act == "restart-vpn":
                ok, out = svc_do("restart", "ofogheamn-vpn")
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
            if act == "apply-firewall":
                try:
                    out = subprocess.run(["ofogheamn-firewall"],
                                         capture_output=True, text=True, timeout=60)
                    return self._json(200, {"ok": out.returncode == 0,
                                            "out": (out.stdout + out.stderr)[-800:]})
                except Exception as exc:
                    return self._json(200, {"ok": False, "out": str(exc)})
            if act in ("region", "bench", "backup"):
                limit = 240 if act == "bench" else 120
                try:
                    out = subprocess.run(["ofogheamn-dns", act],
                                         capture_output=True, text=True, timeout=limit)
                    return self._json(200, {"ok": out.returncode == 0,
                                            "out": (out.stdout + out.stderr)[-2000:]})
                except Exception as exc:
                    return self._json(200, {"ok": False, "out": str(exc)})
            return self._json(400, {"error": "bad action"})

        if path == "/api/mesh":
            op = data.get("op")
            c = mesh_load_raw()
            c.setdefault("enabled", False)
            c.setdefault("peers", [])
            c.setdefault("port", 51821)
            c.setdefault("wg_port", 51822)
            if op == "on":
                if not c.get("key"):
                    c["key"] = secrets.token_hex(16)
                if not c.get("mesh_ip"):
                    c["mesh_ip"] = "10.99.0.1"
                c["enabled"] = True
                mesh_save(c)
                svc_do("enable", "ofogheamn-mesh")
                ok, out = svc_do("start", "ofogheamn-mesh")
                return self._json(200, {"ok": ok, "out": out, "mesh": mesh_get()})
            if op == "off":
                c["enabled"] = False
                mesh_save(c)
                svc_do("stop", "ofogheamn-mesh")
                ok, out = svc_do("disable", "ofogheamn-mesh")
                return self._json(200, {"ok": ok, "out": out, "mesh": mesh_get()})
            if op == "key":
                key = str(data.get("key", "")).strip()
                if len(key) < 8:
                    return self._json(400, {"error": "key too short (min 8)"})
                c["key"] = key
                mesh_save(c)
                if c["enabled"]:
                    svc_do("restart", "ofogheamn-mesh")
                return self._json(200, {"ok": True, "mesh": mesh_get()})
            if op == "add-peer":
                name = str(data.get("name", ""))
                endpoint = str(data.get("endpoint", "")).strip()
                pubkey = str(data.get("pubkey", "")).strip()
                mip = str(data.get("mesh_ip", "")).strip()
                if not USER_RE.match(name):
                    return self._json(400, {"error": "bad name"})
                if not re.match(r"^[A-Za-z0-9.-]+:\d{2,5}$", endpoint):
                    return self._json(400, {"error": "endpoint must be host:port"})
                if not re.match(r"^[A-Za-z0-9+/]{43}=$", pubkey):
                    return self._json(400, {"error": "bad wireguard public key"})
                try:
                    ipaddress.ip_address(mip)
                except ValueError:
                    return self._json(400, {"error": "bad mesh ip"})
                c["peers"] = [p for p in c["peers"] if p.get("name") != name]
                c["peers"].append({"name": name, "endpoint": endpoint,
                                   "pubkey": pubkey, "mesh_ip": mip})
                mesh_save(c)
                if c["enabled"]:
                    svc_do("restart", "ofogheamn-mesh")
                return self._json(200, {"ok": True, "mesh": mesh_get()})
            if op == "del-peer":
                name = str(data.get("name", ""))
                c["peers"] = [p for p in c["peers"] if p.get("name") != name]
                mesh_save(c)
                if c["enabled"]:
                    svc_do("restart", "ofogheamn-mesh")
                return self._json(200, {"ok": True, "mesh": mesh_get()})
            return self._json(400, {"error": "bad op"})

        if path == "/api/hijack":
            dom, tgt = str(data.get("domain", "")).lower(), str(data.get("target", ""))
            if not DOMAIN_RE.match(dom):
                return self._json(400, {"error": "bad domain"})
            # Classify by parse, not by first character: an IPv6
            # target starting with a hex letter or ':' used to be
            # written as a cname rule, corrupting hijack.conf
            # (v1.4 fix).
            try:
                ipaddress.ip_address(tgt)
                rtype = "address"
            except ValueError:
                if not DOMAIN_RE.match(tgt):
                    return self._json(400, {"error": "target must be an IP or a domain (cname)"})
                rtype = "cname"
            t6 = str(data.get("target6", "")).strip()
            if t6:
                try:
                    if ipaddress.ip_address(t6).version != 6:
                        raise ValueError
                except ValueError:
                    return self._json(400, {"error": "target6 must be an IPv6 address"})
            rules = [r for r in hijack_list() if r["domain"] != dom]
            rules.append({"type": rtype, "domain": dom, "target": tgt,
                          "target6": t6 if rtype == "address" else "",
                          "v6_blocked": False})
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

        if path == "/api/feature":
            # Every optional transport is toggled by the CLI —
            # the panel is a remote control, never a second
            # implementation (the v1.4 lesson).
            feat = str(data.get("feature", ""))
            op = str(data.get("op", ""))
            if feat not in ("console", "hysteria2", "tuic", "anytls",
                            "reality", "recursive"):
                return self._json(400, {"error": "bad feature"})
            if op not in ("enable", "disable", "hop", "obfs"):
                return self._json(400, {"error": "bad op"})
            args = ["ofogheamn-dns", feat, op]
            if op == "enable" and data.get("port"):
                try:
                    port = int(data["port"])
                    if not 1 <= port <= 65535:
                        raise ValueError
                except (TypeError, ValueError):
                    return self._json(400, {"error": "bad port"})
                args.append(str(port))
            if feat == "hysteria2" and op == "hop":
                rng = str(data.get("range", "")).strip()
                if rng != "off" and not re.match(r"^\d{2,5}-\d{2,5}$", rng):
                    return self._json(400, {"error": "bad range"})
                args.append(rng)
            if feat == "hysteria2" and op == "obfs":
                if data.get("obfs") not in ("gecko", "salamander", "off"):
                    return self._json(400, {"error": "bad obfs"})
                args.append(str(data["obfs"]))
            if op in ("hop", "obfs") and feat != "hysteria2":
                return self._json(400, {"error": "hop/obfs are hysteria2-only"})
            try:
                out = subprocess.run(args, capture_output=True, text=True, timeout=90)
                return self._json(200, {"ok": out.returncode == 0,
                                        "out": (out.stdout + out.stderr)[-1200:]})
            except Exception as exc:
                return self._json(200, {"ok": False, "out": str(exc)})

        if path == "/api/vpn-creds":
            op = data.get("op")
            if op == "user":
                u, p = str(data.get("user", "")), str(data.get("pass", ""))
                if not USER_RE.match(u) or len(p) < 4:
                    return self._json(400, {"error": "bad user or short password"})
                args = ["ofogheamn-dns", "vpn", "set-user", u, p]
            elif op == "psk":
                psk = str(data.get("psk", ""))
                if len(psk) < 4:
                    return self._json(400, {"error": "short psk"})
                args = ["ofogheamn-dns", "vpn", "set-psk", psk]
            else:
                return self._json(400, {"error": "bad op"})
            try:
                out = subprocess.run(args, capture_output=True, text=True, timeout=60)
                return self._json(200, {"ok": out.returncode == 0,
                                        "out": (out.stdout + out.stderr)[-600:]})
            except Exception as exc:
                return self._json(200, {"ok": False, "out": str(exc)})

        if path == "/api/password":
            cur = hashlib.sha256(str(data.get("current", "")).encode()).hexdigest()
            want = conf_get("password_hash")
            if not want or not secrets.compare_digest(cur, want):
                return self._json(403, {"error": "current password wrong"})
            new = str(data.get("new", ""))
            if len(new) < 8:
                return self._json(400, {"error": "new password too short (min 8)"})
            path_conf = os.path.join(ETC, "panel.conf")
            lines = [ln for ln in read_lines(path_conf)
                     if not ln.startswith("password_hash=")]
            lines.append("password_hash=" + hashlib.sha256(new.encode()).hexdigest())
            write_lines(path_conf, lines)
            os.chmod(path_conf, 0o600)
            return self._json(200, {"ok": True})
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
.card b{font-size:20px;display:block}.ok{color:var(--acc)}.bad{color:var(--bad)}
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
    <button data-t="transports">ترنسپورت‌ها</button>
    <button data-t="wg">تونل گیمینگ (WireGuard)</button>
    <button data-t="vpn">VPN ‏(L2TP/PPTP)</button>
    <button data-t="mesh">مش (اتصال نودها)</button>
    <button data-t="logs">لاگ‌ها</button>
  </nav>
  <p class="msg" id="msg"></p>

  <section id="s-dash" class="on">
    <div class="row">
      <button class="act" onclick="act('restart-dns')">ری‌استارت DNS</button>
      <button class="act" onclick="act('restart-proxy')">ری‌استارت پروکسی</button>
      <button class="act" onclick="act('warmup')">گرم‌کردن کش کالاف</button>
      <button class="act" onclick="act('cod-test')">تست زندهٔ کالاف</button>
      <button class="act" onclick="act('region')">گزارش منطقه</button>
      <button class="act" onclick="act('bench')">بنچمارک</button>
      <button class="act" onclick="act('backup')">پشتیبان‌گیری</button>
      <button class="act" onclick="act('update-blocklist')">به‌روزرسانی لیست مسدودی</button>
      <button class="act" onclick="act('apply-firewall')">اعمال دوبارهٔ فایروال</button>
    </div>
    <h3>پرتکرارترین دامنه‌ها (از لاگ)</h3><div id="tops"></div>
    <pre id="out"></pre>
    <h3>تغییر رمز مدیر پنل</h3>
    <div class="row"><input type="password" id="pw-cur" placeholder="رمز فعلی"><input type="password" id="pw-new" placeholder="رمز تازه (حداقل ۸ حرف)"></div>
    <button class="act" onclick="pwChange()">تغییر رمز</button>
  </section>

  <section id="s-transports">
    <p class="sub">همهٔ مسیرهای ورودی اختیاری نود از همین‌جا کنترل می‌شوند؛ پنل فقط ریموتِ همان فرمان‌های CLI است و منطق دومی ندارد. روشن‌کردن هر کدام، پورتش را هم در فایروال (طبق حالت عمومی/خصوصی) باز می‌کند.</p>
    <div id="t-list"></div>
    <h3>هایستریا۲ — تنظیمات پیشرفته</h3>
    <div class="row"><input id="t-hop" placeholder="بازهٔ هاپ، مثل 20000-30000 یا off" dir="ltr"><button class="act" onclick="featureOp('hysteria2','hop')">اعمال هاپ</button></div>
    <div class="row"><select id="t-obfs"><option value="gecko">Gecko (پیشنهاد پژوهش ۲۰۲۶)</option><option value="salamander">Salamander</option><option value="off">بدون ابهام</option></select><button class="act" onclick="featureOp('hysteria2','obfs')">اعمال ابهام</button></div>
    <h3>REALITY — اطلاعات اتصال کلاینت</h3>
    <pre id="t-reality"></pre>
    <pre id="t-out"></pre>
  </section>

  <section id="s-hijack">
    <div class="row"><input id="h-dom" placeholder="domain.com"><input id="h-tgt" placeholder="IP یا دامنهٔ مقصد"><input id="h-tgt6" placeholder="IPv6 مقصد (اختیاری)"></div>
    <button class="act" onclick="hijackAdd()">افزودن قانون</button>
    <p class="sub">هر قانون دوستونی ذخیره می‌شود: اگر IPv6 ندهی، ستون AAAA با :: بسته می‌شود تا کلاینت دوستونی از کنار قانون رد نشود.</p>
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

  <section id="s-vpn">
    <p class="sub">برای دستگاه‌هایی که اپ WireGuard ندارند: ویندوز، اندروید، آیفون (فقط L2TP) و روترها L2TP/IPsec را بومی دارند و PPTP برای دستگاه‌های قدیمی است. مسیر مثل تونل WireGuard است: کلاینت ← این نود (DNS + NAT) ← اینترنت/بازی. راهنمای وصل‌شدن قدم‌به‌قدم: docs/VPN.fa.md در مخزن پروژه.</p>
    <p id="vpn-info"></p>
    <table id="vpn-table"></table>
    <div style="margin-top:10px"><button class="act" onclick="act('restart-vpn')">ری‌استارت VPN</button></div>
    <h3>تغییر اعتبار VPN</h3>
    <div class="row"><input id="v-user" placeholder="نام کاربری تازه"><input id="v-pass" placeholder="رمز تازه"></div>
    <button class="act" onclick="vpnCreds('user')">ذخیرهٔ نام کاربری و رمز</button>
    <div class="row"><input id="v-psk" placeholder="PSK تازه"><button class="act" onclick="vpnCreds('psk')">ذخیرهٔ PSK</button></div>
    <p class="sub">⚠️ <b>هشدار:</b> نام کاربری، رمز و PSK پیش‌فرض عمومی‌اند و هر کسی می‌داند؛ قبل از استفادهٔ واقعی حتماً عوضشان کن: <span dir="ltr">ofogheamn-dns vpn set-user &lt;user&gt; &lt;pass&gt;</span> و <span dir="ltr">ofogheamn-dns vpn set-psk &lt;new&gt;</span> — فایل مرجع: <span dir="ltr">/etc/ofogheamn-dns/vpn.conf</span>. PPTP ذاتاً ضعیف است؛ هر جا L2TP/IPsec می‌شود، همان را استفاده کن.</p>
  </section>

  <section id="s-mesh">
    <p class="sub">مش یعنی اتصال نودها به هم: هر نود پینگ خودش تا سرورهای بازی و تا همتاهایش را اندازه می‌گیرد؛ اگر جمعِ «من ← همتا» + «همتا ← بازی» از مسیر مستقیم کمتر بود، خروجی از همان همتا می‌رود. فقط به نودی وصل می‌شود که او هم مش را روشن کرده باشد.</p>
    <p id="mesh-info"></p>
    <div class="row">
      <button class="act" onclick="meshSet('on')">روشن‌کردن مش</button>
      <button class="ghost" onclick="meshSet('off')">خاموش‌کردن مش</button>
    </div>
    <label>کلید مشترک مش (باید روی همهٔ همتاها یکی باشد)</label>
    <div class="row"><input id="mesh-key" dir="ltr"><button class="act" onclick="meshKey()">ذخیرهٔ کلید</button></div>
    <h3>همتاها</h3>
    <div class="row"><input id="mp-name" placeholder="نام، مثل frankfurt2"><input id="mp-endpoint" placeholder="host:51822" dir="ltr"></div>
    <div class="row"><input id="mp-pub" placeholder="کلید عمومی WireGuard همتا" dir="ltr"><input id="mp-ip" placeholder="10.99.0.2" dir="ltr"></div>
    <button class="act" onclick="meshPeerAdd()">افزودن همتا</button>
    <table id="mesh-table"></table>
    <h3>نمرهٔ مسیرها (میلی‌ثانیه — کمتر بهتر)</h3>
    <div id="mesh-scores"></div>
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
  '<div class="card">VPN ‏(L2TP/PPTP)<b>'+dot((s.vpn||{}).service||'unknown')+'</b></div>'+
  '<div class="card">حالت<b>'+(s.mode==='public'?'عمومی':'خصوصی')+'</b></div>'+
  '<div class="card">قوانین هایجک<b>'+s.hijack_count+'</b></div>'+
  '<div class="card">دامنهٔ کالاف<b>'+s.cod_count+'</b></div>'+
  '<div class="card">دامنهٔ گیمینگ<b>'+s.gaming_count+'</b></div>'+
  '<div class="card">دامنهٔ مسدود<b>'+(s.blocklist_count||0)+'</b></div>'+
  '<div class="card">مش<b>'+(s.mesh_enabled?('روشن — خروجی: '+(s.mesh_best||'…')):'خاموش')+'</b></div>'+
  '<div class="card">ترنسپورت‌های روشن<b>'+Object.values(s.transports||{}).filter(f=>f.on).length+' از ۶</b></div>';
 const T=s.transports||{};
 const feats=[['console','پروکسی کنسول (بدون رمز، PS5)'],['hysteria2','Hysteria2'],['tuic','TUIC'],['anytls','AnyTLS'],['reality','REALITY ‏(VLESS)'],['recursive','بک‌اند بازگشتی Unbound']];
 $('t-list').innerHTML='<table>'+feats.map(([k,label])=>{const f=T[k]||{};return '<tr><td>'+label+'</td><td>'+(f.on?('<span class="ok">روشن</span> — پورت '+f.port+(k==='hysteria2'&&f.obfs?(' — ابهام: '+f.obfs):'')+(k==='hysteria2'&&f.hop_range?(' — هاپ: '+f.hop_range):'')):('<span class="bad">خاموش</span>'))+'</td><td>'+(f.on?('<button class="ghost" onclick="featureOp(\''+k+'\',\'disable\')">خاموش‌کردن</button>'):('<button class="ghost" onclick="featureOp(\''+k+'\',\'enable\')">روشن‌کردن</button>'))+'</td></tr>'}).join('')+'</table>';
 const R=T.reality||{};
 $('t-reality').textContent=R.on?('نام سرور پوششی: '+(R.server_name||'')+' — پورت: '+R.port+'\nکلید عمومی: '+(R.public_key||'')+'\nShort ID: '+(R.short_id||'')+'\nکلاینت‌ها (UUID هر کاربر پروکسی):\n'+(R.clients||[]).map(c=>'  '+c.user+': '+c.uuid).join('\n')):'REALITY خاموش است.';
 try{const h=await api('/api/health');
  $('cards').innerHTML+=
   '<div class="card">سلامت نود<b>'+(h.healthy?'<span class="ok">سالم</span>':'<span class="bad">'+(h.problems||[]).join('، ')+'</span>')+'</b></div>'+
   '<div class="card">پاسخ DNS محلی<b>'+(h.dns_answer_ms!=null?h.dns_answer_ms+' ms':'—')+'</b></div>'+
   '<div class="card">گواهی TLS<b>'+(h.cert_days_left!=null?h.cert_days_left+' روز':'—')+'</b></div>';
 }catch(e){}
 $('tops').innerHTML='<table>'+(s.top_domains||[]).map(x=>'<tr><td>'+x[0]+'</td><td>'+x[1]+'</td></tr>').join('')+'</table>';
 $('m-mode').value=s.mode;$('m-allow').value=(s.allowlist||[]).join('\n');
 $('p-info').textContent='کاربران فعلی: '+(s.proxy_users||[]).join('، ');
 $('p-table').innerHTML=(s.proxy_users||[]).map(u=>'<tr><td>'+u+'</td><td><button class="ghost" onclick="proxyDel(\''+u+'\')">حذف</button></td></tr>').join('');
 $('w-table').innerHTML=(s.wg_peers||[]).map(u=>'<tr><td>'+u+'</td><td><button class="ghost" onclick="wgDel(\''+u+'\')">حذف</button></td></tr>').join('');
 const v=s.vpn||{};
 $('vpn-info').textContent='وضعیت سرویس: '+(v.service||'—')+' — آدرس سرور برای کلاینت‌ها: آی‌پی عمومی همین نود';
 $('vpn-table').innerHTML=
  '<tr><td>L2TP/IPsec</td><td dir="ltr">UDP 500, 4500, 1701 + ESP</td><td>PSK: <span dir="ltr">'+(v.psk||'—')+'</span></td><td dir="ltr">'+(v.l2tp_pool||'')+'</td></tr>'+
  '<tr><td>PPTP</td><td dir="ltr">TCP 1723 + GRE (47)</td><td>MPPE-128 اجباری</td><td dir="ltr">'+(v.pptp_pool||'')+'</td></tr>'+
  '<tr><td>نام کاربری</td><td dir="ltr">'+(v.user||'—')+'</td><td>رمز: <span dir="ltr">'+(v.pass||'—')+'</span></td><td>DNS کلاینت: خود نود</td></tr>';
 loadHijack();loadDomains();loadMesh();
}catch(e){}}
async function loadMesh(){try{const m=await api('/api/mesh');
 $('mesh-info').textContent='وضعیت: '+(m.enabled?'روشن':'خاموش')+' — سرویس: '+m.service+' — خروجی فعلی: '+((m.state&&m.state.best)||'—')+' — IP مش این نود: '+(m.mesh_ip||'—');
 if(document.activeElement!==$('mesh-key'))$('mesh-key').value=m.key||'';
 $('mesh-table').innerHTML=(m.peers||[]).map(p=>'<tr><td>'+p.name+'</td><td dir="ltr">'+p.endpoint+'</td><td dir="ltr">'+p.mesh_ip+'</td><td><button class="ghost" onclick="meshPeerDel(\''+p.name+'\')">حذف</button></td></tr>').join('');
 const sc=(m.state&&m.state.scores)||{};
 $('mesh-scores').innerHTML='<table>'+Object.keys(sc).map(k=>'<tr><td>'+(k==='direct'?'مستقیم':k)+'</td><td>'+sc[k]+'</td></tr>').join('')+'</table>';
}catch(e){}}
async function meshSet(op){const r=await api('/api/mesh',{method:'POST',body:JSON.stringify({op:op})});msg(r.error||(op==='on'?'مش روشن شد':'مش خاموش شد'));refresh()}
async function meshKey(){const r=await api('/api/mesh',{method:'POST',body:JSON.stringify({op:'key',key:$('mesh-key').value})});msg(r.error||'کلید ذخیره شد');refresh()}
async function meshPeerAdd(){const r=await api('/api/mesh',{method:'POST',body:JSON.stringify({op:'add-peer',name:$('mp-name').value,endpoint:$('mp-endpoint').value,pubkey:$('mp-pub').value,mesh_ip:$('mp-ip').value})});msg(r.error||'همتا افزوده شد');refresh()}
async function meshPeerDel(n){await api('/api/mesh',{method:'POST',body:JSON.stringify({op:'del-peer',name:n})});refresh()}
async function act(a){msg('در حال اجرا...');const r=await api('/api/action',{method:'POST',body:JSON.stringify({action:a})});$('out').textContent=r.out||'';msg(r.ok?'انجام شد':'خطا');refresh()}
async function loadHijack(){const r=await api('/api/hijack');$('h-table').innerHTML=r.rules.map(x=>'<tr><td>'+x.domain+'</td><td>'+x.target+(x.target6?(' + '+x.target6):(x.v6_blocked?' (IPv6 بسته)':''))+'</td><td><button class="ghost" onclick="hijackDel(\''+x.domain+'\')">حذف</button></td></tr>').join('')}
async function hijackAdd(){const r=await api('/api/hijack',{method:'POST',body:JSON.stringify({domain:$('h-dom').value,target:$('h-tgt').value,target6:$('h-tgt6').value})});msg(r.error||'ذخیره شد');loadHijack();refresh()}
async function featureOp(f,op){const body={feature:f,op:op};if(op==='hop')body.range=$('t-hop').value;if(op==='obfs')body.obfs=$('t-obfs').value;msg('در حال اجرا...');const r=await api('/api/feature',{method:'POST',body:JSON.stringify(body)});const el=$('t-out');if(el)el.textContent=r.out||'';msg(r.ok?'انجام شد':(r.error||'خطا'));refresh()}
async function pwChange(){const r=await api('/api/password',{method:'POST',body:JSON.stringify({current:$('pw-cur').value,new:$('pw-new').value})});msg(r.ok?'رمز عوض شد':(r.error||'خطا'))}
async function vpnCreds(op){const body=op==='user'?{op:op,user:$('v-user').value,pass:$('v-pass').value}:{op:op,psk:$('v-psk').value};const r=await api('/api/vpn-creds',{method:'POST',body:JSON.stringify(body)});msg(r.ok?'ذخیره شد':(r.error||'خطا'));refresh()}
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

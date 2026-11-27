#!/usr/bin/env python3
"""Ofogh Telegram admin bot: server uptime/status + IP-registration admin.

Stdlib only. The bot token lives in /etc/ofogheamn-dns/bot-token.txt
(root-only). Admin Telegram user IDs live in bot-admins.json. Non-admins
use the bot to file an access request (name + desired username); the
admin approves or rejects from inside the bot, and approval creates the
IP-registration code and notifies the requester.
"""
import hashlib
import html
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

# The node's IPv6 path to api.telegram.org stalls intermittently and
# urllib has no happy-eyeballs fallback: force IPv4 for that host.
_orig_gai = socket.getaddrinfo


def _gai_v4(host, *args, **kwargs):
    res = _orig_gai(host, *args, **kwargs)
    if host == "api.telegram.org":
        v4 = [r for r in res if r[0] == socket.AF_INET]
        if v4:
            return v4
    return res


socket.getaddrinfo = _gai_v4

ETC = "/etc/ofogheamn-dns"
TOKEN_FILE = os.path.join(ETC, "bot-token.txt")
ADMINS_FILE = os.path.join(ETC, "bot-admins.json")
REQUESTS_FILE = os.path.join(ETC, "bot-requests.json")
OFFSET_FILE = os.path.join(ETC, "bot-offset.json")
CODES = os.path.join(ETC, "reg-codes.json")
STATE = os.path.join(ETC, "reg-state.json")
ALLOW = os.path.join(ETC, "allowlist.txt")
PANEL_URL = "http://180.149.45.237:8081"
API = "https://api.telegram.org/bot%s/%s"
SERVICES = [
    ("ofogheamn-dns", "DNS"),
    ("ofogheamn-proxy", "پروکسی"),
    ("ofogheamn-panel", "پنل وب"),
    ("ofogh-ipreg.service", "پنل ثبت IP"),
    ("wg-quick@wg0", "وایرگارد"),
    ("ofogh-sni-relay", "رلهٔ SNI"),
    ("ofogh-mm-relay", "رلهٔ مچ‌میکینگ"),
]
awaiting = {}
reqflow = {}
EMOJI_FILE = os.path.join(ETC, "bot-emoji.json")
EMOJI_BUILTIN = {
    "👍": "5172639207193051720",
    "🔥": "5170202955713872686",
    "🎉": "5170162552956519052",
    "❤️": "5177198396582139469",
    "💚": "5170527174205112808",
    "💙": "5170503985676681662",
}


def emoji_map():
    m = dict(EMOJI_BUILTIN)
    m.update(load(EMOJI_FILE, {}))
    return m


def u16len(s):
    return len(s.encode("utf-16-le")) // 2


def build_entities(text):
    """Convert the bot's <b>/<code> markup + known premium emoji into
    Telegram message entities. Returns (plain_text, entities)."""
    emap = emoji_map()
    keys = sorted(emap, key=len, reverse=True)
    plain = []
    entities = []
    pos = 0
    stack = []
    for tok in re.split(r"(<b>|</b>|<code>|</code>)", text):
        if tok in ("<b>", "<code>"):
            stack.append(("bold" if tok == "<b>" else "code", pos))
            continue
        if tok in ("</b>", "</code>"):
            typ = "bold" if tok == "</b>" else "code"
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == typ:
                    start = stack.pop(i)[1]
                    if pos > start:
                        entities.append({"type": typ, "offset": start,
                                         "length": pos - start})
                    break
            continue
        seg = html.unescape(tok)
        j = 0
        while j < len(seg):
            hit = None
            for k in keys:
                if seg.startswith(k, j):
                    hit = k
                    break
            if hit:
                plain.append(hit)
                entities.append({"type": "custom_emoji", "offset": pos,
                                 "length": u16len(hit),
                                 "custom_emoji_id": emap[hit]})
                pos += u16len(hit)
                j += len(hit)
            else:
                plain.append(seg[j])
                pos += u16len(seg[j])
                j += 1
    return "".join(plain), entities


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def api(token, method, timeout=70, **kw):
    data = json.dumps(kw).encode()
    req = urllib.request.Request(API % (token, method), data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def send(token, chat, text, kb=None):
    plain, entities = build_entities(text)
    kw = {"chat_id": chat, "text": plain}
    if entities:
        kw["entities"] = entities
    if kb:
        kw["reply_markup"] = {"inline_keyboard": kb}
    for attempt in (1, 2):
        try:
            api(token, "sendMessage", timeout=20, **kw)
            return
        except Exception as e:
            print("send failed (try %d):" % attempt, e, file=sys.stderr,
                  flush=True)
            time.sleep(2)


def rel_time(ts):
    if not ts:
        return "—"
    d = int(time.time()) - int(ts)
    if d < 90:
        return "همین حالا"
    if d < 3600:
        return "%d دقیقه پیش" % (d // 60)
    if d < 86400:
        return "%d ساعت پیش" % (d // 3600)
    return "%d روز پیش" % (d // 86400)


def uptime_text():
    with open("/proc/uptime") as f:
        up = int(float(f.read().split()[0]))
    days, rem = divmod(up, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    parts = []
    if days:
        parts.append("%d روز" % days)
    if hours:
        parts.append("%d ساعت" % hours)
    parts.append("%d دقیقه" % mins)
    with open("/proc/stat") as f:
        boot = next(int(l.split()[1]) for l in f if l.startswith("btime"))
    boot_s = time.strftime("%Y-%m-%d %H:%M", time.localtime(boot))
    with open("/proc/loadavg") as f:
        load_avg = " ".join(f.read().split()[:3])
    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            mem[k] = int(v.split()[0])
    used_gb = (mem["MemTotal"] - mem["MemAvailable"]) / 1048576
    tot_gb = mem["MemTotal"] / 1048576
    import shutil
    du = shutil.disk_usage("/")
    lines = ["⏱ <b>آپتایم سرور:</b> %s" % " و ".join(parts),
             "روشن از: %s" % boot_s,
             "لود: %s" % load_avg,
             "رم: %.1f از %.1f گیگابایت" % (used_gb, tot_gb),
             "دیسک: %.1f از %.1f گیگابایت" % (du.used / 1e9, du.total / 1e9),
             "", "<b>سرویس‌ها:</b>"]
    for unit, label in SERVICES:
        r = subprocess.run(["systemctl", "is-active", unit],
                           capture_output=True, text=True)
        ok = r.stdout.strip() == "active"
        lines.append("%s %s" % ("✅" if ok else "❌", label))
    return "\n".join(lines)


def users_text():
    codes = load(CODES, {})
    state = load(STATE, {})
    if not codes:
        return "هنوز کدی ساخته نشده است."
    lines = ["👥 <b>کاربران ثبت IP</b>", ""]
    for h, v in sorted(codes.items(), key=lambda kv: kv[1].get("label", "")):
        st = state.get(h) or {}
        ip = st.get("ip", "—")
        lines.append("• <code>%s</code>\n  IP: <code>%s</code> (%s)"
                     % (html.escape(v.get("label", "?")), html.escape(ip),
                        rel_time(st.get("updated"))))
    return "\n".join(lines)


def allow_text():
    try:
        with open(ALLOW) as f:
            ips = [l.strip() for l in f if l.strip()]
    except OSError:
        ips = []
    return "🛡 <b>لیست مجاز فایروال</b> (%d IP)\n\n%s" % (
        len(ips), "\n".join("• <code>%s</code>" % html.escape(i) for i in ips))


def code_exists(label):
    codes = load(CODES, {})
    return hashlib.sha256(label.encode()).hexdigest() in codes


def add_code(label):
    codes = load(CODES, {})
    h = hashlib.sha256(label.encode()).hexdigest()
    if h in codes:
        return "این کد از قبل وجود دارد."
    codes[h] = {"label": label, "created": int(time.time())}
    save(CODES, codes)
    return "🎉 کد ساخته شد: <code>%s</code>\nکاربر با همین کد در پنل ثبت IP می‌کند." % html.escape(label)


def revoke_code(label):
    codes = load(CODES, {})
    state = load(STATE, {})
    hit = [h for h, v in codes.items() if v.get("label") == label]
    if not hit:
        return "چنین کدی نیست."
    for h in hit:
        ip = (state.pop(h, None) or {}).get("ip")
        codes.pop(h, None)
        if ip and os.path.exists(ALLOW):
            with open(ALLOW) as f:
                lines = [l.strip() for l in f if l.strip()]
            if ip in lines:
                lines.remove(ip)
                with open(ALLOW, "w") as f:
                    f.write("\n".join(lines) + "\n")
    save(CODES, codes)
    save(STATE, state)
    subprocess.run(["systemctl", "restart", "ofogheamn-firewall.service"],
                   capture_output=True)
    return "🗑 کد <code>%s</code> حذف و IPاش از فایروال برداشته شد." % html.escape(label)


def back_kb():
    return [[{"text": "🔙 بازگشت", "callback_data": "p:home"}]]


def home_kb():
    n = len(load(REQUESTS_FILE, []))
    req_label = "📥 درخواست‌ها (%d)" % n if n else "📥 درخواست‌ها"
    return [[{"text": "⏱ آپتایم و وضعیت سرور", "callback_data": "p:uptime"}],
            [{"text": "👥 کاربران ثبت IP", "callback_data": "p:users"},
             {"text": "🛡 لیست مجاز", "callback_data": "p:allow"}],
            [{"text": req_label, "callback_data": "p:reqs"}],
            [{"text": "➕ ساخت کد تازه", "callback_data": "p:add"},
             {"text": "🗑 حذف کد", "callback_data": "p:revoke"}]]


def request_kb(uid):
    return [[{"text": "✅ تأیید و ساخت کد", "callback_data": "rq:ok:%d" % uid},
             {"text": "❌ رد", "callback_data": "rq:no:%d" % uid}]]


def requests_text_and_kb():
    reqs = load(REQUESTS_FILE, [])
    if not reqs:
        return "درخواست در انتظاری نیست.", back_kb()
    lines = ["📥 <b>درخواست‌های در انتظار</b>", ""]
    kb = []
    for r in reqs:
        lines.append("• نام: %s\n  کد درخواستی: <code>%s</code> (%s)"
                     % (html.escape(r.get("name", "?")),
                        html.escape(r.get("username", "?")),
                        rel_time(r.get("ts"))))
        kb.append([{"text": "✅ %s" % r.get("username", "?"),
                    "callback_data": "rq:ok:%d" % r["id"]},
                   {"text": "❌", "callback_data": "rq:no:%d" % r["id"]}])
    kb.append([{"text": "🔙 بازگشت", "callback_data": "p:home"}])
    return "\n".join(lines), kb


def notify_admins(token, text, kb=None):
    for a in load(ADMINS_FILE, []):
        send(token, a, text, kb)


def resolve_request(token, admin_chat, uid, ok):
    reqs = load(REQUESTS_FILE, [])
    hit = [r for r in reqs if r.get("id") == uid]
    if not hit:
        send(token, admin_chat, "این درخواست قبلاً رسیدگی شده است.", home_kb())
        return
    r = hit[0]
    reqs = [x for x in reqs if x.get("id") != uid]
    save(REQUESTS_FILE, reqs)
    if ok:
        msg = add_code(r["username"])
        send(token, admin_chat,
             "درخواست %s تأیید شد.\n%s" % (html.escape(r.get("name", "")), msg),
             home_kb())
        send(token, uid,
             "🎉 درخواست شما تأیید شد.\nکد ثبت IP شما: <code>%s</code>\n"
             "هر وقت IP اینترنت‌تان عوض شد، در پنل ثبت IP با این کد ثبتش کنید:\n%s"
             % (html.escape(r["username"]), PANEL_URL))
    else:
        send(token, admin_chat,
             "درخواست %s رد شد." % html.escape(r.get("name", "")), home_kb())
        send(token, uid, "❌ درخواست شما توسط مدیر رد شد.")


def handle_user(token, chat, uid, text):
    reqs = load(REQUESTS_FILE, [])
    mine = [r for r in reqs if r.get("id") == uid]
    step = reqflow.get(chat)
    if text.startswith("/start"):
        if mine:
            send(token, chat,
                 "درخواست شما قبلاً ثبت شده و در انتظار تأیید مدیر است.\n"
                 "نام: %s\nکد درخواستی: <code>%s</code>"
                 % (html.escape(mine[0].get("name", "")),
                    html.escape(mine[0].get("username", ""))))
            return
        reqflow[chat] = {"step": "name"}
        send(token, chat,
             "سلام. این ربات برای کاربران نود افق امن است.\n"
             "برای درخواست دسترسی، اول <b>نام و نام خانوادگی</b> خود را بنویسید:")
        return
    if step and step.get("step") == "name" and text:
        reqflow[chat] = {"step": "username", "name": text[:80]}
        send(token, chat,
             "حالا یک <b>نام کاربری انگلیسی</b> برای کد ثبت IP خود انتخاب کنید "
             "(حروف کوچک، عدد و _؛ مثل ali_rezaei):")
        return
    if step and step.get("step") == "username" and text:
        username = text.strip().lower()
        name = step.get("name", "")
        reqflow.pop(chat, None)
        if not re.fullmatch(r"[a-z0-9_]{3,32}", username):
            send(token, chat,
                 "نام کاربری معتبر نیست. با /start دوباره شروع کنید و فقط حروف کوچک انگلیسی، عدد و _ بفرستید.")
            return
        if code_exists(username):
            send(token, chat,
                 "این نام کاربری قبلاً گرفته شده است. با /start دوباره شروع کنید و نام دیگری انتخاب کنید.")
            return
        if any(r.get("username") == username for r in reqs):
            send(token, chat, "این نام کاربری در یک درخواست دیگر در انتظار است.")
            return
        reqs.append({"id": uid, "name": name, "username": username,
                     "ts": int(time.time())})
        save(REQUESTS_FILE, reqs)
        send(token, chat,
             "✅ درخواست شما ثبت شد و برای مدیر ارسال شد.\n"
             "نام: %s\nکد درخواستی: <code>%s</code>\n"
             "بعد از تأیید مدیر، کدتان را همین‌جا دریافت می‌کنید."
             % (html.escape(name), html.escape(username)))
        notify_admins(token,
                      "📥 <b>درخواست تازه</b>\nنام: %s\nکد درخواستی: <code>%s</code>"
                      % (html.escape(name), html.escape(username)),
                      request_kb(uid))
        return
    send(token, chat, "برای ثبت درخواست دسترسی /start را بزنید.")


def handle(token, upd, admins):
    msg = upd.get("message") or {}
    cb = upd.get("callback_query")
    if cb:
        chat = cb["message"]["chat"]["id"]
        uid = cb["from"]["id"]
        data = cb.get("data", "")
        try:
            api(token, "answerCallbackQuery", timeout=6,
                callback_query_id=cb["id"])
        except Exception:
            pass
    else:
        chat = (msg.get("chat") or {}).get("id")
        uid = (msg.get("from") or {}).get("id")
        data = None
    if chat is None or uid is None:
        return
    text = (msg.get("text") or "").strip()

    # The admin can teach the bot premium emoji: any custom emoji in a
    # message from the admin is learned and reused in the bot's replies.
    if uid in admins and msg.get("entities"):
        learned = load(EMOJI_FILE, {})
        new = []
        raw16 = (msg.get("text") or "").encode("utf-16-le")
        for e in msg["entities"]:
            if e.get("type") == "custom_emoji":
                ch = raw16[e["offset"] * 2:(e["offset"] + e["length"]) * 2]
                ch = ch.decode("utf-16-le")
                if ch not in EMOJI_BUILTIN and learned.get(ch) != e["custom_emoji_id"]:
                    learned[ch] = e["custom_emoji_id"]
                    new.append(ch)
        if new:
            save(EMOJI_FILE, learned)
            send(token, chat,
                 "یاد گرفتم و از این به بعد استفاده می‌کنم: " + " ".join(new))

    if uid not in admins:
        if data:
            return
        handle_user(token, chat, uid, text)
        return

    if data:
        if data == "p:home":
            awaiting.pop(chat, None)
            send(token, chat, "پنل مدیریت نود افق امن:", home_kb())
        elif data == "p:uptime":
            send(token, chat, uptime_text(), back_kb())
        elif data == "p:users":
            send(token, chat, users_text(), back_kb())
        elif data == "p:allow":
            send(token, chat, allow_text(), back_kb())
        elif data == "p:reqs":
            t, kb = requests_text_and_kb()
            send(token, chat, t, kb)
        elif data == "p:add":
            awaiting[chat] = "add"
            send(token, chat,
                 "نام کاربری کد تازه را بفرستید (حروف کوچک انگلیسی، عدد و _):",
                 back_kb())
        elif data == "p:revoke":
            codes = load(CODES, {})
            labels = sorted(v.get("label", "?") for v in codes.values())
            if not labels:
                send(token, chat, "کدی برای حذف نیست.", back_kb())
            else:
                kb = [[{"text": "🗑 " + l, "callback_data": "p:rev:" + l}]
                      for l in labels]
                kb.append([{"text": "🔙 بازگشت", "callback_data": "p:home"}])
                send(token, chat, "کدام کد حذف شود؟", kb)
        elif data.startswith("p:rev:"):
            send(token, chat, revoke_code(data[6:]), back_kb())
        elif data.startswith("rq:ok:"):
            resolve_request(token, chat, int(data[6:]), True)
        elif data.startswith("rq:no:"):
            resolve_request(token, chat, int(data[6:]), False)
        return

    if awaiting.get(chat) == "add" and text:
        awaiting.pop(chat, None)
        if not re.fullmatch(r"[a-z0-9_]{3,32}", text):
            send(token, chat,
                 "نام معتبر نیست؛ فقط حروف کوچک انگلیسی، عدد و _ (۳ تا ۳۲ حرف).",
                 back_kb())
        else:
            send(token, chat, add_code(text), back_kb())
        return

    if text.startswith("/start") or text.startswith("/panel"):
        send(token, chat, "پنل مدیریت نود افق امن 🔥\n\n" + uptime_text(),
             home_kb())
    elif text.startswith("/uptime"):
        send(token, chat, uptime_text(), back_kb())
    elif text.startswith("/users"):
        send(token, chat, users_text(), back_kb())
    elif text.startswith("/allow"):
        send(token, chat, allow_text(), back_kb())


def main():
    with open(TOKEN_FILE) as f:
        token = f.read().strip()
    me = api(token, "getMe")
    print("bot online:", me["result"]["username"], flush=True)
    offset = load(OFFSET_FILE, {}).get("offset", 0)
    while True:
        try:
            r = api(token, "getUpdates", offset=offset, timeout=25,
                    allowed_updates=["message", "callback_query"])
            admins = load(ADMINS_FILE, [])
            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                save(OFFSET_FILE, {"offset": offset})
                try:
                    handle(token, upd, admins)
                except Exception as e:
                    print("handle error:", e, file=sys.stderr, flush=True)
        except Exception as e:
            print("poll error:", e, file=sys.stderr, flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()

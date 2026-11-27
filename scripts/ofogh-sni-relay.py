#!/usr/bin/env python3
"""ofogh-sni-relay — transparent SNI router for TCP/443 (opt-in).

Enabled with:  ofogheamn-dns sni-relay enable
(which moves SmartDNS DoH to 127.0.0.1:10443 and starts this
service on public TCP/443).

Routing, decided from the TLS ClientHello's SNI — the TLS itself
is NEVER terminated here; bytes are spliced end-to-end:

  * SNI under a configured suffix (default: embodyvr.io — the
    Embody licensing API behind Call of Duty's Enhanced Audio,
    which geo-blocks some countries with a NET03 error) is
    forwarded to the REAL server of that name, resolved through
    the system resolver (which sits outside SmartDNS and never
    sees the hijack answer that pointed the name at this node).
    Pair with:  ofogheamn-dns add-hijack <host> <node-ip>
  * SNI listed in doh_names, a missing/unparseable SNI, or an
    SNI that would resolve back to this very socket (loop
    guard) goes to the SmartDNS DoH listener on loopback.

Config: /etc/ofogheamn-dns/sni-relay.json
  {"suffixes": ["embodyvr.io"], "doh_names": [],
   "doh_host": "127.0.0.1", "doh_port": 10443}
"""
import asyncio
import json
import os
import socket
import struct
import sys

CONF = "/etc/ofogheamn-dns/sni-relay.json"
_cfg = {"suffixes": ["embodyvr.io"], "doh_names": [],
        "doh_host": "127.0.0.1", "doh_port": 10443}
if os.path.exists(CONF):
    try:
        _cfg.update(json.load(open(CONF, encoding="utf-8")))
    except Exception as e:  # a broken config must not kill DoH routing
        print(f"config load failed, using defaults: {e}",
              file=sys.stderr, flush=True)
DOH = (_cfg["doh_host"], int(_cfg["doh_port"]))
SUFFIXES = [s.lower().lstrip(".") for s in _cfg["suffixes"]]
DOH_NAMES = {n.lower() for n in _cfg["doh_names"]}
IDLE_TIMEOUT = 180


def parse_sni(data: bytes):
    try:
        if len(data) < 5 or data[0] != 0x16:
            return None
        p = 5
        if p >= len(data) or data[p] != 0x01:  # ClientHello
            return None
        p += 4
        p += 2 + 32  # version + random
        if p >= len(data):
            return None
        sid_len = data[p]
        p += 1 + sid_len
        if p + 2 > len(data):
            return None
        cs_len = struct.unpack(">H", data[p:p + 2])[0]
        p += 2 + cs_len
        if p >= len(data):
            return None
        cm_len = data[p]
        p += 1 + cm_len
        if p + 2 > len(data):
            return None
        ext_total = struct.unpack(">H", data[p:p + 2])[0]
        p += 2
        end = min(p + ext_total, len(data))
        while p + 4 <= end:
            etype, elen = struct.unpack(">HH", data[p:p + 4])
            p += 4
            if etype == 0:  # server_name
                q = p
                if q + 2 > len(data):
                    return None
                q += 2  # list length
                if q >= len(data):
                    return None
                q += 1  # name type
                if q + 2 > len(data):
                    return None
                nlen = struct.unpack(">H", data[q:q + 2])[0]
                q += 2
                return data[q:q + nlen].decode("idna").lower()
            p += elen
    except Exception:
        return None
    return None


async def read_client_hello(reader: asyncio.StreamReader) -> bytes:
    buf = b""
    while len(buf) < 5:
        chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
        if not chunk:
            return buf
        buf += chunk
    rec_len = struct.unpack(">H", buf[3:5])[0]
    total = 5 + rec_len
    while len(buf) < total and len(buf) < 65536:
        chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
        if not chunk:
            break
        buf += chunk
    return buf


async def pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while True:
            data = await asyncio.wait_for(reader.read(65536),
                                          timeout=IDLE_TIMEOUT)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        # Half-close, not close (v1.33): closing the shared transport
        # on one direction's EOF killed the opposite direction
        # mid-stream — a client that FINs after its request could
        # lose the tail of the response. Signal EOF to the peer and
        # let the sibling pump finish; handle() closes both writers
        # once both pumps are done.
        try:
            if writer.can_write_eof():
                writer.write_eof()
        except Exception:
            pass


def is_relay_name(sni: str) -> bool:
    return any(sni == s or sni.endswith("." + s) for s in SUFFIXES)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        hello = await read_client_hello(reader)
        if not hello:
            writer.close()
            return
        sni = parse_sni(hello)
        target = DOH
        if sni and sni not in DOH_NAMES and is_relay_name(sni):
            infos = await asyncio.to_thread(
                socket.getaddrinfo, sni, 443, socket.AF_INET,
                socket.SOCK_STREAM)
            real_ip = infos[0][4][0]
            local = writer.get_extra_info("sockname")
            if not local or real_ip != local[0]:
                target = (real_ip, 443)
        up_reader, up_writer = await asyncio.wait_for(
            asyncio.open_connection(target[0], target[1]), timeout=10)
        up_writer.write(hello)
        await up_writer.drain()
        # Per-connection log (v1.33): the live node's debugging
        # depended on seeing which SNI went where, in the journal.
        print(f"relay {writer.get_extra_info('peername')} "
              f"sni={sni} -> {target[0]}:{target[1]}", flush=True)
        await asyncio.gather(pump(reader, up_writer),
                             pump(up_reader, writer))
        for w in (writer, up_writer):
            try:
                w.close()
            except Exception:
                pass
    except Exception as e:
        print(f"sni relay error: {e}", file=sys.stderr, flush=True)
        try:
            writer.close()
        except Exception:
            pass


async def main():
    servers = []
    for host, fam in (("0.0.0.0", socket.AF_INET), ("::", socket.AF_INET6)):
        try:
            srv = await asyncio.start_server(
                handle, host, 443, family=fam, reuse_address=True)
            servers.append(srv)
        except Exception as e:
            print(f"bind {host}:443 failed: {e}",
                  file=sys.stderr, flush=True)
    if not servers:
        sys.exit(1)
    print(f"sni relay listening on 443 (suffixes: {SUFFIXES})", flush=True)
    await asyncio.gather(*(s.serve_forever() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())

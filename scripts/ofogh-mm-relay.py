#!/usr/bin/env python3
"""ofogh-mm-relay — transparent fixed-destination TCP relay (opt-in).

Enabled with:  ofogheamn-dns mm-relay enable
plus:          ofogheamn-dns add-hijack lsg.7500.prod.demonware.net <node-ip>

Listens on the configured port (default TCP/3074) and forwards
every connection, byte for byte, to the real Demonware
login/matchmaking gateway. The destination is re-resolved for
every connection through the SYSTEM resolver, which sits outside
SmartDNS and therefore never sees the hijack answer that points
the name at this node (the gateway's load-balancer address
rotates; per-connection resolution follows it).

Demonware's own session encryption stays end-to-end between the
console and Demonware — this process only carries bytes, so the
session egresses from the node. Measured on the reference node
(2026-11-26): matchmaking ping 87 -> 93 ms (slightly worse) but
visibly better lobbies; the operator kept it for the lobbies.
Every session is logged with duration and byte counts so the
effect stays measurable, never a matter of faith.

Config: /etc/ofogheamn-dns/mm-relay.json
  {"host": "lsg.7500.prod.demonware.net", "port": 3074}
"""
import asyncio
import json
import os
import socket
import sys
import time

CONF = "/etc/ofogheamn-dns/mm-relay.json"
_cfg = {"host": "lsg.7500.prod.demonware.net", "port": 3074}
if os.path.exists(CONF):
    try:
        _cfg.update(json.load(open(CONF, encoding="utf-8")))
    except Exception as e:
        print(f"config load failed, using defaults: {e}",
              file=sys.stderr, flush=True)
TARGET_HOST = _cfg["host"]
TARGET_PORT = int(_cfg["port"])
LISTEN_PORT = int(_cfg["port"])
IDLE_TIMEOUT = 600


async def pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    total = 0
    try:
        while True:
            data = await asyncio.wait_for(reader.read(65536),
                                          timeout=IDLE_TIMEOUT)
            if not data:
                break
            total += len(data)
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        # Half-close, not close (v1.33): closing the shared transport
        # on one direction's EOF killed the opposite direction
        # mid-stream. Signal EOF to the peer and let the sibling
        # pump finish; handle() closes both writers at the end.
        try:
            if writer.can_write_eof():
                writer.write_eof()
        except Exception:
            pass
    return total


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo, TARGET_HOST, TARGET_PORT,
            socket.AF_INET, socket.SOCK_STREAM)
        target_ip = infos[0][4][0]
        up_reader, up_writer = await asyncio.wait_for(
            asyncio.open_connection(target_ip, TARGET_PORT), timeout=10)
        print(f"relay {peer} -> {target_ip}:{TARGET_PORT}", flush=True)
        t0 = time.monotonic()
        up, down = await asyncio.gather(pump(reader, up_writer),
                                        pump(up_reader, writer))
        print(f"closed {peer} -> {target_ip} after "
              f"{time.monotonic() - t0:.0f}s up={up} down={down}",
              flush=True)
        for w in (writer, up_writer):
            try:
                w.close()
            except Exception:
                pass
    except Exception as e:
        print(f"mm relay error from {peer}: {e}",
              file=sys.stderr, flush=True)
        try:
            writer.close()
        except Exception:
            pass


async def main():
    servers = []
    for host, fam in (("0.0.0.0", socket.AF_INET), ("::", socket.AF_INET6)):
        try:
            srv = await asyncio.start_server(
                handle, host, LISTEN_PORT, family=fam, reuse_address=True)
            servers.append(srv)
        except Exception as e:
            print(f"bind {host}:{LISTEN_PORT} failed: {e}",
                  file=sys.stderr, flush=True)
    if not servers:
        sys.exit(1)
    print(f"mm relay listening on {LISTEN_PORT} -> "
          f"{TARGET_HOST}:{TARGET_PORT}", flush=True)
    await asyncio.gather(*(s.serve_forever() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())

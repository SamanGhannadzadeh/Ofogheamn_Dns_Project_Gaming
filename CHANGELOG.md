## v1.29 — 2026-11-22 (DDNS: the node follows your home IP)

- **New: the DDNS allowlist keeper.** A private node trusts the
  admin by home IP — but a home IP changes, and the admin is
  locked out of their own node. The modem's Dynamic DNS page
  (No-IP / DynDNS / TZO) keeps a hostname pointing at the home
  IP; now the node follows it. `ofogheamn-dns ddns set
  <hostname>` arms a 5-minute timer (ofogh-ddns.timer) that
  resolves the hostname and swaps the DDNS-contributed IPs in
  the allowlist, re-applying the firewall only on change. It
  removes only IPs it added itself (tracked in ddns-state.txt),
  never touches hand-written allowlist lines, and a failed
  lookup keeps the old IPs — a DNS hiccup must never lock the
  admin out. The node profile seeds it with OFOGH_DDNS_HOST.
  (DDNS itself moves no traffic and changes no ping — it is a
  name for your home, and this is its one real job here.)

## v1.28 — 2026-11-22 (the console port speaks only what a PS5 speaks)

- **The console port (2081) is now a pure HTTP inbound.** It was
  a mixed (SOCKS5+HTTP) inbound; a PS5 implements exactly one
  proxy protocol — HTTP — so the port now speaks only that, by
  the owner's order ("only the proxies the PS5 directly
  supports"). Through it the console's TCP reaches every IP
  range and every port, as before; nothing the console could
  do has changed, and one unused protocol surface is gone.
  Stated plainly in the generator's docstring, because it is
  the project's standing fact: console game UDP never enters
  the console's proxy setting at all — no server-side proxy of
  any kind can carry what the console itself never sends to a
  proxy. The DNS side is already at its measured ceiling
  (warm answers ~0 ms, fastest-IP, ECS edge steering,
  serve-stale), and the remaining in-game ping is the physical
  path — decided by where the node sits, not by protocol.

## v1.27 — 2026-11-22 (gaming QoS: all ports, both protocols)

- **The gaming sets now mark on every port and both
  protocols**: the cod/dc range rules were UDP-only; they now
  mark TCP too (logins, downloads, store traffic to game
  ranges get the same EF treatment as gameplay UDP). The
  any-destination game-port list grew from 4 UDP ports to the
  well-known console/game set — Xbox Live (88, 500, 3074,
  3544, 4500), PSN (3478, 3479, 3480), Call of Duty (3075,
  3076, 9308), Steam (27015) — UDP and TCP where each applies.
  Marking stays scoped to game ranges + game ports on purpose:
  marking everything would mark nothing, and DSCP is bleached
  on the public internet anyway — its real effect is the
  node's own queue, as documented since v1.20.

## v1.26 — 2026-11-22 (the DNS learns; configs from the panel)

- **Self-learning gaming set**: `ofogh-learn-domains` (daily
  timer on profiled nodes) mines the resolver log for frequent
  domains that are in no set yet, resolves them, and keeps the
  ones whose answers land inside the cod/dc IP ranges — real
  gaming traffic the static lists missed. They join
  lists/learned.domains and get the full gaming treatment
  (edge group, fastest-response, cache warming). The static
  lists stop being the ceiling on coverage.
- **Client configs in the panel**: the transports tab now
  lists every emitted client config (auto, Gecko, Hysteria2,
  TUIC, AnyTLS, HTTPS proxy, gateway) with a download button —
  no more fetching /root files by hand.

## v1.25 — 2026-11-21 (product scope locked: DNS + proxy, no box)

- **Owner's product decision**: no gateway box in the product
  path — nobody pays to put a device in the middle. The
  console connects with its own settings only (node DNS +
  its HTTP proxy field on the node's console port); phones
  and PCs use the client configs. The gateway kit stays in
  the repo as a documented optional extra for owners who
  already have a Linux box.
- **Panel parity completed for the ladder**: Hysteria2-Gecko
  and the HTTPS proxy now appear in the panel's transports
  tab with working enable/disable (through the CLI, as
  always) — every transport is panel-controllable again.

## v1.24 — 2026-11-21 (the best HTTP: CONNECT over TLS)

- **HTTPS proxy inbound**: `ofogheamn-dns https-proxy enable`
  (tcp/9443) — an HTTP proxy whose client-to-node leg is
  TLS-encrypted, for HTTP-only devices (browsers, the
  console's web/store path). Plain HTTP proxying leaves that
  leg readable; this one looks like ordinary HTTPS. TCP-only
  by design: it is not part of the game ladder and carries
  no game UDP. The node profile enables it and emits
  /root/ofogh-https-client.json; the firewall spec loop
  covers its port.

## v1.23 — 2026-11-21 (the ladder is complete + documented)

- **AnyTLS joins as the fifth rung**: the profile enables it
  (guarded), emits /root/ofogh-anytls-client.json and adds it
  to the self-healing group — Gecko → Hysteria2 → TUIC →
  REALITY → AnyTLS. Two independent TCP fallbacks for the
  hours when UDP is throttled or blocked.
- **Client hop range narrowed**: emitted Hysteria2 clients now
  hop inside a 400-port sub-range with the randomized 15–45 s
  interval (the server NAT stays wide) — the profile now
  matches the DPI research instead of hopping the full range.
- **TUIC keepalive**: the emitted TUIC client carries a 15 s
  heartbeat so idle QUIC sessions survive NAT rebinding.
- **README** documents the gaming proxy ladder and the node
  profile.

## v1.22 — 2026-11-21 (TUIC joins the ladder)

- **The better-than-SOCKS5 legs are now the whole ladder**:
  SOCKS5 (1996) keeps only its proper job — the LAN-side entry
  point that apps and consoles speak. Game traffic's WAN leg
  rides UDP-native QUIC transports, and the node profile now
  enables **TUIC** alongside Hysteria2/Gecko, adding it to the
  self-healing urltest group (Gecko → Hysteria2 → TUIC →
  REALITY) and emitting /root/ofogh-tuic-client.json. TUIC is
  the lightest QUIC rung: native UDP relay, BBR, no 0-RTT.

## v1.21 — 2026-11-21 (console gateway kit)

- **The console path is now a first-class deliverable**: the
  node profile also emits /root/ofogh-gateway.json — a sing-box
  config for a small Linux box that sits in-path as the
  console's gateway (the HYPEREV / LagoFast-Box pattern), with
  LAN DNS hijacked to the node resolver and all console traffic
  (TCP + UDP, every port, both stacks) riding the self-healing
  auto group. `docs/CONSOLE-GATEWAY.fa.md` explains why the
  console needs it (the PS5 has no SOCKS5 setting; its HTTP
  proxy carries no game UDP) and how to wire it.

## v1.20 — 2026-11-21 (Pingium-class research round)

- **UDP sessions can no longer be reaped mid-match**: the
  generated server config carries a catch-all route rule with
  `udp_timeout 10m`, and the profile's client configs carry the
  same override — without it, sing-box reaps sniffed UDP sessions
  at the protocol defaults (10 s for stun/dns, 30 s for
  quic/dtls). The profile's conntrack UDP-stream timeout rises
  to 300 s to match.
- **REALITY works in the no-auth product scope**: with an empty
  user store the generator now still emits one operator VLESS
  client (previously the REALITY inbound accepted nobody), and
  the node profile enables REALITY as the TCP/443 fallback rung.
- **Self-healing client**: the profile's combined
  /root/ofogh-client.json routes through an urltest group —
  Gecko, then Hysteria2, then REALITY — so when Iran throttles
  or blocks UDP, the client falls back to TCP/443 by itself.
- **Session-setup latency**: the CoD and PSN sets now answer
  fastest-response with tcp:443 speed checks (fastest-IP remains
  for the download-oriented gaming set); the dual-stack
  selection threshold rises to 50 ms.
- **Firewall parity**: the Gecko (udp/2083) and REALITY
  (tcp/4443) ports get the same allowlist treatment as the other
  authenticated transports in private mode.
- Deliberately unchanged, against generic advice: global
  prefetch stays OFF (the full-set warmer refreshes the
  fastest-IP measurements too; plain prefetch does not), ECS
  stays ON for the gaming sets (the resolver also serves
  direct-exit console customers, and Baku is close enough to
  Iran that the edge penalty is small), and DSCP marking is
  documented as a local-queue tool only — it is measured to be
  ignored across the public internet.

## v1.19 — 2026-11-21 (node profile, improved)

- **Warmup now covers the whole gaming sets** — gaming + CoD +
  PSN lists, A and AAAA, every 4 minutes (replaces the PSN-only
  warmup; the old units are removed on upgrade), so every gaming
  lookup is a cache hit instead of only the top hosts.
- **The profile emits ready-to-import client configs**
  (/root/ofogh-hy2-client.json and /root/ofogh-gecko-client.json):
  BBR (no fixed up/down rates), narrow randomized port hopping on
  the main inbound, dual-stack TUN. Running the profile now
  delivers the node AND its clients.
- **Hardening of the script itself**: the sing-box check is exact
  and fatal (a broken generated config stops the run instead of
  passing silently), re-runs no longer regenerate the Gecko
  passwords (existing client configs keep working), and the
  self-check ends with a bench run.

## v1.18 — 2026-11-21 (Iran→Baku gaming node profile)

- **`scripts/apply-node-profile.sh`** — one idempotent run applies
  the owner's production gaming profile for a Baku node serving
  Iranian players (measured ~40-65 ms from Iranian lines, vs
  ~110+ to Western Europe): the ECS edge group for the CoD/PSN
  sets with the players' /24, gaming TTL floors, Hysteria2
  masquerade + BBR conservative + port hopping, the parallel
  Gecko listener, IP-authenticated (no-password) SOCKS5 product
  scope, conntrack/buffer/Fast-Open kernel tuning, QoS refresh,
  PSN warmup, tunnels off, private firewall. Every step was
  verified live on the 2026-11-21 nodes; the script self-checks
  DNS, the Gecko listener and the hopping NAT at the end.

## v1.17.2 — 2026-11-21 (all domains pass)

- **Nothing is blocked by default**: the shipped SmartDNS template
  no longer loads the public-DoH-resolver sinkhole
  (`doh-resolvers.conf` stays in the repo as a documented opt-in).
  Combined with the empty-by-default blocklist (its refresh timer
  is opt-in and never enabled by the installer), every domain a
  client asks for is resolved and passed through. A static test
  now guards this guarantee.

## v1.17.1 — 2026-11-21 (correction)

- IPv6 through SOCKS is dual-stack **without preference**: the
  `prefer_ipv6` outbound strategy briefly shipped in v1.17 is
  removed again — IPv6 is simply active alongside IPv4.

## v1.17 — 2026-11-21 (Iran-DPI research round)

- **Parallel Hysteria2+Gecko inbound** (`ofogheamn-dns hysteria2-gecko
  enable [port]`, default udp/2083): a second hy2 listener whose obfs
  is Gecko — Salamander scrambling plus fragmentation of the QUIC
  handshake packets, breaking the ~1200-byte Initial clustering plain
  Salamander leaves. It runs alongside the main inbound, so existing
  clients keep working untouched; on this listener obfs replaces the
  masquerade (a prober without the obfs password gets silence).
- **Hysteria2 uses BBR `conservative` by default** (`bbr_profile` in
  hysteria2.json): fixed-rate Brutal-style behaviour is neither
  configured nor encouraged — it does not resemble real HTTP/3.
- **TUIC 0-RTT is now OFF** (`zero_rtt_handshake: false`): replay
  risk per the sing-box docs; two independent reviews agreed.
- **SOCKS passes IPv6 alongside IPv4, with no preference either
  way** (wording corrected in v1.17.1): dual-stack listeners,
  SmartDNS dual-stack selection and the client TUN's IPv6 address
  were already on; the last IPv4-only client settings are removed
  so IPv6 literals and AAAA-only hosts work through the proxy
  while IPv4 behaviour is unchanged.

## v1.16 — 2026-11-21 (consultation round: durability + ECS depth)

- **The generator now emits the live-proven proxy tuning itself**:
  `tcp_fast_open` + `udp_timeout 10m` on both mixed inbounds and
  `tcp_fast_open` on the direct outbound. These were hand-edits on the
  reference node that a config regeneration silently dropped.
- **Hysteria2 masquerade is a feature field**: set `masquerade_url` in
  `hysteria2.json` and the generator emits the flat masquerade block
  sing-box accepts (active-probe resistance for the QUIC port).
- **ECS covers every query type on the edge blueprint**:
  `-subnet-all-query-types` joins the edge upstreams, so HTTPS/SVCB
  lookups carry the player's subnet too, not just A/AAAA.
- **Cache checkpoints every 5 minutes** (`cache-checkpoint-time 300`):
  a crash or reboot no longer loses up to a day of warm cache.

## v1.15 — 2026-11-21 (field fixes from three live nodes + DNS/proxy depth)

- **Installer host prep is automatic now**: writes the systemd-resolved
  no-stub drop-in, disables the distro `unbound.service` (it binds :53
  and crash-loops against the project recursive unit), installs the
  AppArmor local grant for Unbound (`config/apparmor/`), and adds
  `ipset` + `unbound` to the base packages. All four were manual fixes
  on live nodes before.
- **REALITY no longer collides with DoH**: `ofogheamn-dns reality
  enable` writes port **4443** (443 belongs to SmartDNS DoH/Hysteria2).
- **System resolver points at the node**: install guards
  /etc/resolv.conf to 127.0.0.1, so the proxy resolves SOCKS domain
  targets through the gaming DNS instead of the provider resolver —
  before this, every domain a client sent to the SOCKS5 port bypassed
  all gaming rules.
- **Gaming upstreams speak QUIC/H3 too**: `server-quic` + `server-h3`
  join the gaming group next to DoT — no TCP head-of-line blocking on
  the resolution path.
- **ECS edge blueprint updated to the shipped form**: the edge group
  (DoT+QUIC+H3 carrying the player's /24) now also routes the new
  PlayStation set (`lists/psn.domains`); the blueprint documents the
  exact production layout and the two-sets-one-domain trap.
- **Gaming QoS ships as a script**: `scripts/ofogheamn-qos.sh` marks
  game UDP with DSCP EF by port, by `lists/cod-ip-ranges.txt` and by
  aggregated datacenter ranges; `scripts/update-dc-ranges.py` rebuilds
  the datacenter list from the official AWS/GCP/Azure feeds.

## v1.14 — 2026-11-21 (micro pass: warm path measured, bypass closed)

- **Warm path, measured.** With the shipped config running
  against a local fake upstream (300 warm queries, loopback):
  median **0.032 ms**, p95 0.067 ms. The in-server hot path
  is already ~6x under the 0.2 ms ambition; log-level error
  shaves it to 0.025 ms but kills the query log the panel's
  top-domains view reads, so `info` stays — the remaining
  latency for players is network RTT, not resolver config.
- **Warmer is parallel.** cod-warmup.sh ran ~600 digs
  serially; late entries were warmed minutes after early
  ones had cooled. Now xargs -P 8 — the whole list lands
  inside one freshness window.
- **All-requests-through-DNS, resolver layer.** New
  `config/doh-resolvers.conf` (wired like recursive.conf):
  the public encrypted-DNS service names — dns.google,
  Quad9, AdGuard, CleanBrowsing, NextDNS, Firefox's and
  Chrome's built-in DoH hostnames, DoH.pub, AliDNS, dns0,
  CIRA, OpenDNS — answer NXDOMAIN on the node, so a
  subscriber app cannot bootstrap a DoH bypass around it
  and falls back to the node's DNS. One deliberate
  exception, documented in the file: cloudflare-dns.com,
  the node's own DoH upstream hostname. The suite proves
  the sinkhole live against the shipped config — which
  caught the first cut using the documented "-" NXDOMAIN
  form: Release48.5 does not answer it locally (the "#"
  form is the load-bearing one, same lesson as v1.4). The
  stale "-" hint in hijack.conf's header is corrected too.

## v1.13 — 2026-11-21 (panel parity: every feature, one remote)

The panel now controls everything the CLI does. It stays a
remote control — every toggle shells out to the CLI, the
single source of truth (the v1.4 lesson: a second
implementation in the panel once silently dropped REALITY).

- **Transports tab**: console proxy, Hysteria2 (plus port
  hopping and Gecko/Salamander obfs controls), TUIC,
  AnyTLS, REALITY (with the client connection info: cover
  name, public key, short ID, per-user UUIDs) and the
  recursive back-end — state read from the same JSON files
  the CLI writes, toggles executed by the CLI.
- **Dashboard**: transports-on card, and region / bench /
  backup actions next to the existing ones.
- **VPN tab**: change the VPN user/password and the PSK
  from the panel (via `vpn set-user` / `vpn set-psk`).
- **Admin password** can be changed from the dashboard
  (current-password verified, hash-only storage as before).
- **Hijack tab fixed for the dual-stack era**: since v1.9
  a rule is an A+AAAA pair of lines; the panel used to list
  the AAAA "::" plug as a second bogus rule. Rules are now
  paired (with an optional real IPv6 field), and saving
  writes both lines back — proven by a functional test that
  round-trips a CLI-written hijack.conf through the panel.

## v1.12 — 2026-11-21 (debug & hardening pass)

A full audit with the real binaries, not just static greps:

- **sing-box 1.14.4 `check`** passes on the generated config
  with EVERY inbound on at once (mixed, console, Hysteria2 +
  Gecko, TUIC, AnyTLS, REALITY) and on the plain config.
- **SmartDNS (Release48)** starts and answers with every
  optional include populated at once — including the
  recursive include pointing at a dead Unbound (a down
  back-end must never take the front door down with it).
- **unbound-checkconf** validates the shipped unbound.conf.
- **ShellCheck** (error + warning level) and **pyflakes**
  are clean across every shell and Python file in the repo.
- **New: generator port-collision guard.** Two inbounds
  sharing a transport+port previously failed only when
  sing-box started — after the service restart. The
  generator now refuses, naming both tags, while the old
  config is still on disk. Same port on different
  transports (TUIC UDP 8443 + AnyTLS TCP 8443, the shipped
  defaults) stays legal and is covered by a test.

## v1.11 — 2026-11-21 (frontier platform + evaluations; survey stage 3)

- **AmneziaWG platform (experimental).** `platforms/amneziawg/`
  carries a README (why: WireGuard's one-packet fingerprint;
  what it needs: the AWG kernel module + awg tools; honest
  limits: UDP-only, no active-probe resistance) and
  `awgify.py`, a stdlib converter that turns an existing
  WireGuard config into an AmneziaWG one (Jc/Jmin/Jmax junk,
  S1/S2 padding, H1–H4 magic header ranges). Parameters are
  generated once, saved to a JSON file, and reused verbatim
  for the peer config — the suite proves both ends come out
  byte-identical, because mismatched parameters are the
  classic AWG no-connect.
- **docs/FRONTIER.fa.md.** The survey items that are NOT
  becoming defaults, with reasons an operator can re-check:
  BBRv3 (not mainline — A/B procedure only), MASQUE
  (sing-box 1.15-alpha — watch), Xray sidecar for XHTTP
  (evaluated, rejected for now: a second core doubles the
  digest-verified update surface for a capability with no
  measured path where REALITY/443 fails and XHTTP passes),
  multi-path packet duplication (client-side design note),
  anycast+BFD (deployment-level, out of single-node scope;
  its serve-stale half already ships).

## v1.10 — 2026-11-21 (recursive back-end; survey stage 2)

- **Unbound recursive back-end (opt-in).** 
  `ofogheamn-dns recursive enable` starts a local Unbound
  (127.0.0.1:5335, shipped config with serve-expired +
  prefetch, unit ofogheamn-recursive.service) and writes
  one line into the new `recursive.conf` include:
  `server 127.0.0.1:5335 -group recursive`. SmartDNS races
  it against the public upstreams — cold answers cost a
  full recursion, warm ones are local, the node keeps
  resolving when every public upstream is filtered, and no
  single provider sees the whole query stream. Health
  treats the unit as core only while toggled on. The
  include ships inert (a missing conf-file is fatal, so
  the file always exists), and install/uninstall symmetry
  covers every new piece.
- **Split-ECS stays a blueprint, on purpose.** The survey
  suggested productising it; the repo already carries it
  as `config/ecs-split.conf.example` with the reasoning
  (ECS off is the maintainer's core-model decision — the
  node's location is what upstreams should see) and a
  measure-first experiment path. The operator checklist
  now points at it. No blind toggle: the SmartDNS ECS flag
  differs between releases, exactly what the blueprint
  warns about.

## v1.9 — 2026-11-21 (hijack, done properly: dual-stack tight)

The Smart-DNS hijack had a hole you could walk through: 
`add-hijack` wrote only an A record, so AAAA queries for a
hijacked name still resolved upstream and every dual-stack
client bypassed the rule entirely.

- **Two lines, always.** `add-hijack <domain> <ipv4> [ipv6]`
  now writes the A answer and an AAAA answer through one
  helper. With no IPv6 given, AAAA is answered locally as
  `::` — proven against the real SmartDNS binary in the
  static suite (A returns the relay IPv4, AAAA returns `::`,
  no upstream leak). With a real IPv6, both stacks land on
  the relay.
- **Bulk import.** `add-hijack --file domains.txt <ipv4>
  [ipv6]` applies the same dual-stack rule to a service's
  whole domain list with a single reload at the end.
- **Docs.** docs/HIJACK.fa.md explains the model: only the
  names the operator lists are answered locally; everything
  else resolves normally.

## v1.8 — 2026-11-21 (the full QUIC shelf: TUIC, AnyTLS, Hy2 hopping + Gecko)

Stage 1 of the 2026-11-21 technology survey adoption plan
(the survey's shortlist, worked through in order):

- **TUIC v5** — `ofogheamn-dns tuic enable` (UDP 8443, BBR
  congestion control, 0-RTT, node TLS cert). The gentler
  QUIC rung beside Hysteria2's Brutal.
- **AnyTLS** — `ofogheamn-dns anytls enable` (TCP 8443, node
  TLS cert), aimed at the TLS-in-TLS fingerprint. Health now
  probes its port like the other TCP listeners.
- **Hysteria2 port hopping** — `ofogheamn-dns hysteria2 hop
  20000-40000`: the firewall NAT-redirects the whole UDP
  range to the real port; INPUT filtering still applies
  after the redirect, so private mode keeps its allowlist.
- **Hysteria2 Gecko obfs** — `ofogheamn-dns hysteria2 obfs
  gecko` (randomised packet sizes, sing-box >= 1.14);
  Salamander remains the fallback.
- All three new inbounds follow the established opt-in
  pattern (file in /etc/ofogheamn-dns, generator emits only
  while present, firewall guards the port, functional tests
  prove the generator output). Still on the survey plan:
  stage 2 (Unbound recursive back-end, gaming-only ECS
  opt-in), stage 3 (AmneziaWG experimental, Xray sidecar
  evaluation). L2TP/IPsec stays: the survey suggested
  dropping it, but device compatibility is a project
  promise and the maintainer's call outranks the survey.

## v1.7 — 2026-11-21 (Hysteria2: the ladder's rung 2 becomes real)

The transport ladder documented Hysteria2/TUIC as rung 2 —
best loss resilience in the project's own tests — but no node
could actually enable it: the sing-box generator had no
Hysteria2 inbound at all. Now it does, built exactly like the
other opt-in features:

- `ofogheamn-dns hysteria2 enable [port]` writes
  `hysteria2.json` (default UDP 443, random password, mode
  600); the generator emits the `ofogh-hysteria2` inbound
  only while the file exists, using the node's own TLS
  certificate (the DoT/DoH pair). Optional Salamander obfs
  via an `obfs_password` field.
- The firewall guards the port: allowlist chain in private
  mode, open in public mode — it has real password auth,
  unlike the no-auth console port, which stays blocked in
  public mode.
- The static suite proves it end to end: the generator's
  output gains the inbound, with the file's port and
  password, exactly when the file appears.
- TUIC stays documentation-only for now: it shares QUIC's
  loss profile with Hysteria2, and one well-tested QUIC rung
  beats two half-tested ones.

## v1.6.1 — 2026-11-21 (health depth, installer guidance)

- **Health checks the listeners, not just the units.** A
  service can report "active" while its port is wedged; the
  health report now probes the ports the node is configured
  to serve (DoT 853, DoH 443, proxy 2080, panel 8080, and the
  console port while enabled) and flags `port-closed-*`. A
  malformed console.json is flagged instead of crashing.
- **The installer points at the console port.** The closing
  summary now tells PlayStation owners about
  `ofogheamn-dns console enable` — the feature existed since
  v1.6 but a fresh install never mentioned it.
- **The console feature has a functional test.** The static
  suite now runs the sing-box generator both ways and asserts
  the inbound exists exactly when console.json does.

## v1.6 — 2026-11-20 (console proxy, upstream watch, production tuning)

Lessons from the first production node, folded back into the
project.

### Features
- **Console proxy for PlayStation.** The PS5 proxy form has no
  username/password fields, so the authenticated port can never
  work there. `ofogheamn-dns console enable [port]` (default
  2081) now writes `console.json`; the sing-box generator adds
  a no-auth `ofogh-console` inbound only while that file
  exists, and the firewall guards the port — allowlist chain
  in private mode, hard DROP in public mode. The panel is
  never involved; the authenticated port is unchanged.
- **Health watches the upstreams.** `ofogheamn-health.py` now
  probes every upstream named in `smartdns.conf` (UDP query
  for plain servers, TCP connect for DoT/DoH) and reports dead
  ones by name as `upstream-dead-*` problems. Report-only: a
  VPS whose egress stalls on one transport no longer fails
  silently behind a resolver that looks "up".

### Tuning (measured on the production node)
- **Global speed check off.** `speed-check-mode none` is now
  the shipped default: measured cold lookups dropped from
  ~950 ms to ~80 ms, because the check measured every upstream
  on every cold name. The per-domain gaming/CoD rules still
  enforce fastest-IP where it pays.
- **Gaming upstream group is DoT + UDP only.** DoH and QUIC
  binds stay in the default group; on the measured VPS their
  handshake stalls (up to 6 s) hit gaming names first.
- **Kernel:** TCP buffers raised to 16 MB in the shipped
  sysctl file, conntrack ceiling 262144, swappiness 10.

## v1.5 — 2026-11-20 (verification hardening)

A fresh audit of every installer and entry point, hunting the
same bug classes the v1.4 round fixed. Two real findings, both
in download-digest verification; everything else re-checked
clean (install/uninstall file symmetry is exact, VPN defaults
printed by the installer match `config/vpn.conf`, the OpenWrt /
Docker / Windows installers hold all their v1.4 fixes).

### Fixes
- **A failed digest lookup could kill the installer.**
  `verify_digest` fetches the official SHA-256 from the GitHub
  API; when the API is unreachable or rate-limited (HTTP 403 is
  routine for unauthenticated calls), `curl -f` fails — and
  under `set -e` + `pipefail` that failure propagated out of
  the `want=$(...)` assignment and terminated the install
  silently, instead of reaching the documented "warn loudly
  and continue" path. Proven by isolation test (exit 22, no
  output). The lookup is now failure-tolerant (`|| true`) in
  all three bash copies — `install.sh`, the macOS installer
  and the `ofogheamn-dns` CLI updater — and all three outcomes
  are test-proven: API failure → warning + install continues;
  digest match → verified; digest mismatch → SECURITY ABORT.
  (The Windows `Test-Digest` and Docker `verify-download.py`
  already handled this correctly in their own idioms.)
- **macOS installer verified nothing.** It downloaded
  AdGuard Home and sing-box with no digest check at all —
  the last installer still outside the project policy that
  every fetched binary is verified (Linux/Windows/Docker
  since v1.4). It now runs the same `verify_digest` as the
  Linux installer (via the macOS-native `shasum -a 256`).

### Tests
- `tests/static-test.sh`: 52 → **57 checks**, all passing.
  New: macOS verifies both downloads; all three bash
  `verify_digest` copies tolerate API failure.

## v1.4 — 2026-11-20 (debug + polish round)

Every installer and entry point audited as a first-time user
hits it; bugs proven against the real SmartDNS binary where
possible; a regression suite added so this bug class stays
fixed (`tests/static-test.sh`, 52 checks, incl. running the
shipped config on the real core). (v1.3.1/v1.3.2 were the two
Windows first-run fixes, shipped the same day.)

### Critical fixes (first-run killers)
- **install.sh crashed mid-install on fresh servers.**
  `PUBIP` was first computed *after* the WireGuard block that
  uses it — under `set -u` the install died with "PUBIP:
  unbound variable" on any machine with WireGuard available.
  The public IP is now resolved once, before first use.
- **The managed blocklist blocked nothing.** The generator
  emitted `address /domain/` (empty answer form); proven
  against the real SmartDNS binary: the empty form is parsed
  but never answered locally, so ~90k rules were a no-op. The
  generator now emits `address /domain/#`, the only form that
  answers locally (NXDOMAIN, zero answers). Existing nodes pick
  this up on the next blocklist update.
- **Public-mode firewall rule was inverted.** The hashlimit
  rule targeted DROP; `--hashlimit` matches traffic *at or
  below* the limit, so the node dropped every well-behaved
  client and passed floods. Under-limit traffic now RETURNs
  and only the excess is dropped.
- **Docker nodes could never start.** `smartdns.conf` includes
  `mesh-upstream.conf`; a missing include is fatal (proven),
  and the entrypoint never seeded it. It does now. The image
  build also verifies both binary downloads against GitHub's
  recorded SHA-256 digests now, like every other installer.
- **OpenWrt nodes could never start.** The installer never
  downloaded `mesh-upstream.conf` (same fatal include) and
  never created the TLS certificates (missing certs are also
  fatal — SmartDNS does not auto-generate them). Both are now
  provided; the stock `smartdns` UCI service is disabled so it
  stops fighting the project instance for port 53, and the
  DHCP-advertised DNS is the router's real LAN address instead
  of a hardcoded 192.168.1.1.
- **gateway/redirect-53.sh added no rules at all.** Its `add`
  helper ran the existence-check argv on the append path (no
  `-A`), so every rule failed and the script died under
  `set -e`. Fixed and verified with a stub iptables.
- **macOS installer looked for its templates one directory too
  high** (`REPO_ROOT` `../../..` — the Windows v1.3.1 bug,
  twin copy) and died on first run. Now `../..`.
- **Windows installer printed a proxy password that did not
  work.** Every run minted a new password but only wrote
  `proxy.json` when missing — a re-run printed a password that
  was not the stored one. The password is now generated and
  printed only when the file is created, like the Linux
  installer. Also: TLS 1.2 is pinned for downloads (PS 5.1 on
  older .NET failed every GitHub download), generated
  JSON/YAML is written BOM-free (PS 5.1's UTF8 BOM breaks Go
  parsers), downloads are digest-verified like the Linux
  installer, and a missing project template fails with a clear
  message instead of a raw `Get-Content` crash.
  `uninstall.ps1` no longer errors when the install folder is
  already gone.

### First-run feedback (installers verify themselves)
- **Linux install.sh** replaces the bare `dig` probe with a
  per-service PASS/FAIL self-test, a real DNS answer check,
  and an explicit `SELF-TEST: PASS/FAIL` verdict; the banner
  no longer claims "is up" when the test failed, and the
  common port-53 cause (systemd-resolved) is hinted.
- **Windows and macOS installers** gained the same treatment:
  service state, a live DNS answer, and the proxy port are
  checked and reported instead of an unconditional "DONE".

### Panel / CLI / health
- **Panel proxy edits silently dropped REALITY.** Saving proxy
  settings from the panel rewrote `singbox.json` by hand and
  lost the VLESS+REALITY inbound enabled via the CLI. The
  panel now regenerates through `gen-singbox-config.py`, the
  documented single source of truth.
- **Panel hijack API** misclassified IPv6 targets starting with
  a hex letter (or `::`) as hostnames and wrote corrupt cname
  rules; classification now parses the target as an IP.
- **CLI `update`** downloaded the amd64 sing-box build on ARM
  nodes (now arch-aware, like install.sh), verified no
  digests (now verified, like install.sh), and could proceed
  with an empty release tag. `logs proxy` tailed a log file
  that never exists (now `singbox.log`). Status output no
  longer prints `unknown` under `inactive` or `0\n0` counts.
  Missing arguments to `panel-password`, `proxy add/del-user`
  and `wg add/del-peer` print usage instead of a raw
  "unbound variable" crash.
- **Health check** no longer counts the panel (or proxy) as
  core on nodes that never had one — Lite installs showed a
  permanently "unhealthy" panel and the watchdog restarted
  healthy services every 5 minutes.
- **cod-warmup** could print `0\n0` as the gaming-domain total
  on an all-comments list file.

### Uninstall completeness (Linux)
- Removes two orphans: `update-blocklist` (never removed) and
  `ofogheamn-wg-peer` (the list used a `.py` name that was
  never installed). Disables `ofogheamn-wg`, `ofogheamn-mesh`
  and `ofogheamn-blocklist.timer` before deleting their units
  (dangling wants symlinks), drops the `wg0` interface, removes
  the ufw openings the installer added, and removes the
  rendered VPN credential files (`/etc/ipsec.secrets`, and
  `chap-secrets` only when it carries our rendered header).

### Docs aligned with the code
- Root README: Prefetch is off by design (the CoD warmer is
  the prefetch) and ECS is off by default — both bullets said
  the opposite of the shipped config.
- Windows/macOS READMEs + macOS banner claimed "DoT on 853";
  the AdGuard Home editions serve no DoT until a certificate
  is configured in AGH's Encryption settings. macOS README's
  uninstall path pointed at a nonexistent `server/` folder.
- `config/blocklist.conf`'s comment now states the verified
  `#` semantics; `smartdns.conf`'s comment no longer claims
  missing certs are auto-generated (they are fatal).
- MikroTik script creates the container env list before the
  container that references it.

### platforms/saman-os
- Audited: it vendors no stack copy — it delegates to the root
  installer, so it already carries the current stack (VPN
  included). Nothing to sync.

## v1.3 — 2026-11-20 (L2TP/IPsec + PPTP VPN servers)

- **L2TP/IPsec server** (strongSwan IKEv1/PSK + xl2tpd + ppp) and
  **PPTP server** (pptpd, MPPE-128 required) on every node — for
  devices with no WireGuard app: native clients on Windows,
  Android, iOS/macOS (L2TP) and routers. Same exit model as the
  WireGuard tunnel: clients are NATed out of the node and get the
  node's own SmartDNS pushed over PPP (pools 10.67.0.0/24 and
  10.68.0.0/24).
- Credentials live in ONE place, `/etc/ofogheamn-dns/vpn.conf`;
  `ofogheamn-vpn-setup` renders chap-secrets + ipsec.secrets from
  it on every start. Shipped defaults (ofogh / ofogh1234 /
  PSK ofogheamn) are public — the installer banner, the panel VPN
  tab and docs/VPN.fa.md all warn loudly to change them
  (`ofogheamn-dns vpn set-user / set-pass / set-psk`).
- Firewall: UDP 500/4500/1701 + ESP for IPsec, TCP 1723 + GRE for
  PPTP in `ofogheamn-firewall` (+ ufw when active); MSS clamping
  extended from wg0 to ppp+ interfaces.
- Panel: new VPN tab (service state, PSK/user/ports, restart) and a
  dashboard card; health report now includes the VPN service.

## v1.2.1 — 2026-11-20 (startup robustness)

- Ship `config/mesh-upstream.conf` (comment-only placeholder) and
  install it explicitly: `smartdns.conf` includes this file and
  SmartDNS refuses to start when an included file is missing.
  Found by running the real SmartDNS binary against the full
  production config — it now parses and runs clean end-to-end.

## v1.2 — 2026-11-19 (health + operator tooling)

- **Node health watchdog**: `ofogheamn-dns health`
  (`ofogheamn-health.py`) — real DNS answer probe, service states,
  TLS expiry, disk/load; a systemd timer runs it every 5 minutes
  and restarts the DNS service once if it stops answering.
- **Panel parity**: the dashboard now shows node health, local
  DNS answer time and TLS days left (`/api/health`, cached 60 s).
- **Backup / restore**: `ofogheamn-dns backup` writes a 0600
  tarball of the whole node config to /var/backups;
  `restore <file>` brings it back.
- **Operator checklist**: docs/OPERATOR.fa.md.

# تغییرات

## ۱٫۱ — ۱۹ نوامبر ۲۰۲۶ (ارتقای پژوهشی)

بر پایهٔ پژوهش عمیق «قابلیت‌های کاهش پینگ برای اینترنت ایران» —
هر ۱۱ یافته پیاده شد:

- **سنجش دوسویهٔ منطقه** (`ofogheamn-dns region`): نود پینگ خودش تا
  منطقه‌های بازی را رتبه‌بندی می‌کند + مشاوره بر اساس بازی.
- **نردبان ترنسپورت**: ورودی VLESS+REALITY روی نود
  (`ofogheamn-dns reality enable`) + قالب کلاینت sing-box با انتخاب
  خودکار (REALITY ← Hysteria2 ← WireGuard) — docs/LADDER.fa.md
- **بنچ‌مارک یک‌دستوری** (`ofogheamn-dns bench`): DNS سرد/کش،
  رتبه‌بندی منطقه، وضعیت سرویس‌ها.
- **یکپارچگی دانلود**: باینری‌های SmartDNS و sing-box پیش از نصب با
  دیجست رسمی SHA-256 گیت‌هاب تطبیق داده می‌شوند؛ مغایرت = توقف نصب.
- **راهنمای SQM/CAKE** روتر خانه (docs/SQM.fa.md) — بزرگ‌ترین کاهش
  پینگ سمت خانه.
- **بهداشت MTU/MSS**: MTU ‏۱۳۸۰ در کانفیگ پییرهای WireGuard +
  کلمپ MSS روی فوروارد تونل.
- **DoQ/DoH3** به گروه پیش‌فرض آپ‌استریم اضافه شد (از نودِ خارجی
  سالم است و زیر اتلاف برنده است؛ همیشه کنار DoT/DoH مسابقه می‌دهد).
- **راهنمای انتخاب VPS** با روش اندازه‌گیری (docs/VPS.fa.md).
- طرح split-ECS به‌صورت نقشهٔ اختیاریِ خاموش
  (config/ecs-split.conf.example) و سند صادقانهٔ «چرا رلهٔ داخلی
  نساختیم» (docs/RELAY-EXPERIMENTAL.fa.md).

## ۱٫۰ — ۱۹ نوامبر ۲۰۲۶

انتشار عمومی نخست: هستهٔ SmartDNS با انتخاب سریع‌ترین IP و کش
Match-Ready کالاف، پنل فارسی، پروکسی sing-box، تونل WireGuard،
مش نودها، حالت عمومی/خصوصی با اجبار عبور DNS، نسخه‌های
ویندوز/مک (AdGuard Home) و Lite.

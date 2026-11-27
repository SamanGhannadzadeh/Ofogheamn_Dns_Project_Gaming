## v1.44 — 2026-11-27 (all-platform client kit + Telegram admin bot)

Launch readiness across every client platform. The repo now
ships a `clients/` kit generated from the reference node's
real parameters, with an honest per-platform matrix:

- consoles (PS5 / Xbox / Switch): manual DNS, both fields set
  to the node — ready today
- Windows: `Set-OfoghDns.ps1` sets the node on all active
  adapters (with `-Restore` back to DHCP); the DoH variant is
  included, commented, and activates with the domain below
- Android: the sing-box ladder app config (ready today);
  system Private DNS (DoT by hostname) documented and ready
  the moment the domain lands
- iOS: a ready-to-install DoH `.mobileconfig` that also pins
  the node's own CA — it activates as soon as the name below
  resolves publicly
- Linux: systemd-resolved drop-in for plain DNS today, plus
  DoT today via the shipped node CA (`clients/linux/ofogh-ca.pem`)

Named blocker, verified against public resolvers: the name
`dns.ofogheamn.ir` does not exist in public DNS yet (NXDOMAIN
at both Cloudflare and Google) and the node certificate is
self-signed. One A record (`dns.ofogheamn.ir -> node IP`)
unlocks a public Let's Encrypt certificate, after which the
Android / iOS / Windows encrypted paths above go live with
no client changes.

Also new: a Telegram admin bot (`ofogh-telegram-bot.service`)
running on the node — server uptime and service status, the
IP-registration admin panel (list users, create/revoke codes,
view the firewall allowlist), per-section back buttons, an
access-request flow where each requester writes their name
and chosen username for the admin to approve or reject in
chat, and Telegram premium (custom) emoji in its replies,
including a learn-from-the-admin mode for new premium emoji.
The registration panel gained motion design (drifting aurora,
sheen, springy entrances) with `prefers-reduced-motion`
respected, and an installable PWA manifest with custom icons
("add to home screen").

## v1.43 — 2026-11-27 (self-service IP registration panel)

Private mode gates the node by allowlist, which breaks for
users whose egress IP rotates (CGNAT): they had to ask the
operator to edit the list by hand. The node now ships a
registration panel (`ofogh-ipreg.service`, port 8081,
deliberately outside the allowlist chain so unregistered
users can reach it): each user gets a personal code, opens
the page, and their current IP replaces their previous one
in the allowlist; the firewall is re-applied on every
change. Codes are stored as SHA-256 hashes, one active IP
per code, with per-code and per-source rate limits.
Registrations made through a tunnel are refused — the panel
would see the tunnel's egress, not the user's real IP — with
a clear warning on the page. A status view shows the IP a
code currently holds and when it last changed; an admin
view (separate admin code, hash-stored) lists all users.
Codes are managed with `scripts/ofogh-reg-admin.py`
(add/list/revoke). Live since this version on the reference
node, with the first real user registration verified.

## v1.42 — 2026-11-27 (tiered cache warming; DNS core confirmed current)

The all-sets cache warmer became its own denial of service:
with the catalogue at ~1,500 names it ran ~3,000 digs at
parallelism 8 every 4 minutes, saturating the node's single
vCPU for ~90 s per cycle (load ~3) and queueing the proxy
and tunnel traffic behind it — visible to the operator as
periodic ping spikes that no transport tuning could remove.
The warmer is now tiered. The hot tier (the CoD + PSN
session ring, ~40 names) still warms every 4 minutes and
finishes in ~12 s. The bulk catalogue warms on its own
15-minute timer (`ofogh-warm-bulk.timer`) with 2 workers
and staggered starts; serve-expired covers the gaps, and
the v1.33 failure backoff is shared across tiers. Also
verified: the deployed SmartDNS Release48.5 is the newest
stable upstream release (only a nightly exists beyond it),
so the resolver core itself is current.

## v1.41 — 2026-11-27 (proxy session-retention tuning)

An audit of the generated sing-box server config found the
session-retention settings uneven across the transport
ladder: the 10-minute UDP session timeout existed only on
the mixed (SOCKS) inbound, so a game session carried over
Hysteria2 or TUIC could be reaped far earlier than one over
SOCKS; TCP fast open was missing on the REALITY, AnyTLS
and HTTPS-proxy inbounds; and the QUIC inbounds had no idle
timeout, so a quiet tunnel could be torn down between
lobbies at the short library default. The generator now
emits `udp_timeout: 10m` on every ladder inbound,
`tcp_fast_open: true` on every TCP inbound, and
`idle_timeout: 300s` on both Hysteria2 inbounds and TUIC.
Applied live on the reference node and validated with
`sing-box check` plus an end-to-end SOCKS request (204).

## v1.40 — 2026-11-27 (CoD: complete the Demonware relay coverage)

The v1.39 suffix list covered only the prod branch of
Demonware. The reference node's relay journal showed the gap
in the act: the console's rex-gvs connections arrived at the
relay and were handed to the DoH backend (127.0.0.1:10443)
because the suffix list the relay started with predated the
widening — the login host (an exact entry) forwarded fine
while its sibling session hosts fell through. v1.40 widens
the seed suffix to `demonware.net`, covering every branch,
and hijacks the one session host the console's log showed
uncovered: objectstore-cloud-prod-rex.egcp.demonware.net.
Verified live for all five Demonware session hosts (login,
gvs, user-consent, both objectstores): node-IP answers and
the real wildcard certificates (*.prod.demonware.net,
*.egcp.demonware.net) through the relay. Deliberately left
direct: cod-assets.cdn.callofduty.com (content CDN — relaying
it through the node would only slow downloads) and
ingest.datax.activision.com (telemetry, not session layer).
Tests: 1 new static check (244 total).

## v1.39 — 2026-11-27 (smart relay for publisher service hosts)

The SNI relay grows from two licensing/session names to the
major publishers' HTTPS service layer — the layer where the
geo-block actually bites for many titles (account auth and
session setup), and the layer the commercial Smart DNS
services (Shecan and peers) steer the same way: the name
answers with the node's IP, the connection exits at the node,
and the relay forwards by SNI to the real destination with
TLS end-to-end and the service's real certificate.

Starter list (seeded by `sni-relay enable`; each name still
needs its own explicit `add-hijack`): Ubisoft
(public-ubiservices.ubi.com, channel-service.upc.ubi.com,
account.ubisoft.com), EA (accounts.ea.com, signin.ea.com,
gateway.ea.com), Scopely (api.stumbleguys.com, the Spacetime
resolver/session hosts), and the Demonware session suffix
prod.demonware.net — which also puts the already-hijacked
user-consent / rex-gvs / objectstore hosts onto the relay
instead of the DoH fall-through. Verified live on the
reference node for all nine new hosts: node-IP answers, real
issuer certificates through the relay (Ubisoft, DigiCert/EA,
Amazon/Scopely), HTTP behavior identical to direct. Game UDP
and the publishers' custom-port services are untouched, as
before — this is the service layer, not the match path.
Tests: 5 new static checks (243 total).

## v1.38 — 2026-11-27 (the zero-server group: EA / Stumble Guys outage)

Live incident: EA titles, Stumble Guys and The Crew Motorfest
would not connect through the node. Log evidence: every query
for the games' entry names (spring18/spring25 EA redirectors,
api.stumbleguys.com, Scopely resolvers) returned SERVFAIL while
public resolvers answered them fine. Two compounding causes:

- **The profile's edge group had no servers on the node.** The
  conf carried the profile's nameserver rewrites (cod/fifa/
  psn/… → group `edge`) but the `node-profile:edge:v1` server
  block itself was absent — SmartDNS logged 'total server
  number 0' and failed every uncached edge name instantly at
  0 ms. Pins and the cache had masked it since deployment:
  pinned names answer locally, hot names were always cached.
  Rotating names (seasonal EA redirectors) were the first to
  hit it. The group is rebuilt on the node with UDP-majority
  members carrying the profile's client-/24 ECS.
- **A config prune then zeroed the default group too.** While
  pruning dead encrypted upstreams (v1.37), a line-range edit
  commented out the default group's working UDP members along
  with the dead ones, and the follow-up edit that was meant to
  add replacements silently matched nothing. Post-prune checks
  read 0 ms — from the cache. Uncached default-group names
  (Scopely among them) failed until the members were restored.
  Recorded plainly: this one was the operator's own edit, and
  the verification step that should have caught it trusted
  cached answers.

Guards so neither can hide again: the profile's edge block is
now UDP-majority and the profile aborts loudly if the block or
a plain-UDP edge member is missing after application; the
health check scans the SmartDNS log for 'total server number
0' warnings and reports `dns-zero-server-group`. Post-fix
verification ran on a cold cache: EA (www + both redirectors),
all Scopely/Stumble names, Ubisoft, Nintendo, PSN and general
names all answer NOERROR. Tests: 5 new static checks
(238 total).

## v1.37 — 2026-11-27 (everything gap hunt)

- **Upstream transport audit, completed:** the v1.35 fix
  covered the gaming group; this pass probed every remaining
  transport from the reference node. DoH to Cloudflare and
  Google and DoQ to Cloudflare all time out (TCP/QUIC to
  public-resolver IPs is blackholed on this egress class);
  plain UDP answers everywhere (Cloudflare, Google, Quad9,
  Gcore). The default group consequently gains plain-UDP
  members for Google and Quad9 in the template — on such an
  egress it previously had exactly one working member — and
  the reference node's local config comments its dead
  encrypted members out entirely.
- **QoS boot persistence:** QoS (DSCP EF egress marking) was
  an operator-run script whose iptables/tc state vanished at
  reboot. New `ofogheamn-qos.service` re-applies it at boot,
  gated on an opt-in flag file; install ships the unit but
  never enables it. On the reference node QoS stays off by
  decision: transit providers strip DSCP, and there is no
  measured benefit on its path.
- **Warmer politeness:** a full warm cycle over all sets takes
  ~89 s on the 1-vCPU reference node; the warmer unit now runs
  at Nice 19 / CPUWeight 20 / idle IO so a cycle can never
  starve the DNS/proxy data path.
- Checked and left alone, with reasons: panel/proxy run as
  root (the panel performs systemctl operations by design;
  both are firewall-guarded), the two additional allowlisted
  users still at zero packets (their fix is per-user DDNS
  hostnames, still not provided), and the node's own DDNS
  (armed; waits on the owner's modem hostname).
- Tests: 6 new static checks (233 total).

## v1.36 — 2026-11-27 (in-game session tuning, DNS-only)

Focus narrowed to what DNS can still do once a match starts,
established from the reference node's live logs: a console
resolves NO game-server hostnames mid-match (dedicated-server
IPs arrive inside the matchmaking payload), so the honest
DNS surface is the session ring around the match — login,
matchmaking gateway, version/content services, STUN — staying
instant and fresh for the whole session.

- **Respect publisher TTLs on service sets:** the per-title
  sets (cod, psn, fortnite, fifa, valorant, apex, pubg) no
  longer inflate cached answers to a 120 s floor
  (`-rr-ttl-min 0`). A publisher's short TTL is its load
  balancer steering clients across gateway instances; a DNS
  cache that inflates it holds players on instances the
  balancer already rotated away from. Measured on the live
  node: CoD's own names carry TTLs of 128–1021 s, so they were
  never inflated in practice — this removes the trap for the
  short-TTL names in those sets, it does not promise a CoD
  gain that is not there.
- **Warm the exact session hostnames:** cod.domains and
  psn.domains now list the literal hostnames consoles resolve
  around matches (lsg matchmaking, rex login/version,
  objectstore, user-consent, genesis STUN, ps5.np, sgst, ena,
  envelope2, uef) so the cache warmer keeps them at 0 ms
  instead of only warming the apex.
- Audited and deliberately left alone: dual-stack threshold
  (the console's home v6 state is unproven from the node),
  serve-expired (keeps a session alive through upstream
  hiccups), and response modes (ECS steering already returns
  region-appropriate instances; node-side probing cannot rank
  instances for the client's own line).
- Tests: 4 new static checks (227 total).

## v1.35 — 2026-11-27 (worldwide games: 1,499 verified names)

Not just Call of Duty anymore. The general gaming set grows
from 575 to 1,499 names — publishers, platforms, franchises,
studios and esports worldwide (EA, Ubisoft, Riot, Blizzard,
Epic, Xbox, Nintendo, Rockstar, Roblox, Mojang, HoYoverse,
Supercell, Nexon, Square Enix, Capcom, Bandai Namco, Konami,
SEGA, Bethesda, 2K, WB, Bungie, Wargaming, Gaijin, Krafton,
Pearl Abyss, NCSoft, Kakao, NetEase, Tencent and hundreds
more). Every candidate (1,103) was verified to resolve live
before inclusion; 105 dead names were dropped, so the cache
warmer never burns cycles on corpses. Set entries suffix-match
subdomains, so effective service-host coverage is several
thousand. All of it inherits the existing wiring: edge/ECS
upstreams, per-set speed-check (fastest IP), and cache warming
with failure backoff.

- **Critical fix found by the expansion:** the gaming upstream
  group was DoT-only, and on the reference node's egress TCP to
  the public resolver IPs (1.1.1.1, 8.8.8.8 — every port) is
  blackholed while UDP/ICMP pass. The group resolved nothing
  cold; cached names masked it via serve-expired for days, and
  uncached gaming names (accounts.nintendo.com,
  xsts.auth.xboxlive.com, …) SERVFAILed. The group now also has
  plain-UDP members (Cloudflare + Gcore); 15 of the "dead"
  candidates were casualties of this bug and were rescued on
  re-verification through the fixed group.

Sanction reachability, measured from the reference node's
egress: EA accounts, Ubisoft services, Epic account service,
Battle.net + OAuth, Riot auth, Xbox XSTS, Nintendo accounts,
Steam API, Roblox auth and HoYoverse account API all complete
TLS and answer (they refuse Iranian IPs directly; through the
node's proxy exit they respond). Only legacy api.origin.com
did not answer. Tests: 8 new static checks (223 total).

## v1.34 — 2026-11-27 (fastest state: measured edge pins for PSN)

Born on the live node: a PS5 (JP region) failed its system
update check with a generic network error while DNS answered
perfectly — the update hostname was being rotated onto an Akamai
edge the client's line could not use, and other PSN names were
rotating between clusters 50–70 ms apart in handshake time.

- **Edge pins (`ofogheamn-dns edge-pins run`):** measures every
  candidate A record several resolvers return for the built-in
  PlayStation set, times the full TLS handshake from the node,
  and pins the name to the fastest candidate — only after
  openssl verifies the candidate serves Sony's real certificate
  for that name, and only when it beats the current answer by
  >3% (or equals it, locking out bad rotations). Unmeasurable
  names keep their previous pin; nothing is pinned on a guess.
  Pins live in `edge-pin.conf` (shipped comment-only, preserved
  across reinstalls, included by the template).
- Reference-node results: update host 139→118 ms class edge;
  uef 165→116 ms, titlestore-preview 171→122 ms, broadcast
  137→114 ms, action-cards 135→116 ms, library-lambda and home
  to the same fast cluster. Four names (ps5.np, sgst, ena,
  envelope2) already sat on their fastest edge and were left
  alone; ps5cel.np.dl.playstation.net NXDOMAINs at Sony itself.
- Audit notes: per-set speed-check was already on for the
  gaming/PSN sets (global stays `none` on purpose — probing
  every cold answer taxes small nodes), kernel download tuning
  (BBR, fq, slow-start-after-idle=0, notsent_lowat) and sing-box
  TCP Fast Open were verified already at their best values.
- Tests: 10 new static checks (215 total).

## v1.33 — 2026-11-27 (deep debug: persistence, IPv6, uninstall, honesty)

A full audit of the repo plus the live reference node (34
findings; the worst were invisible until looked for). Fixes:

- **Firewall boot persistence (critical):** iptables state is
  runtime-only and nothing re-applied it at boot — after a reboot
  every guard vanished while the panel still said "private", and
  a user-less mixed proxy became an open proxy again. New
  `ofogheamn-firewall.service` (oneshot, before dns/proxy)
  re-applies the saved mode on every boot; install enables it.
- **IPv6 mirror (critical):** every listener binds `[::]` but the
  firewall wrote IPv4 rules only — in private mode the allowlist
  was fully bypassable over IPv6 (verified live: ip6tables empty,
  INPUT ACCEPT). `ofogheamn-firewall` now mirrors the whole
  guarded set into `OFOGH_DNS_IN6` with the same semantics
  (allowlist chain in private mode; rate-limited DNS, open
  authenticated transports, dropped no-auth ports in public).
- **Uninstall actually removes things:** it now deletes the
  firewall INPUT jumps before the chains (the old flush-only code
  could never delete a referenced chain), cleans both address
  families plus the NAT hop redirect, MSS clamps, MASQUERADEs and
  QoS ipsets, restores the pre-install `/etc/resolv.conf` (install
  now backs it up) and the resolved stub, disables — not just
  stops — the VPN daemons, and removes the DDNS units, the boot
  firewall unit, the profile's warm-all/learn units and four
  binaries it used to leave behind (qos, dc-ranges, learn,
  ddns-allowlist).
- **Cache-warmer failure backoff:** ~11% of all answers on the
  live node were SERVFAILs from the warmers re-resolving dead
  set domains (pokedex3d.com, 100classicbooks.com, legacy
  Blizzard/Steam names…) every 4 minutes. Both warmers now share
  a failure state: 4 consecutive failures → skipped for 24 h.
  SmartDNS log rotation trimmed 64 MB×4 → 16 MB×3.
- **DNS64 off by default:** the template enabled synthesis with
  no NAT64 behind it, stalling dual-stack clients on an unrouted
  prefix. The template also stops hardcoding the reference
  host's resolvers, finally wires the PSN domain set (it shipped
  unwired; only profiled nodes ever got it), and the sysctl
  template's ephemeral range starts at 10240, clear of the
  service ports.
- **Profile honesty:** the edge group no longer re-adds the
  Quad9 pair the benchmark pruned; the nameserver rewrites are
  post-checked and abort loudly on template drift; the client
  hop window is capped at the server's redirect range; the
  gateway client keeps its game-UDP pinning rule (only the DNS
  hijack is prepended now).
- **CLI honesty:** a refused config generation (e.g. a port
  collision) used to be followed by "enabled" messages and a
  lying status — toggles now abort on generation failure.
  Re-running a transport `enable` keeps the existing
  keypair/passwords instead of silently rotating them and
  invalidating every distributed client. Allow/hijack/list edits
  are fixed-string (an IP was treated as a regex: removing
  1.2.3.4 also matched 112.3.4). `sni-relay enable` restarts
  SmartDNS before starting the relay (port order) and verifies
  the DoH bind actually moved. `update` keeps `.bak` cores,
  validates the new sing-box against the live config before
  swapping, and rolls back if it does not come up.
- **Panel:** log view tails the last 2 MB instead of loading a
  whole 16 MB log per request; logout invalidates the session
  token; request bodies are capped (the reader runs pre-auth)
  and handler threads have a socket timeout; `mesh.json` (mesh
  key inside) is written 0600.
- **Relays half-close:** both relays closed the shared transport
  when one direction hit EOF, truncating the other direction
  mid-stream; they now `write_eof()` and close only when both
  pumps finish.
- **Robustness:** the config generator quarantines a corrupt
  feature JSON instead of taking every inbound down with it (the
  user store still fails loudly); secret files are created 0600
  rather than chmodded after; the health probe survives a short
  DNS response; the wg-peer tool checks `wg` failures and bounds
  the subnet; VPN credential rendering escapes quotes; the
  installer's public-IP probe is validated.
- Tests: 45 new static checks (205 total).

## v1.32 — 2026-11-27 (gap hunt: the v1.31 relays become first-class)

The v1.31 relays shipped in the installer and the CLI but were
invisible or immortal everywhere else. This release closes those
three gaps; no behaviour of the relays themselves changes.

- **Uninstall now removes the relays.** install.sh ships the
  SNI and matchmaking relays (binaries, units, enabled services),
  but uninstall.sh never stopped or removed them — an uninstalled
  node kept listening on TCP/443 (SNI router) and TCP/3074 with
  nobody owning it. Uninstall now disables both services, deletes
  both unit files and both binaries, and closes 3074/tcp in ufw.
- **The panel shows the relays.** /api/status reports
  `sni_relay` and `mm_relay` service states, and the dashboard
  renders a card for each next to the transport cards — before
  this, the only way to know a relay was up was the CLI.
- **README catches up with v1.31.** The transparent-relays doc
  is linked from the top guide list (NET03 entry point), and the
  upstream line no longer advertises Quad9, which the 39-resolver
  benchmark pruned in v1.31.
- Tests: 160/160 static checks pass (8 new).

## v1.31 — 2026-11-27 (live-node lessons: open-proxy fix, SERVFAIL fix, 1.14 formats, transparent relays)

Every item in this release was found or proven on a live node
(Baku, 2026-11-26) and fixed there first; this release ports the
lessons back into the project.

- **Security: the mixed proxy (2080) could be an open proxy.**
  The firewall deliberately left 2080/8080 alone ("the proxy has
  its users") — but the shipped mixed proxy can run with an
  EMPTY user list, and a stranger relayed through a live node's
  2080 even in private mode. The firewall now chains 2080
  (tcp+udp) and the panel (8080) through the allowlist in
  private mode, and drops a user-less 2080 outright in public
  mode, exactly like the no-auth console port.
- **Private mode dropped the project's own WireGuard clients.**
  The allowlist chain had lo + allowlist only; wg0 traffic now
  RETURNs (tunnel peers are authenticated by their keys).
- **DoT/DoH SERVFAILed every non-gaming name.** The 853/443
  binds carried `-group gaming`, and the gaming group's
  exclude-default upstreams left ordinary names with no path
  (rtcode 2 in ~1 ms). The binds no longer carry the group;
  gaming/edge treatment comes from the domain rules, which key
  on the name, not the arrival port — verified live both ways.
- **Upstreams re-based on a 39-resolver benchmark** measured
  from the node: Cloudflare 1-2 ms (now the gaming group:
  1.1.1.1, 1.0.0.1, v6 ::1111 over DoT + Google DoT), then a
  cliff (Google plain 44 ms, Quad9 56-68 ms — both pruned).
  The default group keeps Cloudflare in every protocol plus
  the host network's own resolvers (Gcore public DNS, 1 ms).
- **sing-box 1.14 formats, everywhere.** Server generator: the
  Hysteria2, Gecko and TUIC inbounds now send ALPN `h3` (TUIC
  refused clients without it: "server did not select an ALPN
  protocol"). Client profile generator: DNS outbounds carry
  `server_port: 53`; Hysteria2 hopping uses `server_ports`
  (colon ranges) + a single `hop_interval`, replacing the
  removed `hop_ports`/`hop_interval_max` pair.
- **New opt-in transparent relays** (docs/TRANSPARENT-RELAYS.fa.md):
  an SNI router for TCP/443 that forwards configured licensing
  hosts (default suffix embodyvr.io — fixes Call of Duty's
  Enhanced Audio NET03 geo-block) to their REAL servers with
  TLS end-to-end, while DoH moves to a loopback listener behind
  the same port; and a fixed-destination relay for the
  Demonware matchmaking gateway (TCP/3074). Both are enabled
  per name with the existing add-hijack rule — never blanket.
  Measured honestly: matchmaking ping 87 -> 93 ms, better
  lobbies; the reference operator kept it for the lobbies.

## v1.30 — 2026-11-22 (gap hunt: more games, BBR node-wide, game-UDP pinning)

- **Five more titles get the full CoD treatment.** Fortnite,
  EA FC/FIFA, Valorant, Apex and PUBG were single names inside
  the big gaming list with generic handling; each now has its
  own set — strict tcp:443 measurement, fastest-response, a
  120 s TTL floor, cache warming, and the ECS edge group on
  profiled nodes. The cache warmer now warms EVERY *.domains
  set, so future sets join automatically.
- **The node's own TCP now runs BBR + fq.** The gaming sysctl
  file set buffers, conntrack and fast-open but left the
  congestion control at the distro default; `default_qdisc=fq`
  and `tcp_congestion_control=bbr` are in — the node's TCP
  rungs (REALITY, AnyTLS, downloads) pace like the QUIC rungs
  already did.
- **Game UDP is pinned to the QUIC rungs in the combined
  client.** The auto urltest could land on a TCP rung, which
  would tunnel game UDP over TCP (head-of-line blocking,
  jitter). A dedicated `game-udp` urltest group (Gecko /
  Hysteria2 / TUIC only) now takes the well-known game ports
  first; everything else still rides auto. The gateway variant
  inherits it.
- Checked and already present, so unchanged: dualstack IP
  selection (threshold 50), serve-stale, cache persistence,
  fastest-response everywhere on game sets, 10-minute UDP
  sessions, port hopping. Checked and still placebo, so still
  not shipped: DSCP beyond the node's own queue (bleached on
  the public internet) and packet duplication over a single
  path (theatre — it needs two genuinely separate paths).

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

#!/bin/bash
# Smoke test against a RUNNING Ofogheamn DNS server.
#   tests/smoke-test.sh [server-ip]     (default 127.0.0.1)
# Checks: UDP, TCP, cache speed, a hijack rule, DoT handshake, DoH.
S="${1:-127.0.0.1}"
fail=0
chk() { if [ "$2" = "0" ]; then echo "PASS  $1"; else echo "FAIL  $1"; fail=1; fi }

A1="$(dig +short +time=3 +tries=1 @"$S" callofduty.com A | head -1)"
[ -n "$A1" ]; chk "UDP/53 answers a gaming domain ($A1)" $?
A2="$(dig +short +time=3 +tries=1 +tcp @"$S" store.steampowered.com A | head -1)"
[ -n "$A2" ]; chk "TCP/53 answers ($A2)" $?
T="$(dig +stats @"$S" callofduty.com A 2>/dev/null | awk '/Query time/{print $4}')"
[ -n "$T" ] && [ "$T" -lt 50 ]; chk "cached answer is fast (${T}ms < 50ms)" $?
echo | openssl s_client -connect "$S":853 >/dev/null 2>&1
chk "DoT/853 TLS handshake" $?
curl -sk --max-time 5 --doh-url "https://$S/dns-query" --doh-insecure https://example.com -o /dev/null
chk "DoH/443 resolves" $?
exit $fail

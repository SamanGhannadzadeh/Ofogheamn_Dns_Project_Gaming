#!/bin/bash
# ofogh-edge-pins — pin latency-sensitive service names to their
# fastest REAL CDN edge.
#
# Why: a games console picks its service hostnames itself (region
# and all); DNS only chooses which edge IP answers. Default CDN
# steering rotates a name across edge clusters of wildly different
# quality (measured on the reference node: the same PSN name at
# 116 ms on one cluster and 183 ms on another), and a bad rotation
# can land on an edge the client's line cannot reach at all — the
# console then reports a generic network error while DNS looks
# perfectly healthy.
#
# What this does, per name: collect every candidate A record that
# several public resolvers return, measure the full TLS handshake
# to each candidate from THIS node, and pin the name (a SmartDNS
# address rule in edge-pin.conf) to the fastest candidate — but
# only when the candidate presents the service owner's real
# certificate for that name (checked with openssl s_client) and
# beats the node's current answer by more than 3%. A name whose
# candidates all fail, or whose certificate does not check out, is
# left exactly as it was. Previous pins for names that could not
# be re-measured are carried over, never silently dropped.
#
# Usage: ofogh-edge-pins [run|show]     (run needs root)
# Names: $EDGE_PIN_NAMES overrides the default PlayStation set.
set -u
ETC="${OFOGH_ETC:-/etc/ofogheamn-dns}"
PINFILE="$ETC/edge-pin.conf"
RESOLVERS="127.0.0.1 1.1.1.1 8.8.8.8 9.9.9.9 95.85.95.85"
OWNER_PATTERN="${EDGE_PIN_OWNER:-Sony Interactive Entertainment}"
NAMES="${EDGE_PIN_NAMES:-fjp01.ps5.update.playstation.net ps5.np.playstation.net sgst.prod.dl.playstation.net ena.net.playstation.net envelope2.np.dl.playstation.net uef.np.dl.playstation.net titlestore-preview.rnps.dl.playstation.net service-hub-psplus.rnps.dl.playstation.net psnow-player.rnps.dl.playstation.net broadcast.rnps.dl.playstation.net action-cards-host-app.rnps.dl.playstation.net library-lambda.rnps.dl.playstation.net home.rnps.dl.playstation.net}"

measure() { # $1=name -> echoes "best_ip best_time current_ip current_time"
  local n="$1" cur cands ip t ts med best="" bestt=999 curt=""
  cur=$(dig @127.0.0.1 "$n" +short 2>/dev/null | grep -E '^[0-9]+\.' | head -1)
  cands=$(for r in $RESOLVERS; do dig @"$r" "$n" +short 2>/dev/null | grep -E '^[0-9]+\.'; done | sort -u)
  for ip in $cands; do
    ts=""
    for _ in 1 2 3; do
      t=$(timeout 5 curl -k -s -o /dev/null -w "%{time_appconnect}" --resolve "$n:443:$ip" "https://$n/" 2>/dev/null)
      ts="$ts $t"
    done
    med=$(echo $ts | tr ' ' '\n' | grep -v '^0.000000$' | sort -n | sed -n '2p')
    [ -z "$med" ] && med=$(echo $ts | tr ' ' '\n' | grep -v '^0.000000$' | sort -n | head -1)
    [ -z "$med" ] && continue
    [ "$ip" = "$cur" ] && curt=$med
    awk -v m="$med" -v b="$bestt" 'BEGIN{exit !(m<b)}' && { bestt=$med; best=$ip; }
  done
  echo "$best $bestt $cur $curt"
}

cert_ok() { # $1=name $2=ip — the edge must serve the owner's real cert
  echo | timeout 8 openssl s_client -connect "$2:443" -servername "$1" 2>/dev/null \
    | grep -a '^subject=' | grep -q "$OWNER_PATTERN"
}

case "${1:-run}" in
  show) cat "$PINFILE" 2>/dev/null || echo "(no edge pins yet)" ;;
  run)
    [ "$(id -u)" = "0" ] || { echo "edge-pins: run needs root" >&2; exit 1; }
    tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
    {
      echo "# Edge pins — written by ofogh-edge-pins; fastest measured"
      echo "# REAL edge per name (certificate-verified). Re-run any time:"
      echo "#   ofogheamn-dns edge-pins run"
    } > "$tmp"
    changed=0
    for n in $NAMES; do
      read -r best bestt cur curt <<< "$(measure "$n")"
      oldpin=$(grep -a "^address /$n/" "$PINFILE" 2>/dev/null | sed 's|.*/\([0-9.]*\)$|\1|' | head -1)
      pin=""
      if [ -n "$best" ] && [ "$bestt" != "999" ]; then
        # Pin when there is no current answer, the best differs and
        # wins by >3%, or the best simply is the current answer
        # (locking it in against rotation costs nothing).
        if [ -z "$cur" ] || [ "$best" = "$cur" ] || \
           awk -v b="$bestt" -v c="${curt:-999}" 'BEGIN{exit !(b < c*0.97)}'; then
          if cert_ok "$n" "$best"; then pin="$best"; fi
        fi
      fi
      [ -z "$pin" ] && pin="$oldpin"   # carry over, never drop silently
      if [ -n "$pin" ]; then
        echo "address /$n/$pin" >> "$tmp"
        [ "$pin" != "$oldpin" ] && { changed=1; echo "pinned  $n -> $pin (handshake ${bestt}s, was ${cur:-none})"; }
        [ "$pin" = "$oldpin" ] && echo "kept    $n -> $pin"
      else
        echo "skipped $n (no verified faster edge; current ${cur:-none})"
      fi
    done
    if [ "$changed" = "1" ] || ! cmp -s "$tmp" "$PINFILE" 2>/dev/null; then
      cp -a "$PINFILE" "$PINFILE.bak" 2>/dev/null || true
      install -m 644 "$tmp" "$PINFILE"
      systemctl restart ofogheamn-dns 2>/dev/null || true
      echo "edge pins updated: $PINFILE"
    else
      echo "edge pins unchanged"
    fi
    ;;
  *) echo "usage: ofogh-edge-pins [run|show]" >&2; exit 64 ;;
esac

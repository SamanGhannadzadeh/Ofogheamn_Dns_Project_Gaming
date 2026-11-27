#!/bin/bash
# Issue a Let's Encrypt cert for ofogheamn.duckdns.org and wire it into
# the node's SmartDNS TLS (DoT/DoH), with a renewal deploy hook.
set -x
export DEBIAN_FRONTEND=noninteractive
DOMAIN=${1:-ofogheamn.duckdns.org}
TLS_DIR=/etc/ofogheamn-dns/tls

if ss -tlnp 2>/dev/null | grep -q ':80 '; then
  echo "PORT80 BUSY - aborting"; exit 1
fi

apt-get update -qq && apt-get install -y -qq certbot || { echo APTFAIL; exit 1; }

certbot certonly --standalone -d "$DOMAIN" \
  --register-unsafely-without-email --agree-tos --non-interactive \
  || { echo CERTBOTFAIL; exit 1; }

mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /usr/local/bin/ofogh-cert-sync.sh <<'EOS'
#!/bin/bash
# Copy the LE cert into SmartDNS's TLS dir and restart the DNS service.
DOMAIN=${1:-ofogheamn.duckdns.org}
TLS_DIR=/etc/ofogheamn-dns/tls
cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$TLS_DIR/fullchain.pem"
cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$TLS_DIR/privkey.pem"
chown ofodns:ofodns "$TLS_DIR/fullchain.pem" "$TLS_DIR/privkey.pem"
chmod 600 "$TLS_DIR/privkey.pem"
systemctl restart ofogheamn-dns.service
EOS
chmod +x /usr/local/bin/ofogh-cert-sync.sh
ln -sf /usr/local/bin/ofogh-cert-sync.sh /etc/letsencrypt/renewal-hooks/deploy/ofogh-sync.sh

cp -a "$TLS_DIR" "$TLS_DIR.bak-selfsigned"
/usr/local/bin/ofogh-cert-sync.sh
sleep 2
echo "dns service: $(systemctl is-active ofogheamn-dns.service)"
openssl x509 -in "$TLS_DIR/fullchain.pem" -noout -issuer -subject -dates | head -4
echo "CERTDONE"

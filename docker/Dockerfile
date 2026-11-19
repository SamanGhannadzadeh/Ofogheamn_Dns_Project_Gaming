# Ofogheamn DNS — all-in-one container (DNS + proxy + panel).
# Runs on any OS with Docker: Linux, Windows, macOS, NAS, and
# RouterOS 7 containers (CHR / ARM64 / x86 routers).
FROM debian:bookworm-slim
ARG SMARTDNS_TAG=Release48.5-RC1
ARG SINGBOX_TAG=v1.14.4
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates openssl dnsutils python3 procps \
      wireguard-tools iproute2 iptables \
    && rm -rf /var/lib/apt/lists/*
RUN case "$(uname -m)" in x86_64) A=x86_64; SA=amd64 ;; aarch64) A=aarch64; SA=arm64 ;; esac \
    && curl -fsSL -o /usr/local/bin/smartdns \
       "https://github.com/pymumu/smartdns/releases/download/${SMARTDNS_TAG}/smartdns-${A}" \
    && chmod 755 /usr/local/bin/smartdns \
    && curl -fsSL "https://github.com/SagerNet/sing-box/releases/download/${SINGBOX_TAG}/sing-box-${SINGBOX_TAG#v}-linux-${SA}.tar.gz" \
       | tar -xz -C /tmp \
    && install -m 755 "/tmp/sing-box-${SINGBOX_TAG#v}-linux-${SA}/sing-box" /usr/local/bin/sing-box
COPY config/ /opt/ofogheamn/config/
COPY scripts/ /opt/ofogheamn/scripts/
COPY panel/panel.py /usr/local/lib/ofogheamn-dns/panel.py
COPY scripts/gen-singbox-config.py /usr/local/lib/ofogheamn-dns/gen-singbox-config.py
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh /opt/ofogheamn/scripts/*.sh \
    && mkdir -p /etc/ofogheamn-dns/lists /etc/ofogheamn-dns/tls \
       /var/cache/ofogheamn-dns /var/log/ofogheamn-dns
VOLUME ["/etc/ofogheamn-dns"]
EXPOSE 53/udp 53/tcp 853/tcp 853/udp 443/tcp 443/udp 2080/tcp 2080/udp 8080/tcp
ENTRYPOINT ["/entrypoint.sh"]

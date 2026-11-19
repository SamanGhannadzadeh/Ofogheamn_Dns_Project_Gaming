# ============================================================
#  Ofogheamn DNS — run the SERVER on MikroTik RouterOS 7
#  RouterOS 7 has a container engine (needs the "container"
#  extra package; works on CHR, x86 and ARM/ARM64 boards with
#  enough storage). The router itself becomes the DNS+proxy
#  server for the whole network.
#  Review every value (IPs, interface names) before importing.
# ============================================================

# 1) A virtual ethernet for the container + addressing
/interface veth
add name=veth-ofogh address=172.17.0.2/24 gateway=172.17.0.1
/interface bridge
add name=bridge-containers
/ip address
add address=172.17.0.1/24 interface=bridge-containers
/interface bridge port
add bridge=bridge-containers interface=veth-ofogh
/ip firewall nat
add chain=srcnat src-address=172.17.0.0/24 action=masquerade comment="Ofogheamn container NAT"

# 2) Pull and create the container (Docker Hub image built from
#    this repo's docker/ folder; or load the tar via file upload)
/container
add remote-image=ofogheamn-dns:latest interface=veth-ofogh \
    root-dir=usb1/ofogheamn-dns start-on-boot=yes \
    envlist=ofogh-env logging=yes name=ofogheamn-dns \
    comment="Ofogheamn DNS + proxy + panel"

# Optional fixed credentials (otherwise random ones print in the
# container log on first start):
/container envs
add name=ofogh-env key=OFOGH_DNS_HOSTNAME value=dns.ofogheamn.ir

# 3) Publish the container ports to the LAN: put the container
#    bridge in the LAN path or dst-nat the service ports from
#    the router's LAN address to 172.17.0.2 — example for DNS:
/ip firewall nat
add chain=dstnat dst-address=192.168.1.1 protocol=udp dst-port=53 \
    action=dst-nat to-addresses=172.17.0.2 to-ports=53 comment="Ofogheamn DNS in"
add chain=dstnat dst-address=192.168.1.1 protocol=tcp dst-port=53 \
    action=dst-nat to-addresses=172.17.0.2 to-ports=53 comment="Ofogheamn DNS in"

# 4) Start it
/container start ofogheamn-dns

# Then point DHCP (option 6) at the router/container and apply
# the enforcement rules from gateway/mikrotik.rsc so every
# subscriber lookup passes through it.

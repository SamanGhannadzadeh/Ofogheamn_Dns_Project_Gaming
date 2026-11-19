# MikroTik RouterOS — force LAN DNS through the Ofogheamn DNS server.
# Replace 192.168.1.2 with your DNS server and 192.168.1.0/24 with your LAN.
# Import with:  /import mikrotik.rsc   (review first!)

/ip firewall nat
add chain=dstnat src-address=192.168.1.0/24 dst-address=!192.168.1.2 \
    protocol=udp dst-port=53 action=dst-nat to-addresses=192.168.1.2 to-ports=53 \
    comment="Ofogheamn DNS redirect UDP"
add chain=dstnat src-address=192.168.1.0/24 dst-address=!192.168.1.2 \
    protocol=tcp dst-port=53 action=dst-nat to-addresses=192.168.1.2 to-ports=53 \
    comment="Ofogheamn DNS redirect TCP"

/ip firewall filter
add chain=forward src-address=192.168.1.0/24 protocol=tcp dst-port=853 action=drop \
    comment="Block direct DoT bypass"
add chain=forward src-address=192.168.1.0/24 protocol=udp dst-port=853 action=drop \
    comment="Block direct DoQ bypass"

# Layer 3: drop encrypted DNS (443/853) to public resolver IPs, so
# hard-coded DoH clients fail and fall back to this DNS server.
/ip firewall address-list
add list=public-dns address=1.1.1.1 comment="Ofogheamn"
add list=public-dns address=1.0.0.1 comment="Ofogheamn"
add list=public-dns address=8.8.8.8 comment="Ofogheamn"
add list=public-dns address=8.8.4.4 comment="Ofogheamn"
add list=public-dns address=9.9.9.9 comment="Ofogheamn"
add list=public-dns address=149.112.112.112 comment="Ofogheamn"
add list=public-dns address=94.140.14.14 comment="Ofogheamn"
add list=public-dns address=94.140.15.15 comment="Ofogheamn"
add list=public-dns address=208.67.222.222 comment="Ofogheamn"
add list=public-dns address=208.67.220.220 comment="Ofogheamn"
add list=public-dns address=76.76.2.0 comment="Ofogheamn"
add list=public-dns address=76.76.10.0 comment="Ofogheamn"

/ip firewall filter
add chain=forward src-address=192.168.1.0/24 dst-address-list=public-dns \
    protocol=tcp dst-port=443 action=drop comment="Block public DoH by IP"
add chain=forward src-address=192.168.1.0/24 dst-address-list=public-dns \
    protocol=udp dst-port=443 action=drop comment="Block public DoQ/DoH3 by IP"

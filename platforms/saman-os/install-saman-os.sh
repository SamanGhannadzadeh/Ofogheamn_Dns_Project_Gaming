#!/bin/bash
# ============================================================
#  Ofogheamn DNS — Saman OS edition installer
#  Saman OS is a first-class target: it is Ubuntu-based, so this
#  runs the main installer, then adds the Saman OS touches:
#  a desktop launcher for the panel and the gaming DNS applied
#  as the system resolver for this machine (optional).
#    sudo bash platforms/saman-os/install-saman-os.sh
#  NOTE: Saman OS *Server* edition ships all of this
#  preinstalled — no installer needed there.
# ============================================================
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

bash "$ROOT/install.sh"

# Desktop launcher for the management panel
install -m 644 "$HERE/ofogheamn-panel.desktop" /usr/share/applications/ofogheamn-panel.desktop
for home in /home/*; do
  [ -d "$home/Desktop" ] && install -m 755 "$HERE/ofogheamn-panel.desktop" "$home/Desktop/" 2>/dev/null || true
  [ -d "$home/دسکتاپ" ] && install -m 755 "$HERE/ofogheamn-panel.desktop" "$home/دسکتاپ/" 2>/dev/null || true
done
echo "Saman OS extras installed: panel launcher on the desktop."

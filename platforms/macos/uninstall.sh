#!/bin/bash
# Ofogheamn DNS — macOS node uninstaller
set -u
ROOT="/opt/ofogheamn"
( cd "$ROOT" && sudo ./AdGuardHome -s stop; sudo ./AdGuardHome -s uninstall ) 2>/dev/null
sudo launchctl unload -w /Library/LaunchDaemons/ir.ofogheamn.proxy.plist 2>/dev/null
sudo rm -f /Library/LaunchDaemons/ir.ofogheamn.proxy.plist
sudo rm -rf "$ROOT"
echo "Removed. Config/data kept in /usr/local/etc/ofogheamn (delete manually if wanted)."

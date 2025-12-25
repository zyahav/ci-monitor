#!/bin/bash
#
# CI Monitor Uninstaller
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"
CONFIG_DIR="$HOME/.ci-monitor"

echo -e "${YELLOW}CI Monitor Uninstaller${NC}"
echo

# Stop daemon if running
if [ -f "$CONFIG_DIR/daemon.pid" ]; then
    echo "Stopping daemon..."
    ci-monitor stop 2>/dev/null || true
fi

# Remove LaunchAgent (macOS)
plist_file="$HOME/Library/LaunchAgents/com.ci-monitor.plist"
if [ -f "$plist_file" ]; then
    echo "Removing LaunchAgent..."
    launchctl unload "$plist_file" 2>/dev/null || true
    rm -f "$plist_file"
fi

# Remove systemd service (Linux)
service_file="$HOME/.config/systemd/user/ci-monitor.service"
if [ -f "$service_file" ]; then
    echo "Removing systemd service..."
    systemctl --user stop ci-monitor 2>/dev/null || true
    systemctl --user disable ci-monitor 2>/dev/null || true
    rm -f "$service_file"
    systemctl --user daemon-reload
fi

# Remove binary
binary="$INSTALL_DIR/ci-monitor"
if [ -f "$binary" ]; then
    echo "Removing $binary..."
    if [ -w "$binary" ]; then
        rm -f "$binary"
    else
        sudo rm -f "$binary"
    fi
fi

# Ask about config
echo
read -p "Remove configuration and history? ($CONFIG_DIR) [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$CONFIG_DIR"
    echo -e "${GREEN}✓${NC} Configuration removed"
else
    echo -e "${YELLOW}Configuration kept at $CONFIG_DIR${NC}"
fi

echo
echo -e "${GREEN}CI Monitor uninstalled.${NC}"

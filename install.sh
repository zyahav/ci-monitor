#!/bin/bash
#
# CI Monitor Installer
# https://github.com/zyahav/ci-monitor
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/zyahav/ci-monitor/main/install.sh | bash
#
# Options (via environment variables):
#   INSTALL_DIR    - Where to install (default: /usr/local/bin)
#   NO_AUTOSTART   - Set to 1 to skip auto-start setup
#   SPEECH_CMD     - Custom speech command (e.g., "mysay")
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
REPO="zyahav/ci-monitor"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"
CONFIG_DIR="$HOME/.ci-monitor"

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       CI Monitor Installer             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo

# Check dependencies
check_deps() {
    local missing=""
    
    if ! command -v python3 &> /dev/null; then
        missing="$missing python3"
    fi
    
    if ! command -v gh &> /dev/null; then
        missing="$missing gh(GitHub CLI)"
    fi
    
    if ! command -v curl &> /dev/null && ! command -v wget &> /dev/null; then
        missing="$missing curl/wget"
    fi
    
    if [ -n "$missing" ]; then
        echo -e "${RED}Missing dependencies:${NC}$missing"
        echo
        echo "Please install:"
        echo "  - Python 3.10+: https://python.org"
        echo "  - GitHub CLI:   https://cli.github.com/"
        exit 1
    fi
    
    # Check Python version
    python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    major=$(echo $python_version | cut -d. -f1)
    minor=$(echo $python_version | cut -d. -f2)
    
    if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 10 ]); then
        echo -e "${YELLOW}Warning: Python $python_version detected. Python 3.10+ recommended.${NC}"
    fi
    
    # Check gh auth
    if ! gh auth status &> /dev/null; then
        echo -e "${RED}GitHub CLI not authenticated.${NC}"
        echo "Run: gh auth login"
        exit 1
    fi
    
    echo -e "${GREEN}✓${NC} Dependencies OK"
}

# Download the script
download() {
    echo -e "Downloading ci-monitor..."
    
    local url="https://raw.githubusercontent.com/$REPO/main/ci_monitor.py"
    local tmp_file=$(mktemp)
    
    if command -v curl &> /dev/null; then
        curl -fsSL "$url" -o "$tmp_file"
    else
        wget -q "$url" -O "$tmp_file"
    fi
    
    echo "$tmp_file"
}

# Install the script
install_script() {
    local src="$1"
    local dest="$INSTALL_DIR/ci-monitor"
    
    # Create install directory if needed
    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}Creating $INSTALL_DIR (requires sudo)${NC}"
        sudo mkdir -p "$INSTALL_DIR"
    fi
    
    # Check write permission
    if [ -w "$INSTALL_DIR" ]; then
        cp "$src" "$dest"
        chmod +x "$dest"
    else
        echo -e "${YELLOW}Installing to $INSTALL_DIR (requires sudo)${NC}"
        sudo cp "$src" "$dest"
        sudo chmod +x "$dest"
    fi
    
    # Add shebang if not present
    if ! head -1 "$dest" | grep -q "^#!"; then
        local python_path=$(which python3)
        if [ -w "$dest" ]; then
            sed -i '' "1i\\
#!$python_path
" "$dest" 2>/dev/null || sudo sed -i "1i #!$python_path" "$dest"
        else
            sudo sed -i '' "1i\\
#!$python_path
" "$dest" 2>/dev/null || sudo sed -i "1i #!$python_path" "$dest"
        fi
    fi
    
    # Create config directory
    mkdir -p "$CONFIG_DIR"
    
    echo -e "${GREEN}✓${NC} Installed to $dest"
}


# Setup auto-start (macOS LaunchAgent)
setup_macos_autostart() {
    local plist_dir="$HOME/Library/LaunchAgents"
    local plist_file="$plist_dir/com.ci-monitor.plist"
    local python_path=$(which python3)
    
    mkdir -p "$plist_dir"
    
    cat > "$plist_file" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ci-monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>$python_path</string>
        <string>$HOME/.ci-monitor/ci_monitor.py</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.ci-monitor/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.ci-monitor/launchd.log</string>
</dict>
</plist>
EOF
    
    # Copy script to config dir for LaunchAgent
    cp "$INSTALL_DIR/ci-monitor" "$CONFIG_DIR/ci_monitor.py"
    
    # Load the agent
    launchctl unload "$plist_file" 2>/dev/null || true
    launchctl load "$plist_file"
    
    echo -e "${GREEN}✓${NC} Auto-start configured (LaunchAgent)"
}

# Setup auto-start (Linux systemd)
setup_linux_autostart() {
    local service_dir="$HOME/.config/systemd/user"
    local service_file="$service_dir/ci-monitor.service"
    
    mkdir -p "$service_dir"
    
    cat > "$service_file" << EOF
[Unit]
Description=CI Monitor - GitHub Actions notifications
After=network.target

[Service]
Type=simple
ExecStart=$INSTALL_DIR/ci-monitor start
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF
    
    systemctl --user daemon-reload
    systemctl --user enable ci-monitor
    systemctl --user start ci-monitor
    
    echo -e "${GREEN}✓${NC} Auto-start configured (systemd user service)"
}

# Setup auto-start based on OS
setup_autostart() {
    if [ "${NO_AUTOSTART:-0}" = "1" ]; then
        echo -e "${YELLOW}Skipping auto-start setup (NO_AUTOSTART=1)${NC}"
        return
    fi
    
    case "$(uname -s)" in
        Darwin)
            setup_macos_autostart
            ;;
        Linux)
            if command -v systemctl &> /dev/null; then
                setup_linux_autostart
            else
                echo -e "${YELLOW}systemd not found, skipping auto-start${NC}"
            fi
            ;;
        *)
            echo -e "${YELLOW}Auto-start not supported on this OS${NC}"
            ;;
    esac
}

# Configure custom speech command
setup_speech() {
    if [ -n "$SPEECH_CMD" ]; then
        echo -e "Setting speech command to: $SPEECH_CMD"
        cat > "$CONFIG_DIR/config.json" << EOF
{
  "check_interval": 60,
  "speech_enabled": true,
  "speech_command": "$SPEECH_CMD",
  "notify_success": true,
  "notify_failure": true
}
EOF
        echo -e "${GREEN}✓${NC} Speech configured"
    fi
}

# Print success message
print_success() {
    echo
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     Installation Complete! 🎉          ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo
    echo "Quick start:"
    echo "  ci-monitor add owner/repo    # Add a repository"
    echo "  ci-monitor start             # Start monitoring"
    echo "  ci-monitor status            # Check status"
    echo "  ci-monitor history           # View activity"
    echo
    echo "Configuration:"
    echo "  ci-monitor config            # View settings"
    echo "  ci-monitor config speech_enabled false  # Disable speech"
    echo
}

# Main
main() {
    check_deps
    
    local script_file
    script_file=$(download)
    
    install_script "$script_file"
    rm -f "$script_file"
    
    setup_speech
    setup_autostart
    
    print_success
}

main "$@"

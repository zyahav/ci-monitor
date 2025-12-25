# CI Monitor 🔔

A lightweight daemon that monitors GitHub Actions workflows and announces results via audio notifications. Perfect for developers and AI agents who want real-time CI/CD feedback without constantly checking GitHub.

## Features

- 🎯 **Simple CLI** - Easy to use command-line interface
- 🔊 **Audio Notifications** - Hear when builds pass or fail
- 🖥️ **Cross-Platform** - Works on macOS, Linux, and Windows
- 🚀 **Auto-Start** - Runs automatically on login (optional)
- 📊 **History Tracking** - Review past CI/CD activity
- ⚙️ **Configurable** - Customize check intervals, speech, and more

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/zyahav/ci-monitor/main/install.sh | bash
```

### Prerequisites

- **Python 3.10+** - [python.org](https://python.org)
- **GitHub CLI** - [cli.github.com](https://cli.github.com) (must be authenticated with `gh auth login`)

## Usage

### Add Repositories to Monitor

```bash
ci-monitor add owner/repo
ci-monitor add facebook/react
ci-monitor add your-org/your-project
```

### Start Monitoring

```bash
ci-monitor start
```

The daemon will run in the background and announce CI results via text-to-speech.

### Other Commands

```bash
ci-monitor status      # Check if daemon is running
ci-monitor stop        # Stop the daemon
ci-monitor history     # View recent CI activity
ci-monitor list        # List monitored repositories
ci-monitor remove owner/repo  # Stop monitoring a repo
ci-monitor check       # Run a single check (for testing)
```

## Configuration

View current settings:
```bash
ci-monitor config
```

Modify settings:
```bash
# Disable audio notifications
ci-monitor config speech_enabled false

# Change check interval (seconds)
ci-monitor config check_interval 120

# Use custom speech command
ci-monitor config speech_command mysay

# Only notify on failures
ci-monitor config notify_success false
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `check_interval` | `60` | Seconds between checks |
| `speech_enabled` | `true` | Enable audio notifications |
| `speech_command` | `null` | Custom TTS command (auto-detect if null) |
| `notify_success` | `true` | Announce successful builds |
| `notify_failure` | `true` | Announce failed builds |

## How It Works

1. **Daemon Mode**: Runs in the background, checking your repositories periodically
2. **GitHub CLI**: Uses `gh run list` to fetch latest workflow status
3. **Deduplication**: Tracks notified runs in SQLite to avoid repeats
4. **Text-to-Speech**: Uses platform-native TTS (macOS `say`, Linux `espeak`, etc.)


## Auto-Start Setup

The installer automatically configures auto-start. If you need to set it up manually:

### macOS (LaunchAgent)

```bash
# The installer creates ~/Library/LaunchAgents/com.ci-monitor.plist
# To manually load/unload:
launchctl load ~/Library/LaunchAgents/com.ci-monitor.plist
launchctl unload ~/Library/LaunchAgents/com.ci-monitor.plist
```

### Linux (systemd)

```bash
# The installer creates ~/.config/systemd/user/ci-monitor.service
systemctl --user enable ci-monitor
systemctl --user start ci-monitor
systemctl --user status ci-monitor
```

## For AI Agents 🤖

CI Monitor is designed to be easily installed and operated by AI coding agents. Here's a typical workflow:

```bash
# 1. Install (one command)
curl -fsSL https://raw.githubusercontent.com/zyahav/ci-monitor/main/install.sh | bash

# 2. Add the repo you're working on
ci-monitor add owner/repo

# 3. Start monitoring
ci-monitor start

# 4. Check status anytime
ci-monitor status

# 5. View history
ci-monitor history
```

### Silent Mode (No Speech)

For environments without audio:

```bash
ci-monitor config speech_enabled false
```

### Environment Variables for Install

```bash
# Custom install location
INSTALL_DIR=/opt/bin curl -fsSL .../install.sh | bash

# Skip auto-start setup
NO_AUTOSTART=1 curl -fsSL .../install.sh | bash

# Custom speech command
SPEECH_CMD=mysay curl -fsSL .../install.sh | bash
```

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/zyahav/ci-monitor/main/uninstall.sh | bash
```

Or manually:

```bash
ci-monitor stop
rm /usr/local/bin/ci-monitor
rm -rf ~/.ci-monitor
# macOS: rm ~/Library/LaunchAgents/com.ci-monitor.plist
# Linux: rm ~/.config/systemd/user/ci-monitor.service
```

## Troubleshooting

### "gh: command not found"

Install GitHub CLI: https://cli.github.com/

### "GitHub CLI not authenticated"

Run: `gh auth login`

### No audio on Linux

Install espeak: `sudo apt install espeak`

### Daemon not starting on login

Check the LaunchAgent (macOS):
```bash
launchctl list | grep ci-monitor
cat ~/Library/LaunchAgents/com.ci-monitor.plist
```

Check systemd (Linux):
```bash
systemctl --user status ci-monitor
journalctl --user -u ci-monitor
```

## Files

| Path | Description |
|------|-------------|
| `/usr/local/bin/ci-monitor` | The CLI executable |
| `~/.ci-monitor/repos.txt` | List of monitored repositories |
| `~/.ci-monitor/config.json` | Configuration file |
| `~/.ci-monitor/history.log` | Notification history |
| `~/.ci-monitor/state.db` | SQLite database for deduplication |
| `~/.ci-monitor/daemon.log` | Daemon output log |
| `~/.ci-monitor/daemon.pid` | PID file when running |

## License

MIT

## Contributing

Issues and pull requests welcome at [github.com/zyahav/ci-monitor](https://github.com/zyahav/ci-monitor)

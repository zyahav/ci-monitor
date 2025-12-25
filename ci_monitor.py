#!/usr/bin/env python3
"""
CI Monitor - GitHub Actions notification daemon.
Monitors repositories and announces CI/CD results via audio notifications.

Cross-platform support:
- macOS: Uses 'say' command or custom speech command
- Linux: Uses 'espeak' or custom speech command  
- Windows: Uses PowerShell speech or custom command
- All: Can be disabled or use custom notification command
"""

from __future__ import annotations

import subprocess
import json
import sqlite3
import time
import os
import sys
import argparse
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional

# Configuration
CONFIG_DIR = Path.home() / ".ci-monitor"
DB_PATH = CONFIG_DIR / "state.db"
REPOS_FILE = CONFIG_DIR / "repos.txt"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "history.log"
PID_FILE = CONFIG_DIR / "daemon.pid"

# Defaults
DEFAULT_CHECK_INTERVAL = 60  # seconds
DEFAULT_CONFIG = {
    "check_interval": DEFAULT_CHECK_INTERVAL,
    "speech_enabled": True,
    "speech_command": None,  # None = auto-detect, or custom command
    "notify_success": True,
    "notify_failure": True,
}


def load_config() -> dict:
    """Load configuration from file or return defaults."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                user_config = json.load(f)
                return {**DEFAULT_CONFIG, **user_config}
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """Save configuration to file."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_check_interval() -> int:
    """Get the check interval from config."""
    return load_config().get("check_interval", DEFAULT_CHECK_INTERVAL)


def init_db():
    """Initialize SQLite database for tracking notified runs."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notified_runs (
            run_id TEXT PRIMARY KEY,
            repo TEXT,
            workflow TEXT,
            conclusion TEXT,
            notified_at TEXT
        )
    """)
    # Clean up old entries (keep last 7 days)
    cursor.execute("""
        DELETE FROM notified_runs 
        WHERE notified_at < datetime('now', '-7 days')
    """)
    conn.commit()
    conn.close()


def get_repos() -> list[str]:
    """Load repository list from config file."""
    if not REPOS_FILE.exists():
        return []
    with open(REPOS_FILE, "r") as f:
        repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return repos


def add_repo(repo: str) -> bool:
    """Add a repository to the watch list."""
    # Validate format
    if "/" not in repo or repo.count("/") != 1:
        print(f"❌ Invalid format. Use: owner/repo")
        return False
    
    repos = get_repos()
    if repo in repos:
        print(f"Repository '{repo}' is already being monitored.")
        return False
    
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(REPOS_FILE, "a") as f:
        f.write(f"{repo}\n")
    print(f"✅ Added '{repo}' to watch list.")
    return True


def remove_repo(repo: str) -> bool:
    """Remove a repository from the watch list."""
    repos = get_repos()
    if repo not in repos:
        print(f"Repository '{repo}' is not in the watch list.")
        return False
    repos.remove(repo)
    with open(REPOS_FILE, "w") as f:
        for r in repos:
            f.write(f"{r}\n")
    print(f"✅ Removed '{repo}' from watch list.")
    return True


def list_repos():
    """List all monitored repositories."""
    repos = get_repos()
    if not repos:
        print("No repositories configured.")
        print("Add repos with: ci-monitor add <owner/repo>")
        return
    print("Monitored repositories:")
    for repo in repos:
        print(f"  • {repo}")


def was_notified(run_id: str) -> bool:
    """Check if we already notified about this run."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM notified_runs WHERE run_id = ?", (run_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def mark_notified(run_id: str, repo: str, workflow: str, conclusion: str):
    """Mark a run as notified."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO notified_runs (run_id, repo, workflow, conclusion, notified_at)
        VALUES (?, ?, ?, ?, ?)
    """, (run_id, repo, workflow, conclusion, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def log_event(repo: str, workflow: str, conclusion: str):
    """Log event to history file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    icon = "✅" if conclusion == "success" else "❌" if conclusion == "failure" else "⚠️"
    repo_short = repo.split("/")[-1]  # Just the repo name, not owner
    line = f"{timestamp} | {repo_short:20} | {workflow:15} | {icon} {conclusion}\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)


def detect_speech_command() -> Optional[list[str]]:
    """Detect the best available speech command for this platform."""
    system = platform.system()
    
    if system == "Darwin":  # macOS
        # Check for custom 'mysay' first, then fall back to 'say'
        for cmd in ["mysay", "say"]:
            if subprocess.run(["which", cmd], capture_output=True).returncode == 0:
                return [cmd]
    
    elif system == "Linux":
        # Try common TTS tools
        for cmd in ["espeak", "espeak-ng", "festival", "spd-say"]:
            if subprocess.run(["which", cmd], capture_output=True).returncode == 0:
                if cmd == "festival":
                    return ["festival", "--tts"]
                elif cmd == "spd-say":
                    return ["spd-say"]
                return [cmd]
    
    elif system == "Windows":
        # PowerShell speech synthesis
        return ["powershell", "-Command", 
                "Add-Type -AssemblyName System.Speech; "
                "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak"]
    
    return None


def speak(message: str):
    """Announce message using text-to-speech."""
    config = load_config()
    
    if not config.get("speech_enabled", True):
        return
    
    # Get speech command
    custom_cmd = config.get("speech_command")
    if custom_cmd:
        # Custom command specified
        if isinstance(custom_cmd, str):
            cmd = [custom_cmd, message]
        else:
            cmd = custom_cmd + [message]
    else:
        # Auto-detect
        speech_cmd = detect_speech_command()
        if not speech_cmd:
            return  # No speech available
        cmd = speech_cmd + [message]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        print(f"Speech timeout for: {message}")
    except Exception as e:
        print(f"Speech error: {e}")


def get_latest_run(repo: str) -> Optional[dict]:
    """Get the latest workflow run for a repository."""
    try:
        result = subprocess.run(
            ["gh", "run", "list", "--repo", repo, "--limit", "1", 
             "--json", "databaseId,status,conclusion,name,updatedAt"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return None
        runs = json.loads(result.stdout)
        if runs:
            return runs[0]
    except subprocess.TimeoutExpired:
        print(f"Timeout checking {repo}")
    except Exception as e:
        print(f"Error checking {repo}: {e}")
    return None


def check_repos():
    """Check all repositories for completed runs."""
    config = load_config()
    repos = get_repos()
    if not repos:
        return
    
    for repo in repos:
        run = get_latest_run(repo)
        if not run:
            continue
        
        run_id = str(run.get("databaseId", ""))
        status = run.get("status", "")
        conclusion = run.get("conclusion", "")
        workflow = run.get("name", "Workflow")
        
        # Only notify on completed runs we haven't seen
        if status == "completed" and run_id and not was_notified(run_id):
            repo_name = repo.split("/")[-1]
            
            # Log it
            log_event(repo, workflow, conclusion)
            
            # Speak based on config
            should_speak = (
                (conclusion == "success" and config.get("notify_success", True)) or
                (conclusion == "failure" and config.get("notify_failure", True)) or
                (conclusion not in ["success", "failure"])
            )
            
            if should_speak:
                if conclusion == "success":
                    speak(f"{repo_name}: {workflow} passed")
                elif conclusion == "failure":
                    speak(f"Attention! {repo_name}: {workflow} failed")
                else:
                    speak(f"{repo_name}: {workflow} completed with {conclusion}")
            
            # Mark as notified
            mark_notified(run_id, repo, workflow, conclusion)
            
            # Print to console too
            icon = "✅" if conclusion == "success" else "❌"
            print(f"{icon} {repo} - {workflow}: {conclusion}")


def show_history(lines: int = 20):
    """Show recent notification history."""
    if not LOG_FILE.exists():
        print("No history yet.")
        return
    
    with open(LOG_FILE, "r") as f:
        all_lines = f.readlines()
    
    recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
    
    if not recent:
        print("No history yet.")
        return
    
    print("Recent CI/CD Activity:")
    print("-" * 60)
    for line in recent:
        print(line.rstrip())


def daemon_running() -> tuple[bool, Optional[int]]:
    """Check if daemon is already running. Returns (running, pid)."""
    if not PID_FILE.exists():
        return False, None
    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process exists
        os.kill(pid, 0)
        return True, pid
    except (ProcessLookupError, ValueError, PermissionError):
        # Process doesn't exist, clean up stale PID file
        PID_FILE.unlink(missing_ok=True)
        return False, None


def start_daemon():
    """Start the monitoring daemon."""
    running, pid = daemon_running()
    if running:
        print(f"⚠️  Daemon is already running (PID: {pid}).")
        print("   Use 'ci-monitor stop' to stop it first.")
        return
    
    repos = get_repos()
    if not repos:
        print("❌ No repositories configured.")
        print("   Add repos first: ci-monitor add <owner/repo>")
        return
    
    # Check for gh CLI
    if subprocess.run(["which", "gh"], capture_output=True).returncode != 0:
        print("❌ GitHub CLI (gh) not found.")
        print("   Install: https://cli.github.com/")
        return
    
    check_interval = get_check_interval()
    
    # Fork to background
    try:
        pid = os.fork()
    except AttributeError:
        # Windows doesn't have fork - run in foreground
        print("Running in foreground mode (Windows)...")
        PID_FILE.write_text(str(os.getpid()))
        run_daemon_loop()
        return
    
    if pid > 0:
        # Parent process
        print(f"✅ CI Monitor started (PID: {pid})")
        print(f"   Monitoring {len(repos)} repositories every {check_interval}s")
        print(f"   View activity: ci-monitor history")
        print(f"   Stop daemon:   ci-monitor stop")
        return
    
    # Child process - become daemon
    os.setsid()
    
    # Write PID file
    PID_FILE.write_text(str(os.getpid()))
    
    run_daemon_loop()


def run_daemon_loop():
    """Main daemon loop."""
    check_interval = get_check_interval()
    
    # Redirect stdout/stderr to log
    daemon_log = CONFIG_DIR / "daemon.log"
    sys.stdout = open(daemon_log, "a")
    sys.stderr = sys.stdout
    
    print(f"\n{'='*40}")
    print(f"Daemon started at {datetime.now().isoformat()}")
    print(f"{'='*40}")
    
    try:
        while True:
            check_repos()
            time.sleep(check_interval)
    except Exception as e:
        print(f"Daemon error: {e}")
    finally:
        PID_FILE.unlink(missing_ok=True)


def stop_daemon():
    """Stop the monitoring daemon."""
    running, pid = daemon_running()
    if not running:
        print("Daemon is not running.")
        return
    
    try:
        os.kill(pid, 15)  # SIGTERM
        PID_FILE.unlink(missing_ok=True)
        print(f"✅ Daemon stopped (was PID: {pid})")
    except Exception as e:
        print(f"Error stopping daemon: {e}")


def show_status():
    """Show daemon status."""
    running, pid = daemon_running()
    config = load_config()
    check_interval = config.get("check_interval", DEFAULT_CHECK_INTERVAL)
    
    if running:
        repos = get_repos()
        print(f"✅ CI Monitor is RUNNING (PID: {pid})")
        print(f"   Monitoring: {len(repos)} repositories")
        print(f"   Interval:   {check_interval} seconds")
        print(f"   Speech:     {'enabled' if config.get('speech_enabled', True) else 'disabled'}")
    else:
        print("⚪ CI Monitor is NOT running")
        print("   Start with: ci-monitor start")
    
    print()
    repos = get_repos()
    if repos:
        print("Watched repositories:")
        for repo in repos:
            print(f"   • {repo}")
    else:
        print("No repositories configured.")
        print("Add with: ci-monitor add <owner/repo>")


def run_once():
    """Run a single check (useful for testing)."""
    repos = get_repos()
    if not repos:
        print("No repositories configured.")
        return
    
    print(f"Checking {len(repos)} repositories...")
    check_repos()
    print("Done.")


def configure(key: str = None, value: str = None):
    """View or modify configuration."""
    config = load_config()
    
    if key is None:
        # Show current config
        print("Current configuration:")
        print(f"  check_interval:  {config.get('check_interval', DEFAULT_CHECK_INTERVAL)}s")
        print(f"  speech_enabled:  {config.get('speech_enabled', True)}")
        print(f"  speech_command:  {config.get('speech_command') or '(auto-detect)'}")
        print(f"  notify_success:  {config.get('notify_success', True)}")
        print(f"  notify_failure:  {config.get('notify_failure', True)}")
        print()
        print("Modify with: ci-monitor config <key> <value>")
        print("Example: ci-monitor config speech_enabled false")
        return
    
    # Modify config
    if key not in DEFAULT_CONFIG:
        print(f"❌ Unknown config key: {key}")
        print(f"   Valid keys: {', '.join(DEFAULT_CONFIG.keys())}")
        return
    
    # Parse value
    if value is None:
        print(f"Current value of {key}: {config.get(key)}")
        return
    
    if key == "check_interval":
        try:
            config[key] = int(value)
        except ValueError:
            print(f"❌ Invalid value for {key}: must be an integer")
            return
    elif key in ["speech_enabled", "notify_success", "notify_failure"]:
        config[key] = value.lower() in ["true", "1", "yes", "on"]
    elif key == "speech_command":
        config[key] = value if value.lower() != "none" else None
    else:
        config[key] = value
    
    save_config(config)
    print(f"✅ Set {key} = {config[key]}")


def main():
    """Main entry point."""
    # Ensure config directory exists
    CONFIG_DIR.mkdir(exist_ok=True)
    init_db()
    
    parser = argparse.ArgumentParser(
        description="CI Monitor - GitHub Actions notification daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ci-monitor add owner/repo    Add a repository to monitor
  ci-monitor start             Start background monitoring
  ci-monitor status            Check if daemon is running
  ci-monitor history           View recent activity
  ci-monitor stop              Stop monitoring
  ci-monitor config            View configuration
  ci-monitor config speech_enabled false   Disable speech
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # start
    subparsers.add_parser("start", help="Start the monitoring daemon")
    
    # stop
    subparsers.add_parser("stop", help="Stop the monitoring daemon")
    
    # status
    subparsers.add_parser("status", help="Show daemon status")
    
    # add
    add_parser = subparsers.add_parser("add", help="Add a repository to monitor")
    add_parser.add_argument("repo", help="Repository (owner/repo)")
    
    # remove
    rm_parser = subparsers.add_parser("remove", help="Remove a repository")
    rm_parser.add_argument("repo", help="Repository (owner/repo)")
    
    # list
    subparsers.add_parser("list", help="List monitored repositories")
    
    # history
    hist_parser = subparsers.add_parser("history", help="Show notification history")
    hist_parser.add_argument("-n", type=int, default=20, help="Number of lines")
    
    # check (single run, for testing)
    subparsers.add_parser("check", help="Run a single check (for testing)")
    
    # config
    config_parser = subparsers.add_parser("config", help="View or modify configuration")
    config_parser.add_argument("key", nargs="?", help="Config key")
    config_parser.add_argument("value", nargs="?", help="New value")
    
    args = parser.parse_args()
    
    if args.command == "start":
        start_daemon()
    elif args.command == "stop":
        stop_daemon()
    elif args.command == "status":
        show_status()
    elif args.command == "add":
        add_repo(args.repo)
    elif args.command == "remove":
        remove_repo(args.repo)
    elif args.command == "list":
        list_repos()
    elif args.command == "history":
        show_history(args.n)
    elif args.command == "check":
        run_once()
    elif args.command == "config":
        configure(args.key, args.value)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

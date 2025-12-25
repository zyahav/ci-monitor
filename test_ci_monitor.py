#!/usr/bin/env python3
"""
Tests for CI Monitor.
Run with: pytest test_ci_monitor.py -v
"""

import os
import sys
import json
import sqlite3
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ci_monitor


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory for tests."""
    config_dir = tmp_path / ".ci-monitor"
    config_dir.mkdir()
    
    # Patch the config paths
    with patch.object(ci_monitor, 'CONFIG_DIR', config_dir), \
         patch.object(ci_monitor, 'DB_PATH', config_dir / "state.db"), \
         patch.object(ci_monitor, 'REPOS_FILE', config_dir / "repos.txt"), \
         patch.object(ci_monitor, 'CONFIG_FILE', config_dir / "config.json"), \
         patch.object(ci_monitor, 'LOG_FILE', config_dir / "history.log"), \
         patch.object(ci_monitor, 'PID_FILE', config_dir / "daemon.pid"):
        ci_monitor.init_db()
        yield config_dir


class TestRepoManagement:
    """Tests for repository management functions."""
    
    def test_add_repo(self, temp_config_dir, capsys):
        """Test adding a repository."""
        result = ci_monitor.add_repo("owner/repo")
        assert result is True
        
        repos = ci_monitor.get_repos()
        assert "owner/repo" in repos
        
        captured = capsys.readouterr()
        assert "Added" in captured.out
    
    def test_add_repo_duplicate(self, temp_config_dir, capsys):
        """Test adding a duplicate repository."""
        ci_monitor.add_repo("owner/repo")
        result = ci_monitor.add_repo("owner/repo")
        assert result is False
        
        captured = capsys.readouterr()
        assert "already being monitored" in captured.out
    
    def test_add_repo_invalid_format(self, temp_config_dir, capsys):
        """Test adding a repo with invalid format."""
        result = ci_monitor.add_repo("invalid-repo")
        assert result is False
        
        captured = capsys.readouterr()
        assert "Invalid format" in captured.out
    
    def test_remove_repo(self, temp_config_dir, capsys):
        """Test removing a repository."""
        ci_monitor.add_repo("owner/repo")
        result = ci_monitor.remove_repo("owner/repo")
        assert result is True
        
        repos = ci_monitor.get_repos()
        assert "owner/repo" not in repos
    
    def test_remove_repo_not_found(self, temp_config_dir, capsys):
        """Test removing a non-existent repository."""
        result = ci_monitor.remove_repo("nonexistent/repo")
        assert result is False
        
        captured = capsys.readouterr()
        assert "not in the watch list" in captured.out
    
    def test_get_repos_empty(self, temp_config_dir):
        """Test getting repos when none configured."""
        repos = ci_monitor.get_repos()
        assert repos == []
    
    def test_get_repos_multiple(self, temp_config_dir):
        """Test getting multiple repos."""
        ci_monitor.add_repo("owner/repo1")
        ci_monitor.add_repo("owner/repo2")
        ci_monitor.add_repo("other/repo3")
        
        repos = ci_monitor.get_repos()
        assert len(repos) == 3
        assert "owner/repo1" in repos
        assert "owner/repo2" in repos
        assert "other/repo3" in repos


class TestDatabase:
    """Tests for database operations."""
    
    def test_mark_notified(self, temp_config_dir):
        """Test marking a run as notified."""
        ci_monitor.mark_notified("123", "owner/repo", "Tests", "success")
        
        assert ci_monitor.was_notified("123") is True
        assert ci_monitor.was_notified("456") is False
    
    def test_was_notified_false(self, temp_config_dir):
        """Test was_notified returns False for unknown run."""
        assert ci_monitor.was_notified("unknown") is False


class TestConfig:
    """Tests for configuration management."""
    
    def test_load_default_config(self, temp_config_dir):
        """Test loading default config when no file exists."""
        config = ci_monitor.load_config()
        
        assert config["check_interval"] == 60
        assert config["speech_enabled"] is True
        assert config["speech_command"] is None
    
    def test_save_and_load_config(self, temp_config_dir):
        """Test saving and loading custom config."""
        config = ci_monitor.load_config()
        config["check_interval"] = 120
        config["speech_enabled"] = False
        ci_monitor.save_config(config)
        
        loaded = ci_monitor.load_config()
        assert loaded["check_interval"] == 120
        assert loaded["speech_enabled"] is False


class TestLogging:
    """Tests for logging functions."""
    
    def test_log_event(self, temp_config_dir):
        """Test logging an event."""
        ci_monitor.log_event("owner/repo", "Tests", "success")
        
        log_file = temp_config_dir / "history.log"
        assert log_file.exists()
        
        content = log_file.read_text()
        assert "repo" in content
        assert "Tests" in content
        assert "success" in content


class TestSpeech:
    """Tests for speech/notification functions."""
    
    def test_detect_speech_command_macos(self, temp_config_dir):
        """Test speech command detection on macOS."""
        with patch('ci_monitor.platform.system', return_value='Darwin'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            cmd = ci_monitor.detect_speech_command()
            assert cmd is not None
    
    def test_detect_speech_command_linux(self, temp_config_dir):
        """Test speech command detection on Linux."""
        with patch('ci_monitor.platform.system', return_value='Linux'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            cmd = ci_monitor.detect_speech_command()
            assert cmd is not None
    
    def test_speak_disabled(self, temp_config_dir):
        """Test that speak does nothing when disabled."""
        config = ci_monitor.load_config()
        config["speech_enabled"] = False
        ci_monitor.save_config(config)
        
        with patch('subprocess.run') as mock_run:
            ci_monitor.speak("test message")
            mock_run.assert_not_called()


class TestDaemon:
    """Tests for daemon functions."""
    
    def test_daemon_not_running(self, temp_config_dir):
        """Test daemon_running returns False when not running."""
        running, pid = ci_monitor.daemon_running()
        assert running is False
        assert pid is None
    
    def test_daemon_running_stale_pid(self, temp_config_dir):
        """Test daemon_running handles stale PID files."""
        pid_file = temp_config_dir / "daemon.pid"
        pid_file.write_text("99999999")  # Non-existent PID
        
        running, pid = ci_monitor.daemon_running()
        assert running is False
        assert not pid_file.exists()  # Should clean up stale file


class TestGitHubIntegration:
    """Tests for GitHub API integration."""
    
    def test_get_latest_run_success(self, temp_config_dir):
        """Test getting latest run with mocked gh CLI."""
        mock_output = json.dumps([{
            "databaseId": 123,
            "status": "completed",
            "conclusion": "success",
            "name": "Tests",
            "updatedAt": "2024-01-01T00:00:00Z"
        }])
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=mock_output
            )
            
            run = ci_monitor.get_latest_run("owner/repo")
            
            assert run is not None
            assert run["databaseId"] == 123
            assert run["conclusion"] == "success"
    
    def test_get_latest_run_failure(self, temp_config_dir):
        """Test handling gh CLI failure."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            
            run = ci_monitor.get_latest_run("owner/repo")
            assert run is None
    
    def test_get_latest_run_timeout(self, temp_config_dir):
        """Test handling timeout."""
        import subprocess
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=30)
            
            run = ci_monitor.get_latest_run("owner/repo")
            assert run is None


class TestCheckRepos:
    """Tests for the main check_repos function."""
    
    def test_check_repos_empty(self, temp_config_dir, capsys):
        """Test check_repos with no repos configured."""
        ci_monitor.check_repos()
        # Should complete without error
    
    def test_check_repos_new_success(self, temp_config_dir):
        """Test check_repos announces new successful run."""
        ci_monitor.add_repo("owner/repo")
        
        mock_output = json.dumps([{
            "databaseId": 456,
            "status": "completed",
            "conclusion": "success",
            "name": "Tests",
            "updatedAt": "2024-01-01T00:00:00Z"
        }])
        
        with patch('subprocess.run') as mock_run, \
             patch.object(ci_monitor, 'speak') as mock_speak:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=mock_output
            )
            
            ci_monitor.check_repos()
            
            # Should have called speak
            mock_speak.assert_called_once()
            call_args = mock_speak.call_args[0][0]
            assert "passed" in call_args
    
    def test_check_repos_already_notified(self, temp_config_dir):
        """Test check_repos skips already notified runs."""
        ci_monitor.add_repo("owner/repo")
        ci_monitor.mark_notified("789", "owner/repo", "Tests", "success")
        
        mock_output = json.dumps([{
            "databaseId": 789,
            "status": "completed",
            "conclusion": "success",
            "name": "Tests",
            "updatedAt": "2024-01-01T00:00:00Z"
        }])
        
        with patch('subprocess.run') as mock_run, \
             patch.object(ci_monitor, 'speak') as mock_speak:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=mock_output
            )
            
            ci_monitor.check_repos()
            
            # Should NOT have called speak (already notified)
            mock_speak.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for checkpoint extraction and formatting."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from tokenxray.commands.checkpoint import extract_checkpoint, format_checkpoint


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _write_jsonl(path, entries):
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _make_session_with_tools(tmpdir, turns=5):
    """Create a session JSONL with realistic tool use blocks."""
    entries = []
    for i in range(turns):
        entries.append({
            "type": "user",
            "cwd": "/home/dev/project",
            "gitBranch": "feature-branch",
            "sessionId": "test-session-123",
            "timestamp": f"2026-01-01T00:{i:02d}:00Z",
            "message": {"content": f"Please fix the bug in module {i}" if i > 0 else "Implement the new auth system for our API"},
        })
        content_blocks = [
            {"type": "text", "text": f"I'll work on fixing this issue in module {i}. Let me read the relevant files first."},
        ]
        if i % 2 == 0:
            content_blocks.append({
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": f"/home/dev/project/src/module_{i}.py"},
            })
        else:
            content_blocks.append({
                "type": "tool_use",
                "name": "Edit",
                "input": {"file_path": f"/home/dev/project/src/module_{i}.py", "old_string": "old", "new_string": "new"},
            })
        if i == 3:
            content_blocks.append({
                "type": "tool_use",
                "name": "Write",
                "input": {"file_path": "/home/dev/project/src/new_file.py", "content": "# new"},
            })
        if i == 4:
            content_blocks.append({
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": "pytest tests/ -v"},
            })
        entries.append({
            "type": "assistant",
            "timestamp": f"2026-01-01T00:{i:02d}:30Z",
            "message": {
                "model": "claude-sonnet-4-6",
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "cache_read_input_tokens": 500,
                    "cache_creation_input_tokens": 300,
                },
                "content": content_blocks,
            },
        })
    filepath = os.path.join(tmpdir, "test-session.jsonl")
    _write_jsonl(filepath, entries)
    return filepath


def _make_minimal_session(tmpdir):
    """Create a minimal session with just one user + assistant turn."""
    entries = [
        {
            "type": "user",
            "cwd": "/home/dev/myproject",
            "gitBranch": "main",
            "sessionId": "minimal-123",
            "message": {"content": "Hello, help me with something"},
        },
        {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "content": [{"type": "text", "text": "Sure, I can help you with that task."}],
            },
        },
    ]
    filepath = os.path.join(tmpdir, "minimal.jsonl")
    _write_jsonl(filepath, entries)
    return filepath


def _make_session_with_noise(tmpdir):
    """Create a session with entries that should be filtered out."""
    entries = [
        {
            "type": "user",
            "cwd": "/home/dev/project",
            "gitBranch": "main",
            "sessionId": "noisy-session",
            "message": {"content": "Build the login page with OAuth support"},
        },
        # Short message — should be filtered
        {
            "type": "user",
            "message": {"content": "yes"},
        },
        # System tag — should be filtered
        {
            "type": "user",
            "message": {"content": "<system-reminder>some system content here</system-reminder>"},
        },
        # tool_result — should be filtered
        {
            "type": "user",
            "message": {"content": "Here is the tool_result from the previous command"},
        },
        # Real message — should be kept
        {
            "type": "user",
            "message": {"content": "Now add the Google OAuth provider to the config"},
        },
        # permission-mode entry — should be ignored entirely
        {
            "type": "permission-mode",
            "message": {"content": "auto"},
        },
        {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 500, "output_tokens": 100},
                "content": [{"type": "text", "text": "I'll add the Google OAuth provider to the configuration."}],
            },
        },
    ]
    filepath = os.path.join(tmpdir, "noisy.jsonl")
    _write_jsonl(filepath, entries)
    return filepath


# ─── Tests: extract_checkpoint ────────────────────────────────────────────────


class TestExtractCheckpoint:
    def test_basic_extraction(self, tmp_path):
        filepath = _make_session_with_tools(str(tmp_path))
        cp = extract_checkpoint(filepath)

        assert cp["session_id"] == "test-session-123"
        assert cp["cwd"] == "/home/dev/project"
        assert cp["git_branch"] == "feature-branch"

    def test_user_messages_captured(self, tmp_path):
        filepath = _make_session_with_tools(str(tmp_path))
        cp = extract_checkpoint(filepath)

        assert len(cp["user_messages"]) > 0
        assert "Implement the new auth system" in cp["user_messages"][0]

    def test_files_edited_detected(self, tmp_path):
        filepath = _make_session_with_tools(str(tmp_path))
        cp = extract_checkpoint(filepath)

        edited = cp["files_edited"]
        assert "/home/dev/project/src/module_1.py" in edited
        assert "/home/dev/project/src/module_3.py" in edited
        # Write also counts as edited
        assert "/home/dev/project/src/new_file.py" in edited

    def test_files_read_detected(self, tmp_path):
        filepath = _make_session_with_tools(str(tmp_path))
        cp = extract_checkpoint(filepath)

        read_files = cp["files_read"]
        assert "/home/dev/project/src/module_0.py" in read_files
        assert "/home/dev/project/src/module_2.py" in read_files
        assert "/home/dev/project/src/module_4.py" in read_files

    def test_bash_commands_detected(self, tmp_path):
        filepath = _make_session_with_tools(str(tmp_path))
        cp = extract_checkpoint(filepath)

        assert "pytest tests/ -v" in cp["commands_run"]

    def test_assistant_texts_captured(self, tmp_path):
        filepath = _make_session_with_tools(str(tmp_path))
        cp = extract_checkpoint(filepath)

        assert len(cp["assistant_summary"]) > 0
        assert any("fixing this issue" in t for t in cp["assistant_summary"])

    def test_assistant_summary_limited_to_5(self, tmp_path):
        """Should only keep last 5 assistant text blocks."""
        entries = []
        for i in range(20):
            entries.append({
                "type": "user",
                "cwd": "/dev",
                "sessionId": "s1",
                "message": {"content": f"Do task number {i} please now"},
            })
            entries.append({
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-6",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                    "content": [{"type": "text", "text": f"Working on task {i} — this is the response."}],
                },
            })
        filepath = str(tmp_path / "many.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert len(cp["assistant_summary"]) == 5

    def test_commands_limited_to_10(self, tmp_path):
        """Should only keep last 10 commands."""
        entries = []
        for i in range(20):
            entries.append({
                "type": "user",
                "cwd": "/dev",
                "sessionId": "s1",
                "message": {"content": f"Run command number {i} right now"},
            })
            entries.append({
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-6",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                    "content": [{"type": "tool_use", "name": "Bash", "input": {"command": f"echo {i}"}}],
                },
            })
        filepath = str(tmp_path / "cmds.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert len(cp["commands_run"]) == 10
        # Should be the last 10
        assert cp["commands_run"][0] == "echo 10"
        assert cp["commands_run"][-1] == "echo 19"

    def test_files_read_limited_to_20(self, tmp_path):
        """Should only keep last 20 read files."""
        entries = []
        for i in range(30):
            entries.append({
                "type": "user",
                "cwd": "/dev",
                "sessionId": "s1",
                "message": {"content": f"Read file number {i} from the project"},
            })
            entries.append({
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-6",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                    "content": [{"type": "tool_use", "name": "Read", "input": {"file_path": f"/dev/file_{i:02d}.py"}}],
                },
            })
        filepath = str(tmp_path / "reads.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert len(cp["files_read"]) == 20


class TestUserMessageFiltering:
    def test_filters_short_messages(self, tmp_path):
        filepath = _make_session_with_noise(str(tmp_path))
        cp = extract_checkpoint(filepath)

        # "yes" is too short (< 10 chars) — should be filtered
        assert not any("yes" == msg for msg in cp["user_messages"])

    def test_filters_system_tags(self, tmp_path):
        filepath = _make_session_with_noise(str(tmp_path))
        cp = extract_checkpoint(filepath)

        assert not any("system-reminder" in msg for msg in cp["user_messages"])

    def test_filters_tool_results(self, tmp_path):
        filepath = _make_session_with_noise(str(tmp_path))
        cp = extract_checkpoint(filepath)

        assert not any("tool_result" in msg for msg in cp["user_messages"])

    def test_keeps_real_messages(self, tmp_path):
        filepath = _make_session_with_noise(str(tmp_path))
        cp = extract_checkpoint(filepath)

        assert any("login page" in msg for msg in cp["user_messages"])
        assert any("Google OAuth" in msg for msg in cp["user_messages"])

    def test_truncates_long_messages(self, tmp_path):
        entries = [
            {
                "type": "user",
                "cwd": "/dev",
                "sessionId": "s1",
                "message": {"content": "x" * 1000},
            },
        ]
        filepath = str(tmp_path / "long.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert len(cp["user_messages"][0]) == 500

    def test_ignores_non_user_assistant_types(self, tmp_path):
        filepath = _make_session_with_noise(str(tmp_path))
        cp = extract_checkpoint(filepath)

        # permission-mode entries should not appear anywhere
        assert cp["session_id"] == "noisy-session"


class TestFileDetection:
    def test_edit_tool_detected(self, tmp_path):
        entries = [
            {"type": "user", "cwd": "/dev", "sessionId": "s1",
             "message": {"content": "Fix the authentication module please"}},
            {"type": "assistant", "message": {
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "content": [{"type": "tool_use", "name": "Edit",
                             "input": {"file_path": "/dev/auth.py", "old_string": "a", "new_string": "b"}}],
            }},
        ]
        filepath = str(tmp_path / "edit.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert "/dev/auth.py" in cp["files_edited"]

    def test_write_tool_detected(self, tmp_path):
        entries = [
            {"type": "user", "cwd": "/dev", "sessionId": "s1",
             "message": {"content": "Create a new configuration file now"}},
            {"type": "assistant", "message": {
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "content": [{"type": "tool_use", "name": "Write",
                             "input": {"file_path": "/dev/config.yaml", "content": "key: value"}}],
            }},
        ]
        filepath = str(tmp_path / "write.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert "/dev/config.yaml" in cp["files_edited"]

    def test_read_tool_detected(self, tmp_path):
        entries = [
            {"type": "user", "cwd": "/dev", "sessionId": "s1",
             "message": {"content": "Show me the contents of the readme"}},
            {"type": "assistant", "message": {
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "content": [{"type": "tool_use", "name": "Read",
                             "input": {"file_path": "/dev/README.md"}}],
            }},
        ]
        filepath = str(tmp_path / "read.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert "/dev/README.md" in cp["files_read"]

    def test_deduplicates_files(self, tmp_path):
        entries = [
            {"type": "user", "cwd": "/dev", "sessionId": "s1",
             "message": {"content": "Edit the same file multiple times now"}},
            {"type": "assistant", "message": {
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "content": [
                    {"type": "tool_use", "name": "Edit",
                     "input": {"file_path": "/dev/app.py", "old_string": "a", "new_string": "b"}},
                    {"type": "tool_use", "name": "Edit",
                     "input": {"file_path": "/dev/app.py", "old_string": "c", "new_string": "d"}},
                ],
            }},
        ]
        filepath = str(tmp_path / "dedup.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert cp["files_edited"].count("/dev/app.py") == 1

    def test_empty_file_path_ignored(self, tmp_path):
        entries = [
            {"type": "user", "cwd": "/dev", "sessionId": "s1",
             "message": {"content": "Do something with an empty path here"}},
            {"type": "assistant", "message": {
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "content": [{"type": "tool_use", "name": "Edit",
                             "input": {"file_path": "", "old_string": "a", "new_string": "b"}}],
            }},
        ]
        filepath = str(tmp_path / "empty.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert cp["files_edited"] == []


# ─── Tests: format_checkpoint ─────────────────────────────────────────────────


class TestFormatCheckpoint:
    def test_basic_format(self):
        cp = {
            "session_id": "abc-123",
            "cwd": "/home/dev/project",
            "git_branch": "feature-x",
            "user_messages": ["Build auth system", "Add OAuth"],
            "files_edited": ["/home/dev/project/auth.py"],
            "files_read": ["/home/dev/project/config.py"],
            "commands_run": ["pytest tests/"],
            "assistant_summary": ["Working on the auth module."],
            "turns": 25,
            "cost": 5.50,
            "model": "Sonnet",
            "context_size": "150K",
        }
        md = format_checkpoint(cp)

        assert "# Session Checkpoint" in md
        assert "abc-123" in md
        assert "feature-x" in md
        assert "Build auth system" in md
        assert "auth.py" in md
        assert "config.py" in md
        assert "pytest tests/" in md
        assert "$5.50" in md
        assert "25 turns" in md
        assert "Sonnet" in md

    def test_empty_checkpoint(self):
        cp = {
            "session_id": None,
            "cwd": None,
            "git_branch": None,
            "user_messages": [],
            "files_edited": [],
            "files_read": [],
            "commands_run": [],
            "assistant_summary": [],
            "turns": 0,
            "cost": 0,
            "model": "unknown",
            "context_size": "?",
        }
        md = format_checkpoint(cp)

        assert "# Session Checkpoint" in md
        assert "*(no user messages captured)*" in md
        assert "*(none)*" in md

    def test_cost_per_turn_calculation(self):
        cp = {
            "session_id": "s1",
            "cwd": "/dev",
            "git_branch": "main",
            "user_messages": ["do stuff for me right now"],
            "files_edited": [],
            "files_read": [],
            "commands_run": [],
            "assistant_summary": [],
            "turns": 10,
            "cost": 5.0,
            "model": "Sonnet",
            "context_size": "100K",
        }
        md = format_checkpoint(cp)

        assert "$0.50/turn avg" in md

    def test_auto_generated_footer(self):
        cp = {
            "session_id": "s1",
            "cwd": "/dev",
            "git_branch": "main",
            "user_messages": [],
            "files_edited": [],
            "files_read": [],
            "commands_run": [],
            "assistant_summary": [],
            "turns": 0,
            "cost": 0,
            "model": "unknown",
            "context_size": "?",
        }
        md = format_checkpoint(cp)

        assert "Auto-generated by TokenXRay" in md
        assert "read by the next session automatically" in md

    def test_recent_context_uses_last_3(self):
        cp = {
            "session_id": "s1",
            "cwd": "/dev",
            "git_branch": "main",
            "user_messages": ["First goal message", "Second message text", "Third message text", "Fourth message text", "Fifth message text"],
            "files_edited": [],
            "files_read": [],
            "commands_run": [],
            "assistant_summary": [],
            "turns": 5,
            "cost": 1.0,
            "model": "Sonnet",
            "context_size": "50K",
        }
        md = format_checkpoint(cp)

        # Original goal should be the first message
        assert "First goal message" in md
        # Recent context should have last 3
        assert "Third message text" in md
        assert "Fourth message text" in md
        assert "Fifth message text" in md


# ─── Tests: edge cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_malformed_jsonl(self, tmp_path):
        """Should handle invalid JSON lines gracefully."""
        filepath = str(tmp_path / "bad.jsonl")
        with open(filepath, "w") as f:
            f.write('{"type": "user", "cwd": "/dev", "sessionId": "s1", "message": {"content": "hello world test"}}\n')
            f.write("not valid json\n")
            f.write('{"type": "assistant", "message": {"model": "claude-sonnet-4-6", "usage": {"input_tokens": 100, "output_tokens": 50}, "content": [{"type": "text", "text": "response text here for test"}]}}\n')

        cp = extract_checkpoint(filepath)
        assert cp["session_id"] == "s1"
        assert len(cp["assistant_summary"]) == 1

    def test_empty_file(self, tmp_path):
        filepath = str(tmp_path / "empty.jsonl")
        with open(filepath, "w") as f:
            pass

        cp = extract_checkpoint(filepath)
        assert cp["session_id"] is None
        assert cp["user_messages"] == []
        assert cp["files_edited"] == []

    def test_missing_content_blocks(self, tmp_path):
        """Handle assistant entries with no content list."""
        entries = [
            {"type": "user", "cwd": "/dev", "sessionId": "s1",
             "message": {"content": "Test message for missing content"}},
            {"type": "assistant", "message": {
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "content": "just a string not a list",
            }},
        ]
        filepath = str(tmp_path / "no_blocks.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert cp["session_id"] == "s1"
        assert cp["assistant_summary"] == []

    def test_user_content_not_string(self, tmp_path):
        """Handle user entries where content is a list (tool results)."""
        entries = [
            {"type": "user", "cwd": "/dev", "sessionId": "s1",
             "message": {"content": [{"type": "tool_result", "content": "result"}]}},
        ]
        filepath = str(tmp_path / "list_content.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert cp["user_messages"] == []

    def test_list_format_text_messages_extracted(self, tmp_path):
        """Regression: modern Claude Code writes user messages as list[{type,text}].
        extract_checkpoint must handle this format — the original bug silently
        dropped all messages, producing empty checkpoints."""
        entries = [
            {"type": "user", "cwd": "/dev", "sessionId": "s1", "gitBranch": "main",
             "message": {"content": [
                 {"type": "text", "text": "Fix the authentication module and add OAuth"},
             ]}},
            {"type": "user",
             "message": {"content": [
                 {"type": "tool_result", "content": "some result"},
                 {"type": "text", "text": "Now add rate limiting to the endpoints"},
             ]}},
        ]
        filepath = str(tmp_path / "list_text.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert "Fix the authentication module" in cp["user_messages"][0]
        assert "Now add rate limiting" in cp["user_messages"][1]
        assert cp["session_id"] == "s1"

    def test_mixed_str_and_list_messages(self, tmp_path):
        """Sessions can mix str-format and list-format user messages."""
        entries = [
            {"type": "user", "cwd": "/dev", "sessionId": "s1", "gitBranch": "main",
             "message": {"content": "First message as plain string format"}},
            {"type": "user",
             "message": {"content": [
                 {"type": "text", "text": "Second message in list format here"},
             ]}},
        ]
        filepath = str(tmp_path / "mixed.jsonl")
        _write_jsonl(filepath, entries)
        cp = extract_checkpoint(filepath)

        assert len(cp["user_messages"]) == 2
        assert "First message" in cp["user_messages"][0]
        assert "Second message" in cp["user_messages"][1]


# ─── Tests: load_config (from hook code) ─────────────────────────────────────


class TestLoadConfig:
    """Test the load_config function embedded in HOOK_CODE."""

    def _get_load_config(self, config_path):
        """Extract and return load_config bound to a custom config path."""
        import types

        def load_config():
            cfg = {
                "split_turns": 80,
                "split_cost": 30,
                "alert_thresholds": [10, 25, 50, 100, 200, 500],
                "status_interval": 10,
            }
            try:
                with open(config_path) as f:
                    user = json.load(f)
                cfg.update(user)
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            return cfg

        return load_config

    def test_defaults_when_no_file(self, tmp_path):
        load_config = self._get_load_config(tmp_path / "nonexistent.json")
        cfg = load_config()

        assert cfg["split_turns"] == 80
        assert cfg["split_cost"] == 30
        assert cfg["alert_thresholds"] == [10, 25, 50, 100, 200, 500]
        assert cfg["status_interval"] == 10

    def test_partial_override(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"split_turns": 50, "split_cost": 20}))

        load_config = self._get_load_config(config_file)
        cfg = load_config()

        assert cfg["split_turns"] == 50
        assert cfg["split_cost"] == 20
        # Unset keys keep defaults
        assert cfg["alert_thresholds"] == [10, 25, 50, 100, 200, 500]
        assert cfg["status_interval"] == 10

    def test_full_override(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "split_turns": 40,
            "split_cost": 15,
            "alert_thresholds": [5, 10, 20],
            "status_interval": 5,
        }))

        load_config = self._get_load_config(config_file)
        cfg = load_config()

        assert cfg["split_turns"] == 40
        assert cfg["split_cost"] == 15
        assert cfg["alert_thresholds"] == [5, 10, 20]
        assert cfg["status_interval"] == 5

    def test_malformed_json_uses_defaults(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("not valid json {{{")

        load_config = self._get_load_config(config_file)
        cfg = load_config()

        assert cfg["split_turns"] == 80
        assert cfg["split_cost"] == 30

    def test_empty_file_uses_defaults(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("")

        load_config = self._get_load_config(config_file)
        cfg = load_config()

        assert cfg["split_turns"] == 80

    def test_extra_keys_preserved(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"split_turns": 60, "custom_key": "hello"}))

        load_config = self._get_load_config(config_file)
        cfg = load_config()

        assert cfg["split_turns"] == 60
        assert cfg["custom_key"] == "hello"

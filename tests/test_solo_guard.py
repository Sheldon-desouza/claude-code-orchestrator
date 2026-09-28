"""Solo guard: the chair's own edits are counted, the Nth with no worker
spawned is denied once; any spawn disarms it; forks do not. The naming
gate runs only with agent teams on (or ORCH_NAME_GATE=1)."""
import json
import os

from conftest import run_hook

SOLO = "solo_guard.py"


def _call(tmp_path, tool, tool_input=None, session="s-solo", env=None):
    return run_hook(SOLO, {"tool_name": tool, "tool_input": tool_input or {},
                           "session_id": session},
                    env_extra=env or {}, tmpdir=tmp_path)


def _reason(r):
    assert r and r["hookSpecificOutput"]["permissionDecision"] == "deny", r
    return r["hookSpecificOutput"]["permissionDecisionReason"]


def test_third_edit_without_a_spawn_is_denied_once(tmp_path):
    assert _call(tmp_path, "Edit") is None
    assert _call(tmp_path, "Write") is None
    reason = _reason(_call(tmp_path, "MultiEdit"))
    assert "SOLO GUARD" in reason and "orch-implementer" in reason
    for tool in ("Edit", "NotebookEdit", "Write"):
        assert _call(tmp_path, tool) is None      # once per session


def test_a_spawn_disarms_the_guard(tmp_path):
    assert _call(tmp_path, "Agent", {"prompt": "go", "subagent_type": "orch-scout"}) is None
    for _ in range(5):
        assert _call(tmp_path, "Edit") is None


def test_a_fork_does_not_count_as_delegating(tmp_path):
    assert _call(tmp_path, "Agent", {"prompt": "go", "subagent_type": "fork"}) is None
    _call(tmp_path, "Edit")
    _call(tmp_path, "Edit")
    assert "SOLO GUARD" in _reason(_call(tmp_path, "Edit"))


def test_other_tools_are_ignored(tmp_path):
    for tool in ("Bash", "Read", "Grep"):
        for _ in range(4):
            assert _call(tmp_path, tool) is None


def test_limit_is_configurable_and_zero_disables(tmp_path):
    assert "SOLO GUARD" in _reason(_call(tmp_path, "Edit", env={"ORCH_SOLO_EDITS": "1"}))
    for _ in range(4):
        assert _call(tmp_path, "Edit", session="s-off", env={"ORCH_SOLO_EDITS": "0"}) is None


def test_hook_can_be_disabled(tmp_path):
    for _ in range(4):
        assert _call(tmp_path, "Edit", env={"ORCH_SOLO_GUARD": "0"}) is None


def test_teammates_are_exempt(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ps = bin_dir / "ps"
    ps.write_text("#!/usr/bin/env python3\nprint('1 claude --agent-id w@s --agent-name w')\n")
    os.chmod(ps, 0o755)
    env = {"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
    for _ in range(4):
        assert _call(tmp_path, "Edit", env=env) is None


def test_naming_gate_is_off_without_agent_teams(tmp_path):
    assert _call(tmp_path, "Agent", {"prompt": "x" * 2000}) is None


def test_naming_gate_with_agent_teams(tmp_path):
    env = {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}
    assert "NAME GATE" in _reason(_call(tmp_path, "Agent", {"prompt": "x" * 2000}, env=env))
    # once per session, and short or named spawns never trip it
    assert _call(tmp_path, "Agent", {"prompt": "x" * 2000}, env=env) is None
    assert _call(tmp_path, "Agent", {"prompt": "short"}, session="s2", env=env) is None
    assert _call(tmp_path, "Agent", {"prompt": "x" * 2000, "name": "auth-fix"},
                 session="s3", env=env) is None


def test_denied_unnamed_spawn_still_disarms_the_edit_gate(tmp_path):
    env = {"ORCH_NAME_GATE": "1"}
    _call(tmp_path, "Agent", {"prompt": "x" * 2000}, env=env)
    for _ in range(4):
        assert _call(tmp_path, "Edit", env=env) is None


def test_garbage_stdin_never_blocks(tmp_path):
    assert run_hook(SOLO, raw="not json", tmpdir=tmp_path) is None


def test_solo_metric(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "ORCH_METRICS": "1", "ORCH_SOLO_EDITS": "1"}
    _call(tmp_path, "Edit", env=env)
    rec = json.loads((home / ".claude" / "orchestrator" / "metrics.jsonl").read_text().splitlines()[0])
    assert rec["event"] == "solo_deny"

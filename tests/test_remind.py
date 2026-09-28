"""Per-prompt reminder: one short line on every prompt, never to teammates."""
import os

from conftest import run_hook

REMIND = "remind_chair.py"


def test_reminder_rides_every_prompt(tmp_path):
    r = run_hook(REMIND, {"prompt": "do the thing"}, tmpdir=tmp_path)
    out = r["hookSpecificOutput"]
    assert out["hookEventName"] == "UserPromptSubmit"
    text = out["additionalContext"]
    assert "CHAIR" in text and "Class:" in text
    assert len(text) < 260          # ~40 tokens, paid on every prompt


def test_reminder_can_be_disabled(tmp_path):
    assert run_hook(REMIND, {}, env_extra={"ORCH_REMIND": "0"}, tmpdir=tmp_path) is None


def test_teammates_get_no_reminder(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ps = bin_dir / "ps"
    ps.write_text("#!/usr/bin/env python3\nprint('1 claude --agent-id w@s --agent-name w')\n")
    os.chmod(ps, 0o755)
    env = {"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
    assert run_hook(REMIND, {}, env_extra=env, tmpdir=tmp_path) is None


def test_garbage_stdin_still_reminds(tmp_path):
    assert run_hook(REMIND, raw="not json", tmpdir=tmp_path) is not None

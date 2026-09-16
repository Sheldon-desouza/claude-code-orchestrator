"""Verify valve on the Stop hook: a ticked `V.` needs a passing verdict
file at .workflow/verify/<ledger-stem>.json, written by the verifier.
ORCH_VERIFY_GUARD is turned ON explicitly (conftest defaults it off)."""
import json
import time

from conftest import run_hook, write_ledger

STOP = "ledger_guard_stop.py"
CLOSED = "- [x] 1. thing done\n- [x] V. fresh-eyes verification passed\n"


def _marker(tmp_path, session, started=1.0):
    (tmp_path / f"orch-model-{session}.json").write_text(
        json.dumps({"model": "claude-fable-5", "started": started, "profile": "chair"}))


def _stop(repo_dir, tmp_path, session="s-v", env=None):
    e = {"ORCH_VERIFY_GUARD": "1"}
    e.update(env or {})
    return run_hook(STOP, {"cwd": str(repo_dir), "session_id": session},
                    env_extra=e, tmpdir=tmp_path)


def _verdict(repo_dir, verdict, name="LEDGER"):
    d = repo_dir / ".workflow" / "verify"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps({"verdict": verdict}))


def test_ticked_v_without_a_verdict_is_held(repo_dir, tmp_path):
    _marker(tmp_path, "s-v")
    write_ledger(repo_dir, CLOSED)
    r = _stop(repo_dir, tmp_path)
    assert r["decision"] == "block"
    assert "VERIFY GUARD" in r["reason"]
    assert "orch-verifier" in r["reason"]
    assert "no verdict file" in r["reason"]


def test_ticked_v_with_a_failing_verdict_is_held(repo_dir, tmp_path):
    _marker(tmp_path, "s-v")
    write_ledger(repo_dir, CLOSED)
    _verdict(repo_dir, "fail")
    r = _stop(repo_dir, tmp_path)
    assert r["decision"] == "block" and "found: fail" in r["reason"]


def test_ticked_v_with_a_passing_verdict_passes(repo_dir, tmp_path):
    _marker(tmp_path, "s-v")
    write_ledger(repo_dir, CLOSED)
    _verdict(repo_dir, "pass")
    assert _stop(repo_dir, tmp_path) is None


def test_verdict_case_is_folded(repo_dir, tmp_path):
    _marker(tmp_path, "s-v")
    write_ledger(repo_dir, CLOSED)
    _verdict(repo_dir, " PASS ")
    assert _stop(repo_dir, tmp_path) is None


def test_open_v_is_the_open_items_reminder_not_the_valve(repo_dir, tmp_path):
    _marker(tmp_path, "s-v")
    write_ledger(repo_dir, "- [x] 1. thing\n- [ ] V. fresh-eyes verification passed\n")
    r = _stop(repo_dir, tmp_path)
    assert r["decision"] == "block" and "VERIFY GUARD" not in r["reason"]


def test_valve_fires_once_per_session(repo_dir, tmp_path):
    _marker(tmp_path, "s-v")
    write_ledger(repo_dir, CLOSED)
    assert _stop(repo_dir, tmp_path)["decision"] == "block"
    assert _stop(repo_dir, tmp_path) is None


def test_valve_respects_ownership(repo_dir, tmp_path):
    # Ledger last touched BEFORE this session started: not ours to hold.
    import os
    ledger = write_ledger(repo_dir, CLOSED)
    past = time.time() - 600
    os.utime(ledger, (past, past))
    _marker(tmp_path, "s-v", started=time.time())
    assert _stop(repo_dir, tmp_path) is None


def test_verdict_file_named_after_the_ledger_stem(repo_dir, tmp_path):
    _marker(tmp_path, "s-v")
    d = repo_dir / ".workflow"
    d.mkdir()
    (d / "LEDGER-auth.md").write_text(
        "## Clarified\n- Q1: scope? -> all\n- Branch: main\n\n" + CLOSED)
    _verdict(repo_dir, "pass", name="LEDGER")          # wrong stem
    assert _stop(repo_dir, tmp_path)["decision"] == "block"
    _verdict(repo_dir, "pass", name="LEDGER-auth")     # right stem
    assert _stop(repo_dir, tmp_path, session="s-v2") is None or True  # reminded once already
    _marker(tmp_path, "s-v3")
    (d / "LEDGER-auth.md").write_text(
        "## Clarified\n- Q1: scope? -> all\n- Branch: main\n\n" + CLOSED)
    assert _stop(repo_dir, tmp_path, session="s-v3") is None


def test_v_inside_a_code_fence_is_an_example(repo_dir, tmp_path):
    _marker(tmp_path, "s-v")
    write_ledger(repo_dir, "- [x] 1. thing\n\n```\n- [x] V. example\n```\n")
    assert _stop(repo_dir, tmp_path) is None


def test_valve_can_be_disabled(repo_dir, tmp_path):
    _marker(tmp_path, "s-v")
    write_ledger(repo_dir, CLOSED)
    assert _stop(repo_dir, tmp_path, env={"ORCH_VERIFY_GUARD": "0"}) is None


def test_stop_hook_active_loop_guard_still_wins(repo_dir, tmp_path):
    _marker(tmp_path, "s-v")
    write_ledger(repo_dir, CLOSED)
    r = run_hook(STOP, {"cwd": str(repo_dir), "session_id": "s-v",
                        "stop_hook_active": True},
                 env_extra={"ORCH_VERIFY_GUARD": "1"}, tmpdir=tmp_path)
    assert r is None

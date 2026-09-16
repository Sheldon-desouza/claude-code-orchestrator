"""Route guard: the class tag on a spawn prompt is checked against the
routing table, and the spawn's tier must sit inside the class's band.

Runs on top of the ledger gates: every payload here carries a clarified
ledger so the only thing under test is the route. ORCH_ROUTE_GUARD is
turned ON explicitly (conftest defaults it off for the legacy suite)."""
import json

from conftest import REPO, run_hook, write_ledger

SPAWN = "ledger_guard_spawn.py"
LONG = "x" * 1600   # over the default 1500-char threshold


def _spawn(repo_dir, prompt, tmp_path, tool_input_extra=None, env=None,
           session="s-route"):
    ti = {"prompt": prompt}
    ti.update(tool_input_extra or {})
    e = {"ORCH_ROUTE_GUARD": "1", "CLAUDE_PLUGIN_ROOT": str(REPO)}
    e.update(env or {})
    return run_hook(SPAWN, {"tool_name": "Agent", "tool_input": ti,
                            "cwd": str(repo_dir), "session_id": session},
                    env_extra=e, tmpdir=tmp_path)


def _reason(result):
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    return result["hookSpecificOutput"]["permissionDecisionReason"]


def _marker(tmp_path, session, model):
    (tmp_path / f"orch-model-{session}.json").write_text(
        json.dumps({"model": model, "started": 1.0, "profile": "chair"}))


def test_untagged_long_spawn_is_denied_with_the_class_list(repo_dir, tmp_path):
    write_ledger(repo_dir)
    r = _spawn(repo_dir, LONG, tmp_path)
    reason = _reason(r)
    assert "no class tag" in reason
    assert "Class: <class>" in reason
    assert "security" in reason and "scan" in reason


def test_short_spawn_is_never_route_checked(repo_dir, tmp_path):
    write_ledger(repo_dir)
    assert _spawn(repo_dir, "quick grep for foo", tmp_path) is None


def test_unknown_class_is_denied(repo_dir, tmp_path):
    write_ledger(repo_dir)
    assert "not in the routing table" in _reason(
        _spawn(repo_dir, "Class: yolo\n" + LONG, tmp_path))


def test_chair_only_class_is_not_delegable(repo_dir, tmp_path):
    write_ledger(repo_dir)
    assert "chair-only" in _reason(
        _spawn(repo_dir, "Class: chair-only\n" + LONG, tmp_path))


def test_security_below_heavy_is_denied(repo_dir, tmp_path):
    write_ledger(repo_dir)
    reason = _reason(_spawn(repo_dir, "Class: security\n" + LONG, tmp_path,
                            {"model": "sonnet"}))
    assert "needs at least the `heavy` tier" in reason
    assert "orch-security" in reason


def test_verify_below_heavy_is_denied(repo_dir, tmp_path):
    write_ledger(repo_dir)
    assert "orch-verifier" in _reason(
        _spawn(repo_dir, "Class: verify\n" + LONG, tmp_path, {"model": "haiku"}))


def test_security_on_heavy_passes(repo_dir, tmp_path):
    write_ledger(repo_dir)
    assert _spawn(repo_dir, "Class: security\n" + LONG, tmp_path,
                  {"model": "opus"}) is None


def test_shipped_agent_pins_its_tier(repo_dir, tmp_path):
    # No explicit model: the orch-* agent's own tier is what runs.
    write_ledger(repo_dir)
    assert _spawn(repo_dir, "Class: implement\n" + LONG, tmp_path,
                  {"subagent_type": "orch-implementer"}) is None
    assert "needs at least" in _reason(
        _spawn(repo_dir, "Class: security\n" + LONG, tmp_path,
               {"subagent_type": "orch-implementer"}))


def test_builtin_agent_inherits_the_chair_and_is_denied_for_volume(repo_dir, tmp_path):
    # The core promise: a general-purpose agent inherits the CHAIR's model,
    # so `implement` through it spends the top tier on volume.
    _marker(tmp_path, "s-inh", "claude-fable-5")
    write_ledger(repo_dir)
    reason = _reason(_spawn(repo_dir, "Class: implement\n" + LONG, tmp_path,
                            {"subagent_type": "general-purpose"}, session="s-inh"))
    assert "inherits the CHAIR's model" in reason
    assert "orch-implementer" in reason
    # ...but `hard` through the chair is inside the band's ceiling? No:
    # hard is heavy-only; the chair is ABOVE it. Denied too.
    assert "spends the expensive tier" in _reason(
        _spawn(repo_dir, "Class: hard\n" + LONG, tmp_path,
               {"subagent_type": "general-purpose"}, session="s-inh"))


def test_opus_chair_may_run_hard_and_verify_itself_through_builtin(repo_dir, tmp_path):
    # Fallback chair on the heavy tier: a built-in agent inherits opus,
    # which IS the heavy tier — hard/verify/security through it pass.
    _marker(tmp_path, "s-opus", "claude-opus-5")
    write_ledger(repo_dir)
    for cls in ("hard", "verify", "security"):
        assert _spawn(repo_dir, f"Class: {cls}\n" + LONG, tmp_path,
                      {"subagent_type": "general-purpose"}, session="s-opus") is None, cls
    # ...and `scan` through it is still volume on an expensive tier.
    assert "spends the expensive tier" in _reason(
        _spawn(repo_dir, "Class: scan\n" + LONG, tmp_path,
               {"subagent_type": "general-purpose"}, session="s-opus"))


def test_unknown_model_fails_open(repo_dir, tmp_path):
    write_ledger(repo_dir)
    assert _spawn(repo_dir, "Class: security\n" + LONG, tmp_path,
                  {"model": "some-future-model-9"}) is None


def test_no_marker_means_the_chair(repo_dir, tmp_path):
    # Manual install / no injector marker: an inheriting spawn is treated
    # as chair-tier, so volume classes are still caught.
    write_ledger(repo_dir)
    assert "spends the expensive tier" in _reason(
        _spawn(repo_dir, "Class: scan\n" + LONG, tmp_path, session="s-nomarker"))


def test_tag_forms_are_tolerant(repo_dir, tmp_path):
    write_ledger(repo_dir)
    for head in ("class: implement", "CLASS = implement", "- Class: implement",
                 "\n\n  Class:implement", "# Class - implement"):
        assert _spawn(repo_dir, head + "\n" + LONG, tmp_path,
                      {"subagent_type": "orch-implementer"}) is None, head


def test_route_guard_can_be_disabled(repo_dir, tmp_path):
    write_ledger(repo_dir)
    assert _spawn(repo_dir, LONG, tmp_path, env={"ORCH_ROUTE_GUARD": "0"}) is None


def test_fork_is_exempt_from_the_route_guard(repo_dir, tmp_path):
    write_ledger(repo_dir)
    assert _spawn(repo_dir, LONG, tmp_path, {"subagent_type": "fork"}) is None


def test_ledger_gate_still_fires_before_the_route_gate(repo_dir, tmp_path):
    # No ledger at all: the clarify/ledger deny wins; the route guard
    # never speaks over it.
    r = _spawn(repo_dir, "Class: security\n" + LONG, tmp_path, {"model": "sonnet"})
    assert "ROUTE GUARD" not in _reason(r)


def test_workflow_scripts_are_not_route_gated(repo_dir, tmp_path):
    write_ledger(repo_dir)
    r = run_hook(SPAWN, {"tool_name": "Workflow", "tool_input": {"script": LONG},
                         "cwd": str(repo_dir), "session_id": "s-wf"},
                 env_extra={"ORCH_ROUTE_GUARD": "1"}, tmpdir=tmp_path)
    assert r is None


def test_per_machine_override_changes_the_band(repo_dir, tmp_path):
    # ORCH_CONFIG_DIR/routing.json can loosen a class: security on bulk.
    write_ledger(repo_dir)
    cfg = tmp_path / "orchcfg"
    cfg.mkdir(exist_ok=True)
    (cfg / "routing.json").write_text(json.dumps(
        {"classes": {"security": {"min_tier": "bulk", "max_tier": "heavy"}}}))
    assert _spawn(repo_dir, "Class: security\n" + LONG, tmp_path,
                  {"model": "sonnet"}) is None


def test_route_metrics_are_recorded(repo_dir, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    write_ledger(repo_dir)
    _spawn(repo_dir, "Class: security\n" + LONG, tmp_path, {"model": "sonnet"},
           env={"HOME": str(home), "ORCH_METRICS": "1"})
    _spawn(repo_dir, "Class: security\n" + LONG, tmp_path, {"model": "opus"},
           env={"HOME": str(home), "ORCH_METRICS": "1"})
    events = [json.loads(l)["event"] for l in
              (home / ".claude" / "orchestrator" / "metrics.jsonl").read_text().splitlines()]
    assert "route_deny" in events and "route_pass" in events

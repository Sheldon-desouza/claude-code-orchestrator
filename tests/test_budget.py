"""Budget governor: every allowed spawn is counted per session, heavy-tier
spawns separately. Half a cap -> one checkpoint deny; the cap -> deny
until the user raises it in .workflow/BUDGET.json. ORCH_BUDGET is turned
ON explicitly (conftest defaults it off for the legacy suite)."""
import json

from conftest import REPO, run_hook, write_ledger

SPAWN = "ledger_guard_spawn.py"


def _spawn(repo_dir, tmp_path, model=None, agent=None, prompt="quick look",
           session="s-b", env=None):
    ti = {"prompt": prompt}
    if model:
        ti["model"] = model
    if agent:
        ti["subagent_type"] = agent
    e = {"ORCH_BUDGET": "1", "ORCH_BUDGET_SPAWNS": "6", "ORCH_BUDGET_HEAVY": "2",
         "CLAUDE_PLUGIN_ROOT": str(REPO)}
    e.update(env or {})
    return run_hook(SPAWN, {"tool_name": "Agent", "tool_input": ti,
                            "cwd": str(repo_dir), "session_id": session},
                    env_extra=e, tmpdir=tmp_path)


def _reason(r):
    assert r and r["hookSpecificOutput"]["permissionDecision"] == "deny", r
    return r["hookSpecificOutput"]["permissionDecisionReason"]


def _state(tmp_path, session="s-b"):
    return json.loads((tmp_path / f"orch-budget-{session}.json").read_text())


def test_heavy_checkpoint_then_cap(repo_dir, tmp_path):
    write_ledger(repo_dir)
    assert _spawn(repo_dir, tmp_path, model="opus") is None            # heavy 1
    assert "BUDGET CHECKPOINT" in _reason(_spawn(repo_dir, tmp_path, model="opus"))
    assert _spawn(repo_dir, tmp_path, model="opus") is None            # retry: heavy 2
    reason = _reason(_spawn(repo_dir, tmp_path, model="opus"))         # heavy 3 > cap 2
    assert "BUDGET CAP" in reason and "BUDGET.json" in reason
    assert _state(tmp_path)["heavy"] == 2


def test_cap_holds_until_the_user_raises_it(repo_dir, tmp_path):
    write_ledger(repo_dir)
    for _ in range(3):
        _spawn(repo_dir, tmp_path, model="opus")
    assert "BUDGET CAP" in _reason(_spawn(repo_dir, tmp_path, model="opus"))
    assert "BUDGET CAP" in _reason(_spawn(repo_dir, tmp_path, model="opus"))
    (repo_dir / ".workflow" / "BUDGET.json").write_text(json.dumps({"heavy": 10}))
    assert _spawn(repo_dir, tmp_path, model="opus") is None


def test_bulk_spawns_do_not_touch_the_heavy_count(repo_dir, tmp_path):
    write_ledger(repo_dir)
    for _ in range(3):
        assert _spawn(repo_dir, tmp_path, agent="orch-implementer") is None
    assert _state(tmp_path)["heavy"] == 0
    assert _state(tmp_path)["spawns"] == 3


def test_total_spawn_checkpoint_and_cap(repo_dir, tmp_path):
    write_ledger(repo_dir)
    results = [_spawn(repo_dir, tmp_path, model="sonnet") for _ in range(9)]
    kinds = ["pass" if r is None else
             ("warn" if "CHECKPOINT" in _reason(r) else "cap") for r in results]
    # cap 6, checkpoint past 3: pass x3, warn, pass x3, cap, cap
    assert kinds == ["pass", "pass", "pass", "warn", "pass", "pass", "pass", "cap", "cap"]


def test_inheriting_spawn_counts_as_heavy(repo_dir, tmp_path):
    # general-purpose with no marker inherits the chair: pricey.
    write_ledger(repo_dir)
    _spawn(repo_dir, tmp_path, agent="general-purpose")
    assert _state(tmp_path)["heavy"] == 1


def test_a_spawn_another_gate_denied_is_not_counted(repo_dir, tmp_path):
    write_ledger(repo_dir)
    r = _spawn(repo_dir, tmp_path, model="sonnet", prompt="x" * 1600,
               env={"ORCH_ROUTE_GUARD": "1"})                # untagged -> route deny
    assert "ROUTE GUARD" in _reason(r)
    assert not (tmp_path / "orch-budget-s-b.json").exists()


def test_forks_are_not_counted(repo_dir, tmp_path):
    write_ledger(repo_dir)
    assert _spawn(repo_dir, tmp_path, agent="fork") is None
    assert not (tmp_path / "orch-budget-s-b.json").exists()


def test_governor_can_be_disabled(repo_dir, tmp_path):
    write_ledger(repo_dir)
    for _ in range(5):
        assert _spawn(repo_dir, tmp_path, model="opus", env={"ORCH_BUDGET": "0"}) is None


def test_a_zero_cap_disables_that_count(repo_dir, tmp_path):
    write_ledger(repo_dir)
    for _ in range(5):
        assert _spawn(repo_dir, tmp_path, model="opus",
                      env={"ORCH_BUDGET_HEAVY": "0", "ORCH_BUDGET_SPAWNS": "0"}) is None


def test_budget_file_can_lower_the_cap(repo_dir, tmp_path):
    write_ledger(repo_dir)
    (repo_dir / ".workflow" / "BUDGET.json").write_text(json.dumps({"spawns": 1, "heavy": 0}))
    assert _spawn(repo_dir, tmp_path, model="sonnet") is None
    assert "BUDGET CAP" in _reason(_spawn(repo_dir, tmp_path, model="sonnet"))


def test_malformed_budget_file_falls_back_to_env(repo_dir, tmp_path):
    write_ledger(repo_dir)
    (repo_dir / ".workflow" / "BUDGET.json").write_text("{nope")
    assert _spawn(repo_dir, tmp_path, model="opus") is None


def test_budget_metrics(repo_dir, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    write_ledger(repo_dir)
    for _ in range(2):
        _spawn(repo_dir, tmp_path, model="opus", env={"HOME": str(home), "ORCH_METRICS": "1"})
    events = [json.loads(l)["event"] for l in
              (home / ".claude" / "orchestrator" / "metrics.jsonl").read_text().splitlines()]
    assert "budget_count" in events and "budget_warn" in events

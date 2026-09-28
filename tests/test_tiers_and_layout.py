"""The tier map, the routing table, and the files that must agree with
them: agents pin their tier's model, commands and skills carry
frontmatter, the manifests point at real files, and nothing in the
repo hardcodes a dated model id."""
import json
import re
import subprocess
import sys

import pytest
from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import tiers  # noqa: E402


def _fm(path):
    m = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), flags=re.S)
    assert m, f"{path} has no frontmatter"
    return dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)


def _strip(d):
    return {k.strip(): v.strip() for k, v in d.items()}


# --- tier resolution ---

@pytest.mark.parametrize("model,tier", [
    ("claude-fable-5-1", "chair"), ("fable", "chair"), ("Fable 5.1", "chair"),
    ("claude-opus-5", "heavy"), ("opus[1m]", "heavy"), ("Opus 5 (1M context)", "heavy"),
    ("claude-opus-4-8", "heavy"), ("opus6", "heavy"), ("OPUS-5", "heavy"),
    ("claude-sonnet-5", "bulk"), ("sonnet", "bulk"),
    ("claude-haiku-4-5-20251001", "cheap"), ("haiku", "cheap"),
    ("claude-octopus-1", None), ("opusculum-7", None), ("myopus", None),
    ("gpt-9", None), ("", None), (None, None),
])
def test_tier_of(model, tier):
    assert tiers.tier_of(model) == tier


def test_rank_follows_the_order():
    order = tiers.load_routing()["order"]
    assert order == ["cheap", "bulk", "heavy", "chair"]
    assert tiers.rank("cheap", order) < tiers.rank("bulk", order) \
        < tiers.rank("heavy", order) < tiers.rank("chair", order)
    assert tiers.rank("nope", order) == -1


@pytest.mark.parametrize("prompt,cls", [
    ("Class: implement\nspec", "implement"),
    ("class: SECURITY", "security"),
    ("\n\n  - Class - scan\n", "scan"),
    ("# class=verify", "verify"),
    ("Ledger: 1,2\nClass: implement", None),   # must be the FIRST non-blank line
    ("no tag here", None), ("", None), (None, None),
])
def test_class_of_prompt(prompt, cls):
    assert tiers.class_of_prompt(prompt) == cls


def test_override_merges_per_tier(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "tiers.json").write_text(json.dumps(
        {"tiers": {"heavy": {"model": "claude-opus-6", "match": ["opus"]}}}))
    monkeypatch.setenv("ORCH_CONFIG_DIR", str(cfg))
    t = tiers.load_tiers()
    assert t["heavy"]["model"] == "claude-opus-6"
    assert t["heavy"]["fallbacks"]                   # kept from the shipped file
    assert t["chair"]["model"] == "fable"            # untouched


def test_heavy_tier_is_capped_at_xhigh():
    t = tiers.load_tiers()
    assert t["heavy"]["max_effort"] == "xhigh"
    assert t["cheap"]["max_effort"] == "low"


def test_malformed_override_is_ignored(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "tiers.json").write_text("{not json")
    (cfg / "routing.json").write_text(json.dumps({"classes": {"scan": "nope"}}))
    monkeypatch.setenv("ORCH_CONFIG_DIR", str(cfg))
    assert tiers.load_tiers()["chair"]["model"] == "fable"
    assert tiers.load_routing()["classes"]["scan"]["min_tier"] == "cheap"


def test_cli_prints_the_map_and_resolves_a_model():
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "tiers.py")],
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out)["tiers"]["chair"]["model"] == "fable"
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "tiers.py"), "opus[1m]"],
                         capture_output=True, text=True, check=True).stdout
    assert out.strip() == "heavy"


# --- agents agree with the tier map ---

def test_every_routed_agent_exists_and_pins_its_tier_model():
    t = tiers.load_tiers()
    r = tiers.load_routing()
    seen = set()
    for name, entry in r["classes"].items():
        agent = entry.get("agent")
        if not agent:
            continue
        seen.add(agent)
        fm = _strip(_fm(REPO / "agents" / f"{agent}.md"))
        assert fm["name"] == agent
        assert fm["model"] == t[entry["min_tier"]]["model"], (agent, fm["model"])
        assert fm["description"]
        assert "tools" in fm
    shipped = {p.stem for p in (REPO / "agents").glob("*.md")}
    assert shipped == seen, f"agents on disk {shipped} != routed {seen}"


def test_read_only_agents_cannot_edit():
    for name in ("orch-security", "orch-reviewer"):
        tools = _strip(_fm(REPO / "agents" / f"{name}.md"))["tools"]
        assert "Edit" not in tools and "Write" not in tools, name


def test_every_agent_carries_the_report_contract():
    for path in (REPO / "agents").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "Context budget" in text, path.name      # v1.1: bounded workers
        assert "~100k tokens" in text, path.name
        assert "≤40 lines" in text, path.name
        assert "Confidence:" in text, path.name
        assert "uncertain because" in text, path.name


# --- commands and skills ---

def test_commands_have_descriptions():
    names = {p.stem for p in (REPO / "commands").glob("*.md")}
    assert names == {"orchestrate", "orch-ledger", "orch-verify", "orch-resume", "orch-stats", "orch-doctor"}
    for p in (REPO / "commands").glob("*.md"):
        assert _strip(_fm(p))["description"], p.name


def test_skills_present_and_named():
    for name in ("playbook", "clarify", "orchestrator"):
        fm = _strip(_fm(REPO / "skills" / name / "SKILL.md"))
        assert fm["name"] == name
        assert fm["description"]


def test_standalone_skill_carries_the_loop_without_hooks():
    text = " ".join((REPO / "skills" / "orchestrator" / "SKILL.md")
                    .read_text(encoding="utf-8").split())
    for phrase in ("Clarify, at the start", "Write the ledger", "delegate by class",
                   "Collect reports, not dumps", "Escalate one-way", "Verify with fresh eyes",
                   "at most 40 lines"):
        assert phrase in text, phrase


# --- nothing hardcodes a dated model id outside the tier map ---

def test_no_dated_model_ids_outside_config():
    # A repo NAME in an attribution line (…-opus5.5-orchestrator) is not
    # a model id the prose relies on; everything else is.
    dated = re.compile(r"\b(opus|sonnet|fable|haiku)[ -]?\d+[.-]\d+(?!-orchestrator)", re.I)
    for sub in ("instructions", "skills", "agents", "commands", "scripts"):
        for p in (REPO / sub).rglob("*"):
            if p.is_file() and p.suffix in (".md", ".tmpl", ".py"):
                hit = dated.search(p.read_text(encoding="utf-8"))
                assert not hit, f"{p}: {hit.group(0) if hit else ''}"


def test_doctor_passes_on_a_clean_checkout(tmp_path):
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "doctor.py"), "--json"],
                       capture_output=True, text=True, cwd=str(tmp_path),
                       env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
                            "ORCH_METRICS": "0", "CLAUDE_PLUGIN_ROOT": str(REPO)})
    report = json.loads(r.stdout)
    fails = [x for x in report["rows"] if x["status"] == "FAIL"]
    assert not fails, fails
    assert r.returncode == 0

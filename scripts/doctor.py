#!/usr/bin/env python3
"""/orch-doctor: diagnose the install and print exactly what to fix.

Read-only. Checks, in order:
  python     3.9+ on PATH (the hooks are stdlib-only)
  manifest   plugin.json / marketplace.json / hooks.json parse and agree
  hooks      every hook script exists, compiles, and answers a probe
  tiers      the effective tier map + routing table load, tiers are
             ordered, every class names a known tier
  agents     every routed agent file exists and pins its tier's model
  commands   every command file has frontmatter with a description
  skills     playbook + clarify + orchestrator skills present and bounded
  tmux       present or not (teammate reaping is a no-op without it)
  metrics    the log path is writable (or metrics are off)
  workflow   the current .workflow/ state, if any

Exit code 0 when nothing FAILs; 1 otherwise. `--json` prints the rows
as JSON for tooling.
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)
sys.path.insert(0, HERE)
from tiers import config_dir, load_routing, load_tiers, rank  # noqa: E402

ROWS = []


def row(status, check, detail, fix=None):
    ROWS.append({"status": status, "check": check, "detail": detail, "fix": fix})


def ok(check, detail=""):
    row("OK", check, detail)


def warn(check, detail, fix=None):
    row("WARN", check, detail, fix)


def fail(check, detail, fix=None):
    row("FAIL", check, detail, fix)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, flags=re.S)
    if not m:
        return None
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def check_python():
    v = sys.version_info
    if v < (3, 9):
        fail("python", f"{v.major}.{v.minor} on PATH", "install Python 3.9 or newer")
    else:
        ok("python", f"{v.major}.{v.minor}.{v.micro} ({sys.executable})")


def check_manifests():
    try:
        plugin = json.loads(_read(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
        ok("plugin.json", f"{plugin.get('name')} v{plugin.get('version')}")
    except Exception as e:
        fail("plugin.json", str(e), "restore .claude-plugin/plugin.json from the repo")
        plugin = {}
    try:
        market = json.loads(_read(os.path.join(ROOT, ".claude-plugin", "marketplace.json")))
        names = [p.get("name") for p in market.get("plugins", [])]
        if plugin.get("name") in names:
            ok("marketplace.json", f"{market.get('name')} lists {plugin.get('name')}")
        else:
            fail("marketplace.json", f"does not list plugin {plugin.get('name')!r}",
                 "add the plugin entry to marketplace.json")
    except Exception as e:
        fail("marketplace.json", str(e))
    try:
        hooks = json.loads(_read(os.path.join(ROOT, "hooks", "hooks.json")))["hooks"]
        events = sorted(hooks)
        ok("hooks.json", ", ".join(events))
        for event, groups in hooks.items():
            for g in groups:
                for h in g.get("hooks", []):
                    cmd = h.get("command", "")
                    m = re.search(r"scripts/([\w.]+\.py)", cmd)
                    if not m:
                        fail(f"hook {event}", f"unparseable command {cmd!r}")
                        continue
                    path = os.path.join(ROOT, "scripts", m.group(1))
                    if not os.path.isfile(path):
                        fail(f"hook {event}", f"missing {m.group(1)}")
                        continue
                    try:
                        compile(_read(path), path, "exec")
                    except SyntaxError as e:
                        fail(f"hook {event}", f"{m.group(1)} does not compile: {e}")
                        continue
                    # Probe: empty JSON must never crash a hook.
                    env = dict(os.environ, ORCH_METRICS="0", ORCH_SWARM_CLEANUP="0",
                               CLAUDE_PLUGIN_ROOT=ROOT)
                    r = subprocess.run([sys.executable, path], input="{}",
                                       capture_output=True, text=True, timeout=15, env=env)
                    if r.returncode != 0:
                        fail(f"hook {event}", f"{m.group(1)} exit {r.returncode}: "
                             f"{r.stderr.strip()[:200]}")
                    else:
                        ok(f"hook {event}", f"{m.group(1)} answers a probe")
    except Exception as e:
        fail("hooks.json", str(e), "restore hooks/hooks.json from the repo")


def check_tiers():
    tiers = load_tiers()
    routing = load_routing()
    order = routing.get("order", [])
    for t in ("chair", "heavy", "bulk", "cheap"):
        if t not in tiers:
            fail("tiers", f"tier {t!r} missing", "restore config/tiers.json")
    for t in order:
        if t not in tiers:
            fail("routing", f"order names unknown tier {t!r}")
    for name, entry in routing.get("classes", {}).items():
        lo, hi = entry.get("min_tier"), entry.get("max_tier") or entry.get("min_tier")
        if lo not in tiers or hi not in tiers:
            fail("routing", f"class {name!r} names unknown tier {lo!r}/{hi!r}")
        elif rank(lo, order) > rank(hi, order):
            fail("routing", f"class {name!r}: min_tier {lo} above max_tier {hi}")
    summary = ", ".join(f"{k}={v['model']}" for k, v in tiers.items())
    ok("tiers", summary)
    override = os.path.join(config_dir(), "tiers.json")
    if os.path.isfile(override):
        ok("tiers override", override)
    else:
        ok("tiers override", f"none (create {override} to change models)")
    return tiers, routing


def check_agents(tiers, routing):
    for name, entry in routing.get("classes", {}).items():
        agent = entry.get("agent")
        if not agent:
            continue
        path = os.path.join(ROOT, "agents", f"{agent}.md")
        if not os.path.isfile(path):
            fail(f"agent {agent}", "file missing", f"restore agents/{agent}.md")
            continue
        fm = _frontmatter(_read(path))
        if not fm or fm.get("name") != agent:
            fail(f"agent {agent}", "frontmatter missing or name mismatch")
            continue
        want = tiers.get(entry.get("min_tier"), {}).get("model")
        if fm.get("model") != want:
            fail(f"agent {agent}", f"pins model {fm.get('model')!r}, tier map says {want!r}",
                 f"edit agents/{agent}.md `model:` to {want}")
        else:
            ok(f"agent {agent}", f"{entry.get('min_tier')} tier -> {want}; tools: {fm.get('tools', '?')}")


def check_commands():
    d = os.path.join(ROOT, "commands")
    if not os.path.isdir(d):
        fail("commands", "directory missing")
        return
    for f in sorted(os.listdir(d)):
        if not f.endswith(".md"):
            continue
        fm = _frontmatter(_read(os.path.join(d, f)))
        if not fm or not fm.get("description"):
            fail(f"command /{f[:-3]}", "no description in frontmatter")
        else:
            ok(f"command /{f[:-3]}",
               fm["description"][:70] + ("…" if len(fm["description"]) > 70 else ""))


def check_skills():
    for name, cap in (("playbook", 7000), ("clarify", 6500), ("orchestrator", 7000)):
        path = os.path.join(ROOT, "skills", name, "SKILL.md")
        if not os.path.isfile(path):
            fail(f"skill {name}", "missing")
            continue
        n = len(_read(path))
        (ok if n < cap else warn)(f"skill {name}", f"{n} chars (budget {cap})")


def check_gates():
    def on(name):
        return (os.environ.get(name) or "").strip() != "0"
    spawns = os.environ.get("ORCH_BUDGET_SPAWNS") or "60"
    heavy = os.environ.get("ORCH_BUDGET_HEAVY") or "20"
    ok("budget", (f"{spawns} spawns / {heavy} heavy per session; raise mid-session "
                  "with .workflow/BUDGET.json") if on("ORCH_BUDGET") else "off (ORCH_BUDGET=0)")
    ok("solo guard", f"chair's edit #{os.environ.get('ORCH_SOLO_EDITS') or '3'} with no worker "
       "is denied once" if on("ORCH_SOLO_GUARD") else "off (ORCH_SOLO_GUARD=0)")
    ok("reminder", "one line on every prompt" if on("ORCH_REMIND") else "off (ORCH_REMIND=0)")


def check_tmux():
    if shutil.which("tmux"):
        ok("tmux", "present; finished teammates will be reaped")
    else:
        warn("tmux", "not found; teammate reaping is a no-op (everything else works)",
             "install tmux only if you use agent teams")


def check_metrics():
    if (os.environ.get("ORCH_METRICS") or "").strip() == "0":
        ok("metrics", "off (ORCH_METRICS=0)")
        return
    d = os.path.join(os.path.expanduser("~"), ".claude", "orchestrator")
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".doctor-probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        ok("metrics", f"{d}/metrics.jsonl (local only, never uploaded)")
    except Exception as e:
        warn("metrics", f"{d} not writable: {e}", "set ORCH_METRICS=0 or fix permissions")


def check_workflow():
    cwd = os.getcwd()
    d = os.path.join(cwd, ".workflow")
    if not os.path.isdir(d):
        ok("workflow", "no .workflow/ here yet (/orchestrate creates it)")
        return
    ledgers = sorted(f for f in os.listdir(d)
                     if f.startswith("LEDGER") and f.endswith(".md") and not f.endswith("-archive.md"))
    if not ledgers:
        ok("workflow", ".workflow/ exists, no active ledger")
        return
    for name in ledgers:
        text = _read(os.path.join(d, name))
        opened = len(re.findall(r"^\s*[-*] \[ \]", text, flags=re.M))
        done = len(re.findall(r"^\s*[-*] \[[xX]\]", text, flags=re.M))
        deferred = len(re.findall(r"^\s*[-*] \[~\]", text, flags=re.M))
        clarified = bool(re.search(r"^#{1,6}\s*clarified\b", text, flags=re.M | re.I))
        vpath = os.path.join(d, "verify", name[:-3] + ".json")
        verdict = "no verdict"
        if os.path.isfile(vpath):
            try:
                verdict = "verdict: " + str(json.loads(_read(vpath)).get("verdict"))
            except Exception:
                verdict = "verdict file unreadable"
        (ok if clarified else warn)(
            f"ledger {name}",
            f"open {opened}, done {done}, deferred {deferred}, "
            f"{'clarified' if clarified else 'NO ## Clarified'}, {verdict}")


def main():
    check_python()
    check_manifests()
    tiers, routing = check_tiers()
    check_agents(tiers, routing)
    check_commands()
    check_skills()
    check_gates()
    check_tmux()
    check_metrics()
    check_workflow()
    fails = [r for r in ROWS if r["status"] == "FAIL"]
    if "--json" in sys.argv:
        print(json.dumps({"rows": ROWS, "ok": not fails}, indent=2))
    else:
        width = max(len(r["check"]) for r in ROWS)
        for r in ROWS:
            line = f"{r['status']:4} {r['check']:<{width}}  {r['detail']}"
            if r["fix"]:
                line += f"\n     {'':<{width}}  fix: {r['fix']}"
            print(line)
        print()
        print("orchestrator: READY" if not fails else
              f"orchestrator: {len(fails)} problem(s) to fix")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

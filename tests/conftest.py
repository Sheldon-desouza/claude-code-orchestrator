import functools
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"

# Env vars that would leak the host's configuration into the tests.
STRIP_ENV = [
    "LEDGER_GUARD_THRESHOLD",
    "LEDGER_GUARD_TASKS",
    "LEDGER_GUARD_CLARIFY",
    "LEDGER_GUARD_STOP_MODE",
    "ORCH_METRICS",
    "ORCH_SWARM_CLEANUP",
    "ORCH_SWARM_MAX_IDLE_H",
    "ORCH_TEAMMATE_IDLE_H",
    "ORCH_TEAMMATE_IDLE_RATE",
    "ORCH_PROFILE",
    "ORCH_TEAMMATE_STOP",
    "ORCH_TEAMMATE_INJECT",
    "ORCH_ROUTE_GUARD",
    "ORCH_VERIFY_GUARD",
    "ORCH_CONFIG_DIR",
    "ORCH_BUDGET",
    "ORCH_BUDGET_SPAWNS",
    "ORCH_BUDGET_HEAVY",
    "ORCH_SOLO_GUARD",
    "ORCH_SOLO_EDITS",
    "ORCH_NAME_CHARS",
    "ORCH_NAME_GATE",
    "ORCH_REMIND",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
    "CLAUDE_CONFIG_DIR",
    "TMUX_TMPDIR",
    "CLAUDE_PLUGIN_ROOT",
]


@functools.lru_cache(maxsize=1)
def _chair_ps_dir():
    """A PATH shim that pins the ancestor walk to an untagged `claude`.

    The hooks answer "am I a teammate?" by walking the REAL process
    tree for `--agent-id`. That makes the suite's result depend on WHO
    RAN IT: from inside a named agent-teams worker — a teammate running
    the tests, or a fresh-eyes verifier checking a release — every hook
    correctly decides "teammate", skips its chair behaviour, and ~40
    tests fail for a reason that has nothing to do with the code under
    test. Pinning the ambient here is the same move as the
    CLAUDE_CONFIG_DIR and ORCH_SWARM_CLEANUP defaults below: the
    sandbox states its own world instead of inheriting the developer's.

    Only the ancestor-walk invocation is answered; every other `ps`
    call falls through to the real binary, and any test that exercises
    the detection supplies its own `ps` via env_extra["PATH"] and never
    reaches this shim.
    """
    bin_dir = Path(tempfile.mkdtemp(prefix="orch-testshim-"))
    ps = bin_dir / "ps"
    ps.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "if 'ppid=,command=' in sys.argv:\n"
        "    print('1 claude')\n"
        "    sys.exit(0)\n"
        "os.execv('/bin/ps', ['ps'] + sys.argv[1:])\n",
        encoding="utf-8",
    )
    os.chmod(ps, 0o755)
    return str(bin_dir)


def run_hook(script, payload=None, raw=None, env_extra=None, tmpdir=None):
    """Run a hook script as a subprocess, exactly as Claude Code would.

    Returns the parsed JSON it printed, or None for empty output.
    `tmpdir` redirects tempfile.gettempdir() inside the subprocess so
    session-cache reads/writes stay inside the test sandbox.
    """
    env = {k: v for k, v in os.environ.items() if k not in STRIP_ENV}
    env["ORCH_METRICS"] = "0"        # keep tests from writing ~/.claude metrics
    env["ORCH_SWARM_CLEANUP"] = "0"  # keep tests away from real tmux servers
    # The route and verify gates are NEW on top of the upstream suite;
    # legacy tests exercise the ledger gates alone. A test about a new
    # gate turns it on explicitly via env_extra.
    env.setdefault("ORCH_ROUTE_GUARD", "0")
    env.setdefault("ORCH_VERIFY_GUARD", "0")
    env.setdefault("ORCH_BUDGET", "0")
    env["ORCH_CONFIG_DIR"] = str(Path(tmpdir) / "orchcfg") if tmpdir else "/nonexistent-orch-cfg"
    # Point Claude Code config at an (empty) sandbox dir so the injector's
    # settings.json model-detection never reads the developer's real
    # default. A test that wants the settings fallback writes
    # <tmpdir>/cfg/settings.json; others get no model key -> no leak.
    env["CLAUDE_CONFIG_DIR"] = str(Path(tmpdir) / "cfg") if tmpdir else "/nonexistent-orch-cfg"
    if tmpdir is not None:
        env["TMPDIR"] = str(tmpdir)
        env["TEMP"] = str(tmpdir)
        env["TMP"] = str(tmpdir)
    if env_extra:
        env.update(env_extra)
    # Ambient "this is a chair" — unless the test drives `ps` itself.
    if not (env_extra or {}).get("PATH"):
        env["PATH"] = _chair_ps_dir() + os.pathsep + env.get("PATH", "")
    # Insurance: a test that turns the swarm cleanup ON without pointing
    # tmux at a sandbox would sweep the developer's REAL tmux servers.
    assert env.get("ORCH_SWARM_CLEANUP") != "1" or "TMUX_TMPDIR" in env, \
        "ORCH_SWARM_CLEANUP=1 requires a sandboxed TMUX_TMPDIR"
    stdin = raw if raw is not None else json.dumps(payload or {})
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    return json.loads(out) if out else None


@pytest.fixture
def repo_dir(tmp_path):
    """A fake repo root: the upward ledger search stops at .git."""
    (tmp_path / ".git").mkdir()
    return tmp_path


# What a clarified ledger looks like: the Rule 0.5 gate wants an
# answered question (`Q -> A`) and a `- Branch:` line under
# `## Clarified`, and every test that is about the LEDGER gates rather
# than the clarify gate needs one to get past it.
CLARIFIED = "## Clarified\n- Q1: what is the scope? -> the whole thing\n- Branch: main\n\n"


def write_ledger(root, body="- [ ] 1. item\n", clarified=True):
    """Write .workflow/LEDGER.md, clarified unless the test says otherwise.

    `clarified=False` (or a body that already carries the heading)
    leaves the section off, which is what the clarify-gate tests want.
    """
    d = root / ".workflow"
    d.mkdir(parents=True, exist_ok=True)
    if clarified and not re.search(r"^[ \t]{0,3}#{1,6}[ \t]*clarified\b",
                                   body, flags=re.M | re.I):
        body = CLARIFIED + body
    (d / "LEDGER.md").write_text(body, encoding="utf-8")
    return d / "LEDGER.md"

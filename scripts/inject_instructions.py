#!/usr/bin/env python3
"""SessionStart hook: inject the Dynamic Workflow instructions.

This plugin is built for a Claude Fable 5 chair, with an Opus
fallback: when the Fable limit is spent and the user moves the chair to
Opus, the OPUS profile keeps the same discipline (the fable tier rests,
verification and the escalation ceiling fall to opus). The chair is
detected per session start and the matching profile injected:

    opus chair    -> dynamic-workflow-opus.md
    anything else -> dynamic-workflow-fable.md   (fable / unknown)

Detection, in priority order (first hit wins):

    1. ORCH_PROFILE = fable | opus   — explicit pin, overrides all
       (auto / unset falls through to detection)
    2. the SessionStart payload's `model`  — authoritative for THIS
       session start, but the harness omits it on some resume/compact
       fires
    3. the user's configured default model in Claude Code settings.json
       — what `/model` persists, so it still tracks the chair when (2)
       is absent (the common "I switched to Opus but the payload was
       empty" case)
    4. the last model this session's marker saw — sticky fallback so a
       null-payload resume never regresses an opus session to fable
    5. fable — the safe default

A mid-session /model switch still only takes visible effect at the next
session start (startup/resume/clear), because SessionStart is the sole
injection point — but (3) makes that next start reliable instead of
racy.

PROFILE-SWITCH DELTA. When a session that already received a core
profile re-fires with the OTHER profile selected (the Fable limit ran
dry mid-session and the chair moved to Opus, or back), the full core is
NOT re-sent — it is already in context, and re-sending it spends the
very limit it exists to protect. A short switch note carries only the
deltas instead:

    fable -> opus -> profile-switch-to-opus.md
    opus  -> fable -> profile-switch-to-fable.md

The marker records the profile this session was last TOLD, so a plain
re-fire (same profile) is indistinguishable from before — it still gets
the full core. A marker with no recorded profile (a pre-0.15.0 marker,
or a session whose only fires were teammate skips) also gets the full
core: a delta is only ever safe on top of a core this session saw.

The delta is further gated to SessionStart `source == "resume"`, the
only fire that provably leaves the earlier injection in context.
`compact` fires precisely BECAUSE the context was rewritten, `clear`
because it was discarded, and a future source is simply unproven — all
three get the full core even when the profile changed. The switch note
says "every other rule from the already-injected core profile stays in
force", which is a lie the chair cannot detect if the core is gone.

TEAMMATE sessions are skipped entirely. Named agent-teams workers are
full claude sessions and fire SessionStart like the chair does — but the
profile is written for the chair alone: injected into a worker it says
"you are the ORCHESTRATOR" and invites it to spawn subagents, inverting
the very discipline the plugin enforces (measured in the wild: 172 of
270 injected sessions were teammates). Detection is the same ancestor
walk the stop guard uses (`--agent-id` on the nearest claude ancestor);
the session marker is still written so the other guards keep working.
ORCH_TEAMMATE_INJECT=1 restores the old inject-everyone
behaviour.

The hook also maintains the per-session marker the Stop and SessionEnd
hooks rely on: its immutable `started` timestamp survives the re-runs
SessionStart gets on resume/clear/compact, and the stop guard compares
ledger mtimes against it to decide ownership.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tiers import load_tiers, tier_of  # noqa: E402


def session_model_cache_path(session_id):
    """Per-session marker file the stop/cleanup hooks read. None if no id."""
    if not session_id:
        return None
    safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_")
    return os.path.join(tempfile.gettempdir(), f"orch-model-{safe}.json")


def _metric(event, session_id=None, **extra):
    """Append one event line to ~/.claude/orchestrator/metrics.jsonl (best effort)."""
    if (os.environ.get("ORCH_METRICS") or "").strip() == "0":
        return
    try:
        d = os.path.join(os.path.expanduser("~"), ".claude", "orchestrator")
        os.makedirs(d, exist_ok=True)
        rec = {"ts": round(time.time(), 3), "event": event}
        if session_id:
            rec["session"] = str(session_id)[:8]
        rec.update(extra)
        with open(os.path.join(d, "metrics.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


PROFILES = ("chair", "fallback")


def _profile_for(model, tiers=None):
    """'chair' when the model is the configured chair tier or unknown
    (a brand-new model name is more likely the top tier than not, and
    the safe side hands it the full profile); 'fallback' when it
    resolves to any OTHER tier — the chair tier's limit is spent and a
    cheaper model holds the chair, so the profile must tell it not to
    spawn the resting tier."""
    t = tier_of(model, tiers or load_tiers())
    return "chair" if t in (None, "chair") else "fallback"


def render_profile(profile, model=None, switch=False, tiers=None, root=None):
    """The chair text for `profile`, rendered from the tier map.

    One template serves every chair: the tier map supplies the model
    names, so a new model is a one-line config change, not a release.
    `switch=True` renders the short delta note instead of the full
    core (see the PROFILE-SWITCH DELTA note in the module docstring).
    """
    tiers = tiers or load_tiers()
    root = root or os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    name = "profile-switch.md.tmpl" if switch else "profile.md.tmpl"
    with open(os.path.join(root, "instructions", name), encoding="utf-8") as f:
        text = f.read()
    chair = tiers["chair"]["model"]
    heavy = tiers["heavy"]["model"]
    held_by = tier_of(model, tiers) if model else None
    if profile == "fallback":
        holder = tiers.get(held_by, {}).get("model", str(model or "fallback"))
        fields = {
            "PROFILE_LABEL": f"FALLBACK profile: {holder} holds the chair, {chair} rests",
            "PROFILE_NOTE": (f"The {chair} limit is spent; {holder} holds the chair until "
                             f"it returns. Do NOT spawn {chair}-tier agents — they burn "
                             f"the exhausted limit. {heavy} is the escalation ceiling "
                             f"and every verifier. The usage limit still wins over "
                             f"context hygiene."),
            "CHAIR": holder,
            "ROUTING_NOTE": (f"\nThe chair tier ({chair}) is RESTING: never spawn it; its "
                             f"roles fall to heavy ({heavy})."),
        }
    else:
        fields = {
            "PROFILE_LABEL": f"CHAIR profile: {chair} in the chair",
            "PROFILE_NOTE": (f"{chair}-in-chair, token-frugal: the scarce resource is the "
                             f"USAGE LIMIT. When the limit and context hygiene conflict, "
                             f"the limit wins. {heavy} spares the {chair} limit wherever it "
                             f"can; {chair} is the escalation ceiling."),
            "CHAIR": chair,
            "ROUTING_NOTE": "",
        }
    fields["PROFILE_NAME"] = "FALLBACK" if profile == "fallback" else "CHAIR"
    fields.update({"HEAVY": heavy, "BULK": tiers["bulk"]["model"],
                   "CHEAP": tiers["cheap"]["model"]})
    for key, val in fields.items():
        text = text.replace("{{" + key + "}}", val)
    return text


def _configured_model():
    """The user's configured default model from Claude Code settings, or
    None. `/model` persists the default here, so it tracks the current
    chair even when the SessionStart payload omits `model`. settings.local
    overrides settings; either may carry the key."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    for name in ("settings.local.json", "settings.json"):
        try:
            with open(os.path.join(base, name), encoding="utf-8") as f:
                m = json.load(f).get("model")
        except Exception:
            continue
        if isinstance(m, str) and m.strip():
            return m
    return None


def _read_marker(cache):
    """(started, model, profile) from the marker; (None, None, None) if unreadable.

    `profile` is the profile this session was last INJECTED with — the
    switch detector's only input. It is absent on markers written by
    pre-0.15.0 versions and on sessions whose fires were all teammate
    skips; in both cases the caller must fall back to the full core."""
    if not cache:
        return None, None, None
    try:
        with open(cache, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            return d.get("started"), d.get("model"), d.get("profile")
    except Exception:
        pass
    return None, None, None


TEAMMATE_DETECT_BUDGET = 1.5  # seconds; the walk measures ~5ms in practice


def _budget(deadline, cap=5.0):
    """Seconds a subprocess may run without overshooting the deadline.

    Monotonic, exactly as in the stop guard: a wall clock can step
    backwards (NTP, a manual change) and would then hand back a budget
    that never expires, defeating the bound entirely."""
    if deadline is None:
        return cap
    return max(0.2, min(cap, deadline - time.monotonic()))


def _is_teammate_session(max_hops=12):
    """True when this hook is running inside a named teammate.

    Teammates are launched with `--agent-id`. The profile belongs to the
    CHAIR: a worker that receives it is told it is the orchestrator and
    may spawn subagents liberally — the inverse of its actual job. Walks
    up to the first claude ancestor and answers from its argv; same
    logic as the stop guard's copy, kept verbatim so a future common
    module can unify them.

    HARD-BUDGETED because SessionStart must never hang a session open:
    on budget exhaustion the answer is False — "assume chair", so the
    profile is still delivered. That failure costs one teammate carrying
    the profile (the pre-fix behaviour for every teammate); the opposite
    default would strip the chair of its orchestration instructions.
    """
    deadline = time.monotonic() + TEAMMATE_DETECT_BUDGET
    pid = os.getpid()
    for _ in range(max_hops):
        if time.monotonic() > deadline:
            return False
        try:
            out = subprocess.run(
                ["ps", "-o", "ppid=,command=", "-p", str(pid)],
                capture_output=True, text=True, timeout=_budget(deadline),
            ).stdout.strip()
            bits = (out.splitlines()[0] if out else "").split(None, 1)
            ppid = int(bits[0])
        except Exception:
            return False
        command = bits[1] if len(bits) > 1 else ""
        for tok in command.split():
            base = os.path.basename(tok.strip("\"'"))
            if base == "claude" or "claude-code" in tok or base.startswith("2."):
                return "--agent-id" in command
        if ppid <= 1:
            return False
        pid = ppid
    return False


def resolve_profile(payload_model, configured_model, marker_model):
    """Return (profile, source, model) — 'chair'|'fallback', which signal
    decided, and the model string it decided from.
    Priority: env override > payload model > settings default > marker.
    ORCH_PROFILE accepts a profile name (`chair`/`fallback`) or any model
    or tier name the tier map resolves (`opus`, `fable`, `claude-opus-5`);
    `auto`/unset falls through to detection."""
    tiers = load_tiers()
    override = (os.environ.get("ORCH_PROFILE") or "").strip().lower()
    if override in PROFILES:
        model = payload_model or configured_model or marker_model
        return override, "override", model
    if override and override != "auto" and tier_of(override, tiers):
        return _profile_for(override, tiers), "override", override
    if str(payload_model or "").strip():
        return _profile_for(payload_model, tiers), "payload", payload_model
    if str(configured_model or "").strip():
        return _profile_for(configured_model, tiers), "settings", configured_model
    if str(marker_model or "").strip():
        return _profile_for(marker_model, tiers), "marker", marker_model
    return "chair", "default", None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

    model = data.get("model")  # optional; the harness omits it on some fires
    session_id = data.get("session_id")
    fire = data.get("source")  # startup | resume | clear | compact (advisory)
    cache = session_model_cache_path(session_id)
    prev_started, prev_model, prev_profile = _read_marker(cache)

    profile, source, decided_from = resolve_profile(model, _configured_model(), prev_model)

    # Profile-switch delta: this session already carries a core profile
    # and the chair has since moved to the other tier. Re-sending ~3.7k
    # chars of unchanged rules costs the limit the profile exists to
    # protect, so only the deltas go out. Requires a RECORDED previous
    # profile — never inferred, because a delta on top of no core would
    # silently strip the chair of every orchestration rule.
    # GATED TO `resume`, the only fire that provably keeps the core in
    # context. `compact` re-fires BECAUSE the context was rewritten and
    # `clear` because it was discarded — a delta on either can leave the
    # chair with no threshold, no ledger rule and no routing, silently.
    # Any unrecognised future source takes the same safe side: an
    # unproven source gets the full core. Wrong-delta costs a ruleless
    # chair; wrong-full-core costs ~3.7k chars.
    switched = (bool(prev_profile) and prev_profile != profile
                and fire == "resume")

    # The profile is chair-only; a teammate session skips the injection
    # but still gets its marker below — stop, spawn, and cleanup key off
    # it. Resolution ran first so the skip metric records which profile
    # the worker WOULD have received.
    teammate = False
    if (os.environ.get("ORCH_TEAMMATE_INJECT") or "").strip() != "1":
        teammate = _is_teammate_session()

    text = None
    if not teammate:
        try:
            text = render_profile(profile, model=decided_from, switch=switched)
        except Exception:
            return  # never break session start

    # Session marker for the guards (best effort; never fatal).
    # `started` marks the session's FIRST start and must survive the
    # re-runs SessionStart gets on resume/clear/compact — the stop guard
    # compares ledger mtimes against it to decide ownership, so it can
    # never move forward. `model` keeps the last NON-EMPTY model seen, so
    # a later null-payload fire stays sticky instead of forgetting the
    # chair.
    try:
        if cache:
            started = prev_started
            try:
                started = float(started)
            except (TypeError, ValueError):
                # Marker from an older version (no `started`) or corrupt:
                # fall back to the file's mtime — NEVER to "now", which
                # would disown every ledger touched before this re-run.
                try:
                    started = os.path.getmtime(cache)
                except OSError:
                    started = time.time()
            stored_model = model if str(model or "").strip() else prev_model
            # `profile` records what this session was actually TOLD, so
            # the next fire can tell a switch from a plain re-fire. A
            # teammate received nothing, so its marker carries the
            # previous value forward rather than claiming an injection
            # that never happened.
            stored_profile = prev_profile if teammate else profile
            # Atomic replace: a crash mid-write must never leave a
            # truncated marker. The tmp name keeps the orch-*.json
            # shape so an orphan from a crash still matches the 96h sweep.
            tmp = f"{cache}.{os.getpid()}.tmp.json"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {"model": stored_model, "session_id": session_id,
                     "started": round(started, 3), "profile": stored_profile},
                    f,
                )
            os.replace(tmp, cache)
    except Exception:
        pass

    if teammate:
        _metric("inject_skipped", session_id, model=model, profile=profile,
                source=source, reason="teammate")
        return

    if switched:
        # Distinct event, not a field on `inject`: an inject counts a
        # session that received the discipline, a switch counts a chair
        # that moved tiers mid-session. `fire` records which SessionStart
        # kind delivered the delta (resume/compact/clear).
        _metric("inject_switch", session_id, model=model, profile=profile,
                source=source, from_profile=prev_profile, fire=fire)
    else:
        _metric("inject", session_id, model=model, profile=profile,
                source=source)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--render":
        # `--render chair|fallback [model] [--switch]`: print the text a
        # session would receive, without touching any marker.
        which = sys.argv[2]
        rest = [a for a in sys.argv[3:] if a != "--switch"]
        print(render_profile(which, model=(rest[0] if rest else None),
                             switch="--switch" in sys.argv[3:]), end="")
    else:
        main()

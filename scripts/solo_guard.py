#!/usr/bin/env python3
"""PreToolUse guard: the gate that watches the CHAIR, not the delegation.

Ported from Rylaa/fable5-opus5.5-orchestrator v0.16.0-v0.16.1 (MIT),
where it was measured into existence: five consecutive sessions
received the full profile and spawned zero workers while hand-editing
dozens of files. Every other gate in this plugin watches DELEGATION
(spawn prompts, tracker tasks, the close), so a chair that never
delegates never meets one. This one counts the chair's own edits.

    Agent / Task                            -> records a spawn (and, with
                                               agent teams on, asks once
                                               for a `name` on a long
                                               unnamed spawn)
    Edit / Write / MultiEdit / NotebookEdit -> counted; the Nth in a
                                               session with zero spawns
                                               is denied, ONCE

It is a nudge, not a wall: two edits pass free, the deny fires once per
session, and the message says how to proceed if it really was a
single-sitting fix. One spawned worker disarms it for the session.

Exempt: teammates (a worker's job IS to edit files) and any session
that has spawned a worker. A fork does NOT count as delegating — it is
the chair's own context at the chair's own model.

Not covered on purpose: `Bash` heredocs and `sed -i`. Telling
`cat > file` from `cat file` means parsing shell, and a guard that
misreads a read as a write is worse than a known hole. The per-prompt
reminder (remind_chair.py) covers that path.

The naming half: a named teammate runs in a tmux pane the user watches;
an unnamed subagent is a silent spinner. Names only mean something with
agent teams, so the naming gate is ON only when
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is set (or ORCH_NAME_GATE=1).

Configuration:
    ORCH_SOLO_EDITS    deny at the Nth chair edit (default 3; 0 disables)
    ORCH_SOLO_GUARD=0  disables this hook entirely
    ORCH_NAME_CHARS    prompt length that needs a name (default 1500; 0 off)
    ORCH_NAME_GATE     1 forces the naming gate on, 0 off; default follows
                       CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _state import env_int, env_off, tmp_json, update_state  # noqa: E402
from inject_instructions import _is_teammate_session, _metric  # noqa: E402

DEFAULT_EDIT_LIMIT = 3
DEFAULT_NAME_CHARS = 1500
SPAWN_TOOLS = ("Agent", "Task")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")

DENY_REASON = (
    "SOLO GUARD: you are the ORCHESTRATOR, and this session has made "
    "{count} file edits with no worker spawned. Every token you spend "
    "editing is spent on the most expensive tier.\n\n"
    "Hand the rest to workers: `orch-implementer` (Class: implement) for "
    "the volume, `orch-hard-slice` (Class: hard) for the hard slice. "
    "Give each a spec that cites ledger items and spawn independent ones "
    "in ONE message.\n\n"
    "If this really is a single-sitting fix the user asked for directly, "
    "say so in one line and redo the edit. This fires once per session."
)

NAME_REASON = (
    "NAME GATE: this {count}-char spawn has no `name`. A named teammate "
    "runs in a tmux pane the user watches live; an unnamed one runs where "
    "nobody can see it. Re-send the same spawn with `name` set to a short "
    "kebab-case label for the job. Sub-minute lookups can stay unnamed. "
    "This fires once per session."
)


def edit_limit():
    return env_int("ORCH_SOLO_EDITS", DEFAULT_EDIT_LIMIT)


def name_gate_on():
    forced = (os.environ.get("ORCH_NAME_GATE") or "").strip()
    if forced in ("0", "1"):
        return forced == "1"
    teams = (os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS") or "").strip()
    return teams not in ("", "0", "false", "False")


def _deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _record_spawn(session_id, unnamed):
    """Mark the session as orchestrating. True when this is the session's
    first unnamed-spawn deny. The spawn counts either way: the retry with
    a name is the same worker, and a chair plainly delegating must not
    then be denied its own small edits."""
    def mutate(state):
        try:
            spawns = int(state.get("spawns") or 0)
        except (TypeError, ValueError):
            spawns = 0
        state["spawns"] = spawns + 1
        deny_now = bool(unnamed) and not bool(state.get("named_denied"))
        if unnamed:
            state["named_denied"] = True
        return state, deny_now
    return bool(update_state(tmp_json("orch-solo", session_id), mutate))


def _count_edit(session_id):
    """(count, spawns, denied_before) after counting this edit, or None."""
    def mutate(state):
        try:
            count = int(state.get("edits") or 0) + 1
        except (TypeError, ValueError):
            count = 1
        try:
            spawns = int(state.get("spawns") or 0)
        except (TypeError, ValueError):
            spawns = 0
        denied_before = bool(state.get("denied"))
        limit = edit_limit()
        deny_now = limit > 0 and count >= limit and spawns == 0 and not denied_before
        state.update(edits=count, spawns=spawns, denied=denied_before or deny_now)
        return state, (count, spawns, denied_before)
    return update_state(tmp_json("orch-solo", session_id), mutate)


def guard(data):
    if env_off("ORCH_SOLO_GUARD"):
        return None
    tool = data.get("tool_name") or ""
    session_id = data.get("session_id")

    if tool in SPAWN_TOOLS:
        tool_input = data.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            tool_input = {}
        if str(tool_input.get("subagent_type") or "").strip().lower() == "fork":
            return None  # the chair's own context: not delegating, no pane
        prompt = str(tool_input.get("prompt") or "")
        limit = env_int("ORCH_NAME_CHARS", DEFAULT_NAME_CHARS)
        unnamed = (limit > 0 and name_gate_on()
                   and not str(tool_input.get("name") or "").strip()
                   and len(prompt) >= limit)
        if _record_spawn(session_id, unnamed):
            _metric("unnamed_spawn_deny", session_id, chars=len(prompt), tool=tool)
            return _deny(NAME_REASON.format(count=len(prompt)))
        return None

    if tool not in EDIT_TOOLS or edit_limit() <= 0:
        return None
    if _is_teammate_session():
        return None
    result = _count_edit(session_id)
    if result is None:
        return None
    count, spawns, denied_before = result
    if spawns or count < edit_limit():
        return None
    if denied_before:
        _metric("solo_suppressed", session_id, count=count)
        return None
    _metric("solo_deny", session_id, count=count, tool=tool)
    return _deny(DENY_REASON.format(count=count))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    try:
        out = guard(data)
    except Exception:
        return  # a broken guard must never block a tool call
    if out:
        print(json.dumps(out))


if __name__ == "__main__":
    main()

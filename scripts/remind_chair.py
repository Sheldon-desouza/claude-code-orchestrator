#!/usr/bin/env python3
"""UserPromptSubmit hook: one line of orchestration on every prompt.

Ported from Rylaa/fable5-opus5.5-orchestrator v0.16.0 (MIT). The core
profile arrives once, at SessionStart, and then competes with every
token after it; in a many-hour session a rule read at hour zero loses.
This restates the loop in ~40 tokens and nothing else — routing,
effort and the report contract stay in the core and the playbook.

Teammates are skipped: a worker told to delegate would spawn workers of
its own, the exact failure the plugin exists to prevent.

    ORCH_REMIND=0   disables the per-prompt line
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _state import env_off  # noqa: E402
from inject_instructions import _is_teammate_session  # noqa: E402

REMINDER = (
    "[orchestrator] You are the CHAIR: clarify, ledger, then delegate by "
    "class (`Class:` tag, orch-* workers, independent ones in one message). "
    "Read reports, not bulk. Solo only for a single-sitting fix."
)


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass
    if env_off("ORCH_REMIND"):
        return
    try:
        if _is_teammate_session():
            return
    except Exception:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": REMINDER,
    }}))


if __name__ == "__main__":
    main()

---
description: Diagnose the orchestrator install — Python, hooks, tier map, agents in sync, tmux, metrics path, and the current .workflow state — and print exactly what to fix.
allowed-tools: Bash
---

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py"` and present its report verbatim. For every line marked `FAIL` or `WARN`, restate the fix in one sentence. If everything passes, say the plugin is ready and point at `/orchestrate`.

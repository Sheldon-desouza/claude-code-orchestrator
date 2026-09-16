---
description: Show orchestrator metrics — gate denials, routing mix by class and tier, spawns per session, clarify misses — from the local metrics log.
argument-hint: [--json]
allowed-tools: Bash
---

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/stats.py" $ARGUMENTS` and present the output. The log is local (`~/.claude/orchestrator/metrics.jsonl`), never sent anywhere, and `ORCH_METRICS=0` turns it off.

If the log is empty, say that the plugin has not seen an orchestrated session yet on this machine and point at `/orchestrate`.

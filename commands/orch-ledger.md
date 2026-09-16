---
description: Show the active Requirements Ledger — clarified answers, open, done and deferred items, and the verify verdict if one exists.
argument-hint: [archive]
allowed-tools: Read, Glob, Bash
---

Find the active ledger: the most recent `.workflow/LEDGER*.md` (excluding `*-archive.md`) searching from the working directory up to the repo root.

If `$ARGUMENTS` is `archive`: rename it to `LEDGER-<topic>-archive.md` (derive `<topic>` from its first heading or first item) and confirm; a fully closed ledger from an earlier task must not keep gating this one.

Otherwise print, compactly:
- the `## Clarified` block verbatim
- counts: open `- [ ]`, done `- [x]`, deferred `- [~]`
- every open item, one per line
- whether `./.workflow/verify/<ledger-stem>.json` exists and its `verdict`
- whether the ledger was modified in this session (compare its mtime against the session marker in the temp dir, `orch-model-<session_id>.json`)

If no ledger exists, say so and point at `/orchestrate`.

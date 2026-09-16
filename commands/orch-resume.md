---
description: Rebuild orchestration state after a crash, /clear or compaction — reads the ledger, scratch index and verify verdicts from disk and tells you where the job stands.
allowed-tools: Read, Glob, Bash
---

The orchestration state lives on disk, not in this conversation. Reconstruct it:

1. Active ledger: most recent `.workflow/LEDGER*.md` excluding `*-archive.md`, searched upward from the working directory. Print `## Clarified` verbatim and the open / done / deferred counts.
2. Scratch index: list `./.workflow/scratch/` by mtime with sizes; for each file, one line on what it appears to hold (read only the first 20 lines).
3. Verdicts: every `./.workflow/verify/*.json`, its `verdict`, timestamp, and any `findings`.
4. Working tree: `git status --short` and `git diff --stat` so uncommitted worker output is visible.
5. Running workers: if `ListAgents` is available, list them; otherwise say the session cannot see them.

Then state, in ≤10 lines: what was asked, what is clarified, what is done, what is open, what is blocked, and the next action by class. Do not start work — the user decides whether to continue.

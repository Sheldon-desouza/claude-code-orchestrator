---
description: Spawn a fresh-eyes verifier for the active ledger (bulk tier; heavy for risky closes). It writes the verdict file and is the only agent that may close the V. item.
argument-hint: [ledger path]
allowed-tools: Read, Glob, Agent
---

Locate the active ledger (or use `$ARGUMENTS` as its path). Gather the work-product paths: diffs (`git diff --stat` and the files it names), worker reports in `./.workflow/scratch/`, test output. Do NOT hand the verifier the raw scratch dump.

Spawn ONE `orch-verifier` agent (`Class: verify`, effort `high`). It runs on the bulk tier by default; for security, irreversible or architecture closes pass the heavy model (`model: opus`, effort `xhigh`). Give it:
- the original request as the user phrased it
- the ledger path
- the work-product paths
- the instruction to write `./.workflow/verify/<ledger-stem>.json` and tick `V.` only on a passing verdict

When it returns: if `fail`, append each finding as a new `- [ ] N.` ledger item and route the fixes by class. Cap at 3 verify→fix cycles, then report the open items to the user. Never tick `V.` yourself.

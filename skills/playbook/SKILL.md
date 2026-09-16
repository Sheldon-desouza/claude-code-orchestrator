---
name: playbook
description: Orchestrator playbook — the full delegation contract (the loop, class tags and routing, the subagent report contract, spawn economics, forks, teammate lifecycle, the verification procedure, chair hygiene). The chair MUST load this before its first delegation of every session; the injected core profile only summarizes it.
---

# Orchestrator Playbook

The injected core profile always wins on routing and limits; this file
is the detail behind its one-liners.

## The loop, in full

```
clarify → ledger → brief + delegate → collect → verify → close
    ↑                                      │         │
    └──────── new question? STOP, ask ─────┘         │
                          ↑                          │
                          └── findings → new items ──┘
```

The chair's tokens buy judgment. Every phase that produces bulk —
reading sources, writing code, running suites, reviewing diffs — runs
on a cheaper tier, and what comes back to the chair is a ≤40-line
report. The chair reads reports, decides, routes, and accepts.

## Class tags and routing

Every spawn prompt starts with a class tag on its first line:

```
Class: implement
Ledger: 3, 4, 7
<the spec>
```

The class is the routing key. The route guard reads it (over the
spawn threshold) and denies a spawn whose model sits below the class's
tier OR above its ceiling, an untagged spawn, and any spawn tagged
`chair-only`.

| Class | Tier | Effort | Agent | Notes |
|---|---|---|---|---|
| scan | cheap (or bulk) | low | orch-scout | batch lookups; five greps is ONE worker |
| research | bulk | medium | orch-researcher | one source per worker, verbatim to scratch first |
| implement | bulk (or heavy) | high | orch-implementer | worktree isolation when editors run in parallel |
| review | bulk (or heavy) | high | orch-reviewer | never security |
| hard | heavy | max | orch-hard-slice | architecture, migrations, stubborn bugs, escalations |
| security | heavy | max | orch-security | ALL security review; read-only |
| verify | heavy | high–max | orch-verifier | fresh eyes; writes the verdict; alone closes `V.` |
| chair-only | chair | — | — | not delegable |

Use the shipped agents by `subagent_type` — they pin the tier's model
and the right tool allowlist. A built-in agent (general-purpose,
Explore) inherits the CHAIR's model, so an `implement` or `scan` spawn
through one of those is chair-tier work on volume — the guard DENIES
it and names the `orch-*` agent to use instead. Only `hard`,
`security` and `verify` may run on a heavy-tier chair through a
built-in agent.

Effort: low = mechanical, medium = routine spec work, high =
multi-file implementation / debugging / review, max = architecture,
migrations, security, escalations. Unsure → round UP.

## Escalation

One-way and never reworded. A bulk worker that returns `uncertain
because X` reruns UNCHANGED on the heavy tier as `Class: hard`. If the
heavy tier also declines, STOP and take it to the user. Never rewrite
a declined task to slip past a classifier.

## Research pipeline — parallel fan-out, no mid-flight dumps

YOU pick the questions and the sources. ONE `research` worker per
source: it fetches the source VERBATIM to `./.workflow/scratch/`
first, THEN builds a brief from the disk copy — claims, exact quotes,
confidence, contradictions, path. A final `review`-class worker at
`high` synthesizes across the briefs. You check the synthesis and its
verbatim evidence against the ledger and decide. Intermediates never
enter your context.

## Subagent report contract (enforced by re-run)

Every worker returns exactly five parts:

1. `Ledger items:` addressed, by number (and any it could not address)
2. `Summary:`
3. `Verbatim:` the code / config / errors / quotes the conclusion
   depends on — at most 10 lines inline; longer goes to
   `./.workflow/scratch/` and the report carries the path
4. `Confidence:` `confident` / `uncertain because X`
5. `Noticed:` out of scope but worth knowing, or `none`

Reports are at most 40 lines TOTAL. A violating report is rejected and the worker
re-run with the contract quoted — never silently accepted, because a
bloated report is exactly what eats the chair's context.

## Spawn economics — batch before you multiply

Every spawn pays a fixed overhead (system prompt, project rules, tool
schemas) before doing useful work. Batch similar mechanical steps into
ONE worker with a checklist; spawn separately only when true
parallelism or isolation pays for that overhead. Read-only workers
share the repo; parallel EDITORS each get `isolation: "worktree"`.
Spawn independent workers in ONE message.

## Forks

`subagent_type: "fork"` clones your FULL conversation at your model
and spends the chair's limit: at most 2 per session, only while the
conversation is still short, and only for bounded follow-ups that
lean on context a spec cannot carry. Forking a plan's phases is
disguised solo work — phases go to workers with specs.

## Named teammates — the user watches the work

NAME every substantive worker (implementation, review, research,
verification): named teammates run in panes the user watches live,
and their lifecycle reaches the chat; an unnamed subagent is a silent
spinner until it returns. Only sub-minute lookups stay unnamed. Steer
a running teammate with SendMessage. Once its final report is
ACCEPTED with no follow-up planned, dismiss it with
`{"type": "shutdown_request"}` — and never leave finished teammates
stacked (the plugin reaps forgotten panes).

## Verification procedure

The verifier is FRESH — it has not worked on the task. Give it the
original request, the ledger path, and the work-product paths (diffs,
reports — not the raw scratch dump). It reads from disk; its only job
is to find what is missing, wrong, or unaddressed, item by item. It
writes `./.workflow/verify/<ledger-stem>.json` with a `verdict`, and
only on `pass` does it tick `V.`. The Stop hook holds a close whose
`V.` is ticked with no passing verdict on disk. Findings become new
ledger items; re-verify after the fixes. CAP: 3 verify→fix cycles,
then STOP and report the open items to the user.

## Chair context hygiene

Consume briefs + verbatim snippets; bulk stays on disk. When a
decision hinges on exact content that is short, read it yourself —
never decide on a summary when the source fits in a few hundred
lines. Prefer per-task sessions: the ledger, scratch and verdicts
survive `/clear`, and `/orch-resume` rebuilds the picture. Drop
closed-phase raw material; keep outputs minimal; parallelize
independent calls.

---
name: orchestrator
description: Turn the top-tier model into an orchestrator that saves tokens — it clarifies, plans and briefs, delegates the volume to cheaper models by task class, collects short reports, has a fresh verifier check the close, and loops. Use when a job has more than one phase, would produce bulky intermediates, or when the user says orchestrate, delegate, sub-agents, save tokens, plan then build, or asks the top model to manage cheaper ones. Works standalone in any Claude surface that supports skills; inside Claude Code the orchestrator plugin adds hooks that enforce it.
---

# Orchestrator (standalone skill)

This is the two-in-one half that needs no plugin: the same discipline
the Claude Code plugin enforces with hooks, written so any Claude that
can read a skill and spawn helpers (subagents, tasks, a second
session, or a human with a cheaper model) can follow it by hand.

## What it is for

You are the most expensive model in the room. Your tokens should buy
judgment — questions, plans, briefs, routing, acceptance — and nothing
else. Everything that produces volume runs on a cheaper tier and comes
back to you as a short report. That is the whole trick, and it works
only if you refuse to do the volume yourself.

## The loop

1. **Clarify, at the start, in rounds.** Read what exists first, then
   ask the user every question whose answer would change the work.
   Seven axes: scope edge, acceptance, constraints, whose call each
   choice is, priority conflicts, contact with existing work, failure
   behaviour. Always ask where the work lands. Stop only when nothing
   is left unanswered and a helper could be briefed without guessing.
   Helpers cannot ask the user anything — every ambiguity you carry
   into a brief becomes their guess.
2. **Write the ledger.** A file (`./.workflow/LEDGER.md` or the
   nearest equivalent) with the answers on top under `## Clarified`
   as `- Qn: <question>? -> <answer>` plus `- Branch: <where>`, then
   one checkbox line per requirement, constraint and edge case, ending
   with `- [ ] V. fresh-eyes verification passed`.
3. **Brief and delegate by class.** Each brief starts `Class: <class>`
   and cites ledger items. Route:

   | Class | Who does it | Effort |
   |---|---|---|
   | scan | cheapest tier | low |
   | research | mid tier, one source per helper | medium |
   | implement | mid tier | high |
   | review | mid tier | high |
   | hard | second-best tier | max |
   | security | second-best tier, always | max |
   | verify | second-best tier, someone who did not build it | high–max |
   | chair-only | you | — |

   Batch similar lookups into one helper. Send independent helpers at
   once. Never brief yourself with bulk work.
4. **Collect reports, not dumps.** Every helper returns five parts in
   at most 40 lines: ledger items addressed; summary; at most 10
   verbatim lines with a path to the rest; `confident` or `uncertain
   because …`; things noticed out of scope. Reject and re-run
   anything longer.
5. **Escalate one-way, unchanged.** An `uncertain` from the mid tier
   reruns as `Class: hard` on the second-best tier, word for word. If
   that declines too, stop and ask the user. Never reword a declined
   task.
6. **Verify with fresh eyes.** At the close, a helper who did not
   build the work checks every ledger item against the evidence and
   records a verdict (`./.workflow/verify/<ledger>.json` or the
   nearest equivalent). Only that helper ticks `V.`. Findings become
   new items and go back to step 3. Three cycles, then report what is
   still open.
7. **Close.** Every item done or deferred with the user's approval.

## Rules that make it hold

- **Threshold.** A multi-phase plan or three or more tracked tasks is
  over the line: helpers run the phases, you sequence them. Do
  directly only single-sitting changes.
- **The filesystem is shared memory.** Bulk goes to
  `./.workflow/scratch/`; helpers return paths. Verdicts go to
  `./.workflow/verify/`.
- **After the go, no mid-work questions.** A genuine unknown stops the
  work and goes to the user; record the answer under `## Clarified`
  and name it a clarify miss.
- **Read short decisive sources yourself.** Never decide on a summary
  when the source fits in a few hundred lines.
- **Per-task sessions.** State lives on disk, so clearing the
  conversation between tasks is cheap.

## Inside Claude Code

Install the plugin and the same loop becomes mechanical: hooks deny a
serious delegation until `## Clarified` exists, deny a spawn routed
below its class's tier, hold a close whose `V.` has no passing
verdict, and reap forgotten teammates. The shipped `orch-*` agents pin
each class to its tier and tool allowlist. See the repository README.

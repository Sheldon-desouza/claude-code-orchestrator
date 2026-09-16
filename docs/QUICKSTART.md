# Quickstart — your first orchestrated job

Ten minutes, one real task. This walks through what you will see.

## 0. Install and check

```
/plugin marketplace add Sheldon-desouza/claude-code-orchestrator
/plugin install orchestrator@claude-code-orchestrator
```

Restart Claude Code. Open any project and run:

```
/orch-doctor
```

You want a wall of `OK` and the last line `orchestrator: READY`. A `WARN` on tmux is fine; it only matters for agent teams.

## 1. Give the chair a job

Set your model to the top tier you have (`/model`, then pick Fable if you have it; Opus works too, the plugin adapts). Then:

```
/orchestrate add CSV export to the reports page, with a date-range filter
```

## 2. Answer the questions

The chair reads the relevant files first, then asks. Expect a round of up to four questions like:

> - Should the export include archived reports? (changes the query)
> - Is the column order part of a contract downstream? (changes whether we can reorder)
> - Where does "done" get checked: a unit test, or you clicking it in the UI?
> - Does this land on the current branch or a new one?

Answer them. It may ask a second round if your answers opened new questions. This is the phase that stops workers from guessing; it is short and it is the most valuable minute of the session.

## 3. Watch the ledger appear

`./.workflow/LEDGER.md`:

```markdown
## Clarified
- Q1: include archived reports? -> no, active only
- Q2: is column order a contract? -> yes, keep it
- Q3: how is done checked? -> the existing export test suite plus a manual click
- Branch: feature/csv-export, new

- [ ] 1. Export endpoint returns CSV for the active-report query
- [ ] 2. Date-range filter applies to the export
- [ ] 3. Column order matches the current table
- [ ] 4. Export test suite passes
- [ ] V. fresh-eyes verification passed
```

## 4. Watch the routing

In the same message, the chair spawns its first wave. Each spawn starts with a class tag, and you will see the shipped agents by name:

```
orch-researcher   Class: research   → reads the current export module, briefs it
orch-implementer  Class: implement  → items 1–3, worktree
orch-implementer  Class: implement  → item 4, tests
```

If the chair tries to skip the tag or send a security review to Sonnet, you will see a hook denial in the transcript with the exact fix. That is the plugin working, not failing.

## 5. Reports come back

Each worker returns at most 40 lines in five parts. The chair reads those, not the diff. If a worker says `uncertain because …`, the chair re-runs that item unchanged on Opus as `Class: hard`.

## 6. The close

When every item is ticked, the chair spawns `orch-verifier` (or you run `/orch-verify`). It reads the ledger and the work from disk, checks each item, and writes `.workflow/verify/LEDGER.json`. If the verdict is `fail`, the findings become new ledger items and the loop goes round again. If it is `pass`, it ticks `V.` and the chair closes.

Try ending the turn early with `V.` ticked by hand: the Stop hook holds it and tells you to run the verifier. Once per session, so it does not nag.

## 7. Next time

- `/orch-ledger` shows where a job stands.
- `/orch-resume` rebuilds the picture after `/clear` or a crash.
- `/orch-stats` shows where your spawns went, by class and tier.
- `/orch-ledger archive` retires a finished ledger so it stops gating the next job.

## Changing which models are used

`~/.claude/orchestrator/tiers.json` (create it):

```json
{ "tiers": { "heavy": { "model": "opus", "match": ["opus"] } } }
```

Only the keys you include change. Run `/orch-doctor` afterwards.

## Using it without Claude Code

Upload [`skills/orchestrator/SKILL.md`](../skills/orchestrator/SKILL.md) as a skill in claude.ai or Claude Desktop, or drop it in your skills folder. It is the same loop written for a model that reads skills but has no hooks: it will still clarify first, write a ledger, brief by class, keep reports short, and verify with fresh eyes — it just relies on the model following the text rather than on a hook denying it.

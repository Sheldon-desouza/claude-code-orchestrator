# Claude Code Orchestrator — the token-saver plugin

[![CI](https://github.com/Sheldon-desouza/claude-code-orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/Sheldon-desouza/claude-code-orchestrator/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-blueviolet)](#install)

**Keep Claude Fable 5 (or whatever your top model is) in the chair. Let cheaper models do the work.**

A Claude Code plugin for **multi-agent orchestration that saves tokens**: the expensive model asks the questions, writes the plan and briefs the workers; Haiku scouts fetch, Sonnet builds and verifies; Opus takes the hard slices and every security review; and it loops until the ledger is done. Hooks enforce the loop so it does not depend on the model remembering to be frugal, including a per-session spawn budget and a guard that stops the top model doing the work itself.

It also ships as a **standalone skill** for claude.ai and Claude Desktop — same loop, no hooks — so it is two tools in one.

```
you ──job──▶ CHAIR (Fable 5)            asks, plans, briefs, routes, accepts
                │
                ├─ Class: scan       ──▶ Haiku    grep / fetch-to-disk / count
                ├─ Class: research   ──▶ Sonnet   brief the scout's saved copy
                ├─ Class: implement  ──▶ Sonnet   code to spec + tests
                ├─ Class: review     ──▶ Sonnet   standard review
                ├─ Class: hard       ──▶ Opus     architecture, migrations, stubborn bugs (xhigh, never max)
                ├─ Class: security   ──▶ Opus     always
                └─ Class: verify     ──▶ Sonnet   fresh eyes on the close, writes the verdict
                                         (Opus for security, irreversible or architecture closes)
                │
         ≤40-line reports come back ──▶ chair decides ──▶ loop until every ledger item is ticked
```

## Why

Multi-agent setups burn tokens: Anthropic measured roughly 15× a normal chat turn. The win only exists if the top model's tokens buy *judgment* and nothing else. Every plugin says that in its prompt. This one **enforces** it:

| The chair tries to… | The hook… |
|---|---|
| delegate before asking you the questions | denies the spawn until `## Clarified` holds real answers |
| delegate with no Requirements Ledger | denies the spawn until `.workflow/LEDGER.md` exists |
| run a security review on Sonnet | denies: "needs at least the `heavy` tier — spawn `orch-security`" |
| do bulk work through a built-in agent (which inherits the top model) | denies: "spends the expensive tier on volume — spawn `orch-implementer`" |
| edit files itself instead of delegating | denies its 3rd edit in a session with no worker spawned, once |
| run a scan on Sonnet, or Opus at `max` effort | denies: scans belong to `orch-scout`; the heavy tier is capped at `xhigh` |
| spawn workers without end | checkpoints once past half the session budget, then stops at the cap until you raise it |
| tick the verification box itself | holds the turn until a verifier has written a passing verdict file |
| end the turn with open items | holds it once and lists them |
| leave finished teammates running in tmux | reaps them |

## Install

In Claude Code:

```
/plugin marketplace add Sheldon-desouza/claude-code-orchestrator
/plugin install orchestrator@claude-code-orchestrator
```

Restart Claude Code, then run `/orch-doctor`. It needs `python3` (3.9+) on your PATH; macOS and Linux (Windows via WSL).

**Standalone skill (claude.ai, Claude Desktop, other agents):** copy [`skills/orchestrator/SKILL.md`](skills/orchestrator/SKILL.md) into your skills folder, or upload it as a skill. It carries the whole loop in prose.

## How a session runs

1. **You give the chair a job** — or type `/orchestrate <what you want>`.
2. **It asks questions, all of them, at the start.** It reads the repo first, then asks in rounds (four per message) until nothing would change the code and a worker could be briefed without guessing. It always asks one thing: does this land on the current branch or a new one?
3. **It writes the ledger** at `./.workflow/LEDGER.md`: the answers under `## Clarified`, then one checkbox per requirement, ending with `V. fresh-eyes verification passed`.
4. **It briefs and delegates.** Every spawn's first line is `Class: <class>`. The routing table picks the tier. Workers cannot ask you anything, which is why step 2 exists.
5. **Reports come back, 40 lines max.** Ledger items addressed, summary, ≤10 verbatim lines (the rest on disk with a path), confidence, and anything noticed out of scope. Longer reports are rejected and re-run.
6. **A fresh verifier checks the close** (on Sonnet; on Opus when the close is security, irreversible or architecture) and writes `.workflow/verify/LEDGER.json`. Only it ticks `V.`. Findings become new ledger items and the loop goes round again — three cycles max, then it reports what is still open.

## Commands

| Command | Does |
|---|---|
| `/orchestrate <job>` | start the loop: clarify → ledger → first wave |
| `/orch-ledger [archive]` | show the ledger and verdict; archive a finished one |
| `/orch-verify` | spawn the fresh verifier for the current close |
| `/orch-resume` | rebuild state from disk after a crash, `/clear` or compaction |
| `/orch-stats` | routing mix, denials, spawns per session (local log) |
| `/orch-doctor` | diagnose the install and print what to fix |

## Agents

Seven agents, each pinned to its tier's model with a tool allowlist, the report contract, and a **context budget**: past ~100k tokens a worker saves its progress to scratch and hands back, so the chair re-briefs a fresh one instead of paying for one worker re-reading a ballooning context every turn. The reviewer and the security agent are read-only.

| Agent | Tier | Model | For |
|---|---|---|---|
| `orch-scout` | cheap | haiku | grep, glob, fetch-to-disk, counts |
| `orch-researcher` | bulk | sonnet | briefs one source from the scout's scratch copy |
| `orch-implementer` | bulk | sonnet | code to a spec, tests, refactors |
| `orch-reviewer` | bulk | sonnet | standard review against the ledger |
| `orch-hard-slice` | heavy | opus | architecture, migrations, stubborn bugs, escalations |
| `orch-security` | heavy | opus | all security review |
| `orch-verifier` | bulk | sonnet | fresh-eyes close, writes the verdict (spawn with `model: opus` for risky closes) |

## Change the models

`config/tiers.json` is the only file that names a model:

```json
"heavy": { "model": "opus", "match": ["opus"], "fallbacks": ["fable", "sonnet"] }
```

Tiers are roles; models are interchangeable. When Opus 5.5 shipped, the `opus` alias picked it up with no change at all. Each tier also carries a `max_effort` (heavy is `xhigh` by default); the route guard denies a spawn asking for more. A new model ships → edit one line (per machine at `~/.claude/orchestrator/tiers.json`, no reinstall). The route guard reads your override; the shipped agents pin the defaults, and `/orch-doctor` tells you if they disagree.

`config/routing.json` maps task classes to tier bands. Loosen or tighten a class the same way.

## When the top model's limit runs dry

Switch the chair with `/model`. The next session start renders the **fallback profile** from the tier map: "opus holds the chair, fable rests, do not spawn fable agents." Switch back and it switches back. Pin it with `ORCH_PROFILE=chair|fallback` (or a model name).

## Configuration

All optional, under `"env"` in `~/.claude/settings.json`.

| Env var | Default | Meaning |
|---|---|---|
| `LEDGER_GUARD_THRESHOLD` | 1500 | spawn-guard gate, in chars; shorter spawns are never gated |
| `LEDGER_GUARD_CLARIFY` | on | `0` disables the clarify gate |
| `LEDGER_GUARD_TASKS` | 3 | Nth ledgerless tracker task denied once; `0` off |
| `LEDGER_GUARD_STOP_MODE` | once-per-session | `every-turn` holds every turn end |
| `ORCH_ROUTE_GUARD` | on | `0` disables class/tier routing enforcement |
| `ORCH_VERIFY_GUARD` | on | `0` disables the verdict-file valve |
| `ORCH_BUDGET` | on | `0` disables the per-session spawn budget |
| `ORCH_BUDGET_SPAWNS` | 60 | spawns per session; checkpoint past half, stop at the cap; `0` no cap |
| `ORCH_BUDGET_HEAVY` | 20 | heavy-tier (or chair-model) spawns per session, same rules |
| `ORCH_SOLO_EDITS` | 3 | the chair's Nth file edit with no worker spawned is denied once; `0` off |
| `ORCH_SOLO_GUARD` | on | `0` disables the solo guard and the naming gate |
| `ORCH_NAME_GATE` | follows agent teams | `1`/`0` force the "name your long spawns" gate on/off |
| `ORCH_REMIND` | on | `0` disables the one-line reminder on every prompt |
| `ORCH_PROFILE` | auto | pin the chair profile: `chair`, `fallback`, or a model name |
| `ORCH_CONFIG_DIR` | `~/.claude/orchestrator` | where `tiers.json` / `routing.json` overrides live |
| `ORCH_METRICS` | on | `0` disables the local metrics log |
| `ORCH_SWARM_CLEANUP` | on | `0` disables teammate reaping |
| `ORCH_TEAMMATE_IDLE_H` | 1 | reap teammate panes idle for N hours; `0` off |

**Raising the budget mid-session:** write `.workflow/BUDGET.json` in the project, e.g. `{"spawns": 100, "heavy": 30}`. It takes effect on the next spawn, no restart.

Metrics are written to `~/.claude/orchestrator/metrics.jsonl`, stay on your machine, and are never sent anywhere. `/orch-stats` shows where your spawns ran by tier, the class mix, and why the guards said no.

## The ledger, exactly

```markdown
## Clarified
- Q1: does this replace the old exporter, or run beside it? -> beside it, for one release
- Q2: is the CSV column order part of the contract? -> yes, downstream parses by position
- Branch: main, the checkout in place

- [ ] 1. Every explicit requirement, one line each
- [ ] 2. Implicit expectations and constraints too
- [x] 3. Marked done only after verification confirms it
- [~] 4. deferred: user approved postponing this
- [ ] V. fresh-eyes verification passed
```

The clarify gate reads `## Clarified` by four rules and names the one that failed: every bullet's last `?` has its `->` answer; no `Assumption:` line; at least one answered question; a `Branch:` line. A checkbox line ends the section; a template in a code fence is an example, not a record.

## Tests

```bash
pip install pytest
python3 -m pytest tests/ -q      # ~300 tests; the hooks run as real subprocesses
python3 scripts/doctor.py
```

## Limitations, honestly

- Hooks check **shape**, not fidelity: the clarify gate proves questions were answered in the documented shape, not that the right questions were asked. The route guard proves the class tag matches the tier, not that the class was chosen well.
- The solo guard counts Edit/Write calls, not work: a chair that edits through `Bash` heredocs never trips it. The per-prompt reminder is the only thing covering that path.
- The verifier can write files (it has to write the verdict). Its prompt confines it to `.workflow/verify/`; a hook does not.
- Enforcement is only as strong as the host's hook pipeline. Run `/orch-doctor` once on your setup.
- macOS and Linux. Windows users: WSL works; native Windows is untested.
- No benchmark numbers yet. An eval harness is the next milestone; until it lands, this README makes no percentage claims.

## Roadmap

- **Eval harness** with a fixed task set, run with and without the plugin, published in this README.
- **Report-contract hook**: reject over-length worker reports mechanically instead of by instruction.
- **Token-aware budget**: today the budget counts spawns; counting tokens needs usage data hooks do not receive yet.
- **Agent-teams routing** behind `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`.

The design record is in [`docs/DESIGN.md`](docs/DESIGN.md).

## Lineage and licence

MIT. Forked from [Rylaa/fable5-opus5-orchestrator](https://github.com/Rylaa/fable5-opus5-orchestrator) v0.23.0 by Yusuf Demirkoparan, whose clarify gate, ledger hooks and teammate reaping are the foundation here. v1.1 also ports the solo guard, the per-prompt reminder, the naming gate and a switch-delta fix from his later [fable5-opus5.5-orchestrator](https://github.com/Rylaa/fable5-opus5.5-orchestrator) line. Upstream has since dropped the ledger and the verifier; this project keeps the full clarify → delegate → verify loop. Full attribution in [`NOTICE`](NOTICE); the upstream commit history is preserved in this repository.

---

*Keywords: Claude Code orchestrator, Claude Code plugin, multi-agent orchestration, sub-agents, token saver, Fable 5, Opus, Sonnet, Haiku, model routing, delegation, hooks, agent teams.*

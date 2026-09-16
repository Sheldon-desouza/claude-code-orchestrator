# Orchestrator Plugin — Design Document

**Status:** implemented as v1.0.0 (Layers 1–3); Layers 4–5 are the roadmap. Kept as the design record.
**Date:** 2026-09-10
**Lineage:** hard fork of [`Rylaa/fable5-opus5-orchestrator`](https://github.com/Rylaa/fable5-opus5-orchestrator) (MIT, v0.23.0), with attribution retained.
**Goal:** a free, MIT-licensed Claude Code plugin published on GitHub, designed to be adopted by people other than its author.

---

## 1. What the upstream repo actually is

Not a toy. 5,885 lines, one squashed commit, MIT, CI on Ubuntu + macOS across Python 3.9 and 3.13. The tests are 2,845 of those lines and they run the hooks end to end as subprocesses, which is the correct way to test stdin/stdout JSON filters.

```
.claude-plugin/plugin.json      9 lines    manifest, v0.23.0
.claude-plugin/marketplace.json 15         self-hosted marketplace
hooks/hooks.json                53         4 hooks
instructions/                   195        2 chair profiles + 2 switch deltas
scripts/                        2,222      4 hooks + a stats reader
skills/                         210        playbook + clarify
tests/                          2,845      5 test files
```

### The idea in one line

The model in the chair (Fable 5.1) spends its tokens on judgment only. Volume goes to Sonnet 5, hard slices go to Opus 5, and **four hooks stop the chair from cheating**, because a rule that lives only in a prompt is a rule the model forgets under load.

### The four gates

| # | Hook | Fires on | Denies unless |
|---|------|----------|---------------|
| 1 | Clarify (PreToolUse) | spawn > 1500 chars | ledger has a real `## Clarified` block: every `?` has a `->` answer, no `Assumption:` line, at least one Q→A, a `Branch:` line |
| 2 | Spawn (PreToolUse) | spawn > 1500 chars | some `.workflow/LEDGER*.md` exists with numbered checkboxes |
| 3 | Task list (PreToolUse) | 3rd `TaskCreate` with no ledger | same (fires once per session) |
| 4 | Close (Stop) | turn ends with `- [ ]` open | items closed, deferred with approval, or acknowledged (once per session) |

### What is genuinely good and must survive the fork

1. **Enforcement over instruction.** This is the whole thesis and it is correct. Every competing plugin ships prose and hopes.
2. **The clarify gate.** Front-loading every question before the first spawn, because *workers cannot ask the user anything*, is the single highest-value idea in the repo. Ambiguity carried into a spawn prompt becomes a guess committed to code.
3. **Staleness handling.** A finished ledger from last week does not silence the gates; a `-archive.md` rename retires one. Small detail, prevents the gates rotting into no-ops.
4. **Teammate reaping.** The docstring cites 63 orphaned agents holding ~5 GB RSS measured in the wild. That is a real bug in agent teams and this plugin fixes it.
5. **Profile-switch deltas.** When the chair moves Fable→Opus mid-session, it sends a 7-line delta rather than re-injecting the 91-line core, and gates the delta to `source == "resume"` because `compact` and `clear` provably discarded the earlier injection. That is careful engineering.
6. **The markdown parsing is paranoid in the right way.** Setext headings, spaceless ATX, fenced-code examples, tab-as-four-columns, checkbox-ends-section. Reimplementing this from scratch would take days and be worse.

### What is missing, wrong, or unenforced

This is the fork's reason to exist.

| # | Gap | Why it matters |
|---|-----|----------------|
| G1 | **Ships zero `agents/`.** No subagent definitions at all. | Routing exists only as prose in a 91-line profile. The plugin's core claim — "Sonnet does volume, Opus does hard slices" — has no mechanical backing. A chair that ignores it is not stopped by anything. |
| G2 | **Ships zero `commands/`.** No slash commands. | Nothing is discoverable. A user installs it and gets... four denials. Discoverability is most of adoption. |
| G3 | **Model names are hardcoded** into filenames, env vars, metrics paths, prose. `fable`/`opus`/`sonnet` appear as literals throughout. | Directly blocks your stated requirement: "Opus 5, Opus 6, and whoever is available." A new model ships and this repo needs a release. |
| G4 | **Routing is never validated.** | Nothing checks that the security review actually went to Opus. Gate 2 checks *that* a ledger exists, never *what tier* the spawn used. |
| G5 | **`V.` verification is unenforced.** Prose says "only the verifier closes it." | The chair can type `- [x] V.` itself. The one gate protecting close quality is honour-system. |
| G6 | **The report contract is unenforced.** "≤40 lines, verbatim over 10 lines goes to scratch." | Stated in the playbook skill, checked by nothing. Report bloat is exactly what blows the chair's context. |
| G7 | **No budget governor.** The stated scarce resource is the usage limit, and nothing measures or caps it. | Anthropic measured multi-agent at ~15× the tokens of chat. A plugin whose thesis is "the limit is scarce" should count. |
| G8 | **No resume path.** `/clear`, a crash, or a compact loses the orchestration state that is already sitting on disk. | Checkpoint-and-resume is Anthropic's headline production lesson. The state is already in `.workflow/` — it just needs a reader. |
| G9 | **No evals.** | Every competitor claims "30–50% token savings" with no evidence. Whoever ships numbers wins the argument. |
| G10 | **macOS/Linux only**, `python3` required on PATH. | Excludes Windows/WSL users from a plugin that is otherwise pure stdlib. |
| G11 | **Named after Anthropic's model.** `fable5-opus5-orchestrator`, `FABLE_ORCH_*`, `fable-orchestrator`. | Two problems: it dates instantly, and it builds a public brand on a trademark you do not own. |
| G12 | **Two chairs only.** "Any other model gets the Fable profile." | Same root cause as G3. |

---

## 2. What the research says

### The economics are real but expensive

- Anthropic's own multi-agent research system: **Opus lead + Sonnet subagents beat single-agent Opus by 90.2%**, at roughly **15× the token cost of a chat turn**, and token usage alone explained **80% of the performance variance**. ([Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system))
- Crucially, that same write-up says the architecture **excels at breadth-first parallel research and struggles with coding tasks** requiring shared context and real-time coordination. This plugin is aimed squarely at coding. That is not fatal, but it is the honest framing: the wins here come from *context preservation on the chair* and *tier arbitrage*, not from parallelism magic.
- Fable 5.1 sits at **$10/M input, $50/M output, $0.25/M cached input**, 1M context, 128K max output. On a subscription the binding constraint is the usage limit, not the invoice — which is why the upstream profile is right to say "when the limit and context hygiene conflict, the limit wins." ([Anthropic docs](https://platform.claude.com/docs/en/models/fable-5-1/overview), [Artificial Analysis](https://artificialanalysis.ai/models/releases/claude-fable-5-1))

### Where multi-agent systems actually break

The MAST taxonomy (1,600+ annotated traces across 7 frameworks, 14 failure modes) splits failures three ways:

| Category | Share | Upstream coverage |
|---|---|---|
| Specification & system design | **41.8%** | Strong — this is exactly what clarify + ledger attack |
| Inter-agent misalignment | **36.9%** | **None.** No report contract enforcement, no shared-state protocol |
| Task verification | **21.3%** | Prose only (G5) |

Specification ambiguity plus unstructured coordination account for **79% of production breakdowns**. The upstream repo covers the first half properly and the second half not at all. ([Augment Code summary](https://www.augmentcode.com/guides/why-multi-agent-llm-systems-fail-and-how-to-fix-them), [Future AGI](https://futureagi.substack.com/p/why-do-multi-agent-llm-systems-fail))

Recent work also argues coordination should be a **configurable architectural layer, separable from agent logic** — centralized / decentralized / hierarchical topologies as a choice, not a hardcode. ([arXiv 2605.03310](https://arxiv.org/html/2605.03310v1), [survey](https://doi.org/10.3390/fi18060326))

### The platform moved under this repo

Claude Code now ships three native primitives: **subagents** (in-session, report to parent only), **agent teams** (separate sessions, shared task list, direct peer messaging, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, shipped Feb 2026), and **background agents**. Reusable subagent definitions can now be referenced as team members. ([alexop.dev](https://alexop.dev/posts/from-tasks-to-swarms-agent-teams-in-claude-code/), [claudefa.st](https://claudefa.st/blog/guide/agents/agent-teams))

The upstream repo half-knows this — it reaps tmux teammate panes — but its profile still reasons in subagent terms. The shared task list and mailbox are *exactly* the missing coordination layer for MAST's 36.9%.

### The competition

- **oh-my-claudecode** — 19 agents, 35+ skills, `/autopilot`, `/team N:agent`, MIT, free. Claims "30–50% lower costs", "3–5× faster". No published evidence. This is the plugin to beat on positioning.
- **claude-night-market** — 23 plugins, 186 skills, 128 commands, 54 agents, multi-LLM delegation. Kitchen sink.
- Common pattern-language is settling on six shapes: orchestrator-worker, parallel reviewers, pipeline chain, debate-and-converge, fan-out/fan-in, self-healing retry. ([The Prompt Shelf](https://thepromptshelf.dev/blog/claude-code-multi-agent-orchestration-patterns-2026/))

**The open niche:** everyone ships agent rosters and prompt libraries. Nobody ships *enforcement with published numbers*. That is the whole positioning.

---

## 3. Two corrections to the plan as stated

**"Opus 5, Opus 6, and whoever is available."** There is no Opus 6. As of today the current models are the Claude 5 family (Fable 5.1, Opus 5, Sonnet 5) plus Haiku 4.5. The right response is not to guess at future names — it is to stop hardcoding names at all, which is item G3 and the single biggest architectural change in this design. When Opus 6 does ship you edit one JSON file, or the plugin picks it up automatically.

**"Sub-agents using lower models."** Worth being precise about what "lower" buys. Fable 5.1 in the chair at $10/$50 is the most expensive token in the stack, so the arbitrage is real — but only if the chair's tokens genuinely go to judgment. If the chair reads three 2,000-line files itself, the routing saved nothing. That is why the budget governor (G7) is in scope: it is the only way to know whether the thesis is working on your machine.

---

## 4. The design

Five layers. Layers 1–2 are upstream, kept. Layers 3–5 are the fork's contribution.

```
┌─ 5  Observability ──── metrics, /orch-stats, eval harness, published benchmarks
├─ 4  Coordination ───── report contract, shared state, resume, budget governor
├─ 3  Routing ────────── tiers.json, agents/, routing table, route validation hook
├─ 2  Discipline ─────── clarify gate, ledger, verification valve   [upstream, kept]
└─ 1  Injection ──────── SessionStart profile, switch deltas         [upstream, kept]
```

### Layer 3 — Routing becomes data (fixes G1, G3, G4, G12)

Replace the two hardcoded chair profiles with a **tier map** the user owns:

```jsonc
// tiers.json — the only file that knows a model's name
{
  "chair":  { "model": "fable",  "fallbacks": ["opus", "sonnet"] },
  "heavy":  { "model": "opus",   "fallbacks": ["fable"] },
  "bulk":   { "model": "sonnet", "fallbacks": ["opus"] },
  "cheap":  { "model": "haiku",  "fallbacks": ["sonnet"] }
}
```

Then a **routing table**, also data, mapping task class → tier + effort + isolation:

| Task class | Tier | Effort | Isolation |
|---|---|---|---|
| scan, fetch, grep, mechanical edit | bulk | low | shared |
| spec code, tests, briefs, standard review | bulk | medium–high | worktree if editing |
| architecture, migration, stubborn debugging | heavy | max | worktree |
| **security review** | heavy | max | shared, read-only |
| fresh-eyes verification | heavy | high–max | shared, read-only |
| arbitration, escalation ceiling | chair | — | — |

Three things follow from making this data rather than prose:

1. **`agents/` definitions are generated from it.** The plugin ships real subagent definitions — `orch-researcher`, `orch-implementer`, `orch-hard-slice`, `orch-verifier`, `orch-security` — each with its tier's model pinned and a tool allowlist. Verifier and security agents get read-only tools, so a verifier *structurally cannot* fix what it is meant to find. That closes half of G5 with a file permission rather than a sentence.
2. **A new PreToolUse hook validates the route.** Spawn a security review on `bulk` and it is denied, naming the table row. This is gate 2's missing half: it currently checks that a ledger exists, never what tier the work went to.
3. **Model churn stops being a release.** New model, one line. Missing model, fallback chain. Unknown chair, the map's `chair` entry wins instead of "anything else gets the Fable profile."

The profile injection then becomes one template rendered against the tier map, which also kills the fable/opus file duplication (two nearly identical 90-line files that must be edited in lockstep today).

### Layer 4 — Coordination (fixes G5, G6, G7, G8; targets MAST's 36.9% + 21.3%)

**Report contract enforcement.** The 5-part, ≤40-line contract exists in the playbook skill and is checked by nothing. Add a `SubagentStop`-side validator: over-length reports, or reports missing the confidence field, are rejected and re-run rather than silently accepted. This is the cheapest available win against inter-agent misalignment, and it directly protects the chair's context, which is the whole point of the plugin.

**Verification valve, actually valved.** `- [x] V.` is only accepted when a matching verdict artifact exists in `.workflow/verify/<ledger>-<n>.json`, written by an agent whose definition is one of the read-only verifier types. The Stop hook checks for it. Prose becomes a file check.

**Budget governor.** Every spawn already emits a metrics line; extend it with tier, effort, task class, duration, outcome and escalation. Then a soft cap: at N spawns or an estimated token ceiling in a session, the chair gets a warning injected; at the hard cap, spawns are denied until the user raises it. Given the 15× multiplier this is the feature that makes the "the limit is the scarce resource" claim operational instead of decorative.

**Resume.** `/orch-resume` reconstructs orchestration state from `.workflow/` — the ledger, the open items, the verify verdicts, the scratch index — after a crash, a compact, or a `/clear`. The state is already on disk. Nobody reads it back. This is a day of work for a feature that reads like magic in a demo.

**Agent-teams awareness (opt-in).** When `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, route multi-worker phases through the shared task list and mailbox rather than fire-and-forget subagents, so peers can reconcile instead of duplicating. Keep it behind the flag; it is experimental upstream of us.

### Layer 5 — Observability and evidence (fixes G9)

**`/orch-stats`** — routing mix, escalation rate, clarify-miss rate, denial counts by gate, spawns per session, estimated tokens by tier. Rendered as a terminal table, with an `--html` flag that writes a small report.

**An eval harness.** Anthropic's guidance is to start with ~20 representative cases and an LLM-as-judge rubric. Ship exactly that: a fixed task set, run with the plugin and without, publish tokens-to-completion, wall-clock, and a quality score. Claude Code's own `claude plugin eval` is the vehicle.

This is the differentiator. oh-my-claudecode claims 30–50% savings with nothing behind it. A README with a reproducible table and the harness in-repo is the thing that gets linked, argued about, and starred. It also constrains us honestly: if the numbers come out at 12%, the README says 12%.

---

## 5. Repo layout

```
orchestrator-plugin/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── agents/                    NEW — generated from tiers.json
│   ├── orch-researcher.md
│   ├── orch-implementer.md
│   ├── orch-hard-slice.md
│   ├── orch-verifier.md       read-only tools
│   └── orch-security.md       read-only tools
├── commands/                  NEW
│   ├── orchestrate.md         start a job: clarify → ledger → first wave
│   ├── ledger.md              show / edit / archive
│   ├── verify.md              spawn a fresh verifier, write the verdict
│   ├── resume.md              rebuild state from .workflow/
│   ├── stats.md               routing + budget report
│   └── doctor.md              diagnose hooks, python, tmux, tier map
├── config/
│   ├── tiers.json             NEW — the only file naming a model
│   └── routing.json           NEW — task class → tier/effort/isolation
├── hooks/hooks.json
├── instructions/
│   └── profile.md.tmpl        one template, rendered per tier map
├── scripts/
│   ├── inject_instructions.py      kept, de-hardcoded
│   ├── ledger_guard_spawn.py       kept, + route validation
│   ├── ledger_guard_stop.py        kept, + verify-artifact check
│   ├── report_contract.py          NEW
│   ├── budget_governor.py          NEW
│   ├── cleanup_session_cache.py    kept
│   └── stats.py                    extended
├── skills/
│   ├── clarify/SKILL.md            kept, near-verbatim
│   ├── playbook/SKILL.md           kept, rewritten for the tier map
│   └── routing/SKILL.md            NEW
├── evals/                     NEW — 20 cases + judge rubric
├── tests/                     kept + extended
├── LICENSE                    MIT, both copyright lines
├── NOTICE                     attribution
└── README.md
```

Python stdlib only, no dependencies, 3.9+, tested on Ubuntu + macOS + Windows.

---

## 6. Redistribution — what you may and must do

The upstream is **MIT, Copyright (c) 2026 Yusuf Demirkoparan**. MIT is one of the most permissive licences there is, and it explicitly grants the rights to *use, copy, modify, merge, publish, distribute, sublicense, and sell*. So:

**You may:** fork it, rename it, rewrite any part of it, host it on your own GitHub account, publish it to your own marketplace, and charge for it if you ever wanted to. No permission needed, no notification, no share-alike obligation. Your additions are yours.

**You must** — this is the entire obligation, one sentence in the licence — include the original copyright notice and the MIT permission text in all copies or substantial portions. Concretely:

1. **`LICENSE`** keeps his line and adds yours:
   ```
   MIT License

   Copyright (c) 2026 Yusuf Demirkoparan
   Copyright (c) 2026 <your name>
   ```
   The permission and warranty paragraphs stay exactly as they are.
2. **`NOTICE`** — not required by MIT, but it is the honest thing and it costs nothing: name the upstream repo, the commit you forked from, the licence, and what you changed.
3. **README** — a "Lineage" line near the top: forked from `Rylaa/fable5-opus5-orchestrator`, MIT, with a link. In practice this earns goodwill rather than costing anything; forks that hide their origin get called out, and that is the one kind of GitHub attention you do not want.
4. **GitHub fork vs. fresh repo.** Use a *fresh repo* with the history imported, not GitHub's fork button. Forks don't show up in search, can't be starred as effectively, and the star count reads as belonging to the parent. Import the upstream commit so the lineage is in the git history, then build on top.

**What you must not do:** imply endorsement by the original author, or strip the copyright line. That is the whole list.

**One more, unrelated to the licence:** do not name the plugin after an Anthropic model. `fable5-opus5-orchestrator` bakes in a model name you don't own and a version number that dates in weeks. Pick a name that describes the *behaviour*, not the models — the tier map means the plugin no longer cares which models exist.

---

## 7. Getting stars

Stars follow from three things, in this order: it solves a felt problem, the README proves it in thirty seconds, and it is trivial to try.

1. **A benchmark table above the fold.** Reproducible, with the harness in-repo. This is the thing nobody else has.
2. **A 20-second asciinema** of a gate firing — the chair tries to spawn, gets denied, writes the ledger, proceeds. The denial *is* the product; show it.
3. **Two-line install**, and `/orch-doctor` as the first thing the README tells you to run.
4. **A comparison table** against oh-my-claudecode and claude-night-market that is fair, including where they win (bigger agent rosters, more commands). Fairness is what makes the table quotable.
5. **Honest limits section**, inherited from upstream, which already does this well: hooks check shape not fidelity; enforcement is only as strong as the host's hook pipeline.
6. **Distribution:** submit to the awesome-claude-code lists, the plugin marketplaces, and post once to r/ClaudeAI and HN with the benchmark as the hook, not the feature list.
7. **`good first issue` labels** on day one. Contributors star.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Hook APIs change under us | Pure stdlib, defensive parsing, `/orch-doctor`, CI on multiple Python versions |
| Deny-based UX annoys users into uninstalling | Every deny names the rule and the fix; a documented escape hatch; every gate individually disableable by env var |
| Evals show a small win | Publish it anyway. A credible small number beats an incredible large one, and it is still the only number in the category |
| Upstream keeps shipping and we diverge | Track upstream, cherry-pick, credit in NOTICE |
| Agent teams remain experimental | Keep behind the env flag; degrade to subagents |
| Maintenance burden of a public repo | Scope discipline: this is an enforcement layer, not another 186-skill kitchen sink |

---

## 9. Open questions for you

1. **Name.** It should describe the behaviour, not the models. I'd want to shortlist rather than pick one unilaterally.
2. **Scope of v0.1.** My recommendation: Layers 1–3 only (fork + tier map + agents + route validation + commands + doctor). Ship that, then add Layer 4 in 0.2 and the evals in 0.3. Shipping all five before the first release delays it by weeks and the evals are worth more once real users have run it.
3. **Non-Claude workers.** "Whoever is available" could extend to Codex or Gemini CLIs as bulk workers. I'd keep it out of core and behind an adapter, but say if you want it in v1.
4. **Windows.** Adds test surface for tmux-adjacent code. Worth it, or macOS/Linux like upstream?

---

## Sources

- [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Claude Fable 5.1 — Claude Platform Docs](https://platform.claude.com/docs/en/models/fable-5-1/overview)
- [Artificial Analysis — Claude Fable 5.1](https://artificialanalysis.ai/models/releases/claude-fable-5-1)
- [Augment Code — Why multi-agent LLM systems fail (MAST)](https://www.augmentcode.com/guides/why-multi-agent-llm-systems-fail-and-how-to-fix-them)
- [Future AGI — Why do multi-agent LLM systems fail](https://futureagi.substack.com/p/why-do-multi-agent-llm-systems-fail)
- [Coordination as an Architectural Layer for LLM-Based Multi-Agent Systems](https://arxiv.org/html/2605.03310v1)
- [LLM-Based Multi-Agent Orchestration: A Survey](https://doi.org/10.3390/fi18060326)
- [The Prompt Shelf — Claude Code multi-agent orchestration: 6 patterns](https://thepromptshelf.dev/blog/claude-code-multi-agent-orchestration-patterns-2026/)
- [alexop.dev — Agent teams in Claude Code](https://alexop.dev/posts/from-tasks-to-swarms-agent-teams-in-claude-code/)
- [claudefa.st — Claude Code agent teams](https://claudefa.st/blog/guide/agents/agent-teams)
- [oh-my-claudecode](https://ohmyclaudecode.com/)
- [athola/claude-night-market](https://github.com/athola/claude-night-market)
- [Rylaa/fable5-opus5-orchestrator](https://github.com/Rylaa/fable5-opus5-orchestrator)

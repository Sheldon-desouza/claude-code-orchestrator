# Changelog

## 1.1.0 — 2026-09-28

Driven by real usage: one 17-hour session with Fable in the chair spent 66% on Opus, 21% on Sonnet, 0% on Haiku, and read 1.1B cached tokens, 79% of it above 150k context. The chair discipline held (Fable was 14%); the workers were the cost.

### Behaviour changes (read before upgrading)
- **Verification runs on Sonnet by default.** `orch-verifier` now pins the bulk tier; pass `model: opus` for security, irreversible or architecture closes. Measured: 80 of 168 heavy-tier spawns were verifiers.
- **Scans are cheap-tier only.** `Class: scan` must run on `orch-scout` (Haiku). Measured: 11 of 16 scans ran on Sonnet.
- **Opus is capped at `xhigh` effort.** `hard` and `security` default to `xhigh`; a spawn asking the heavy tier for `max` is denied. Per tier via `max_effort` in `tiers.json`.
- **Five hook events** instead of four: `UserPromptSubmit` is new.

### Added
- **Budget governor** (spawn hook): counts every allowed spawn per session, and heavy-tier ones separately. One checkpoint deny past half a cap, then a hard stop at the cap until the user raises it in `.workflow/BUDGET.json`. Defaults 60 spawns / 20 heavy. `ORCH_BUDGET`, `ORCH_BUDGET_SPAWNS`, `ORCH_BUDGET_HEAVY`.
- **Worker context budget** in all seven agents: past ~100k tokens a worker writes progress to scratch and hands back `uncertain because context budget`.
- **Solo guard** (new PreToolUse hook, ported from upstream v0.16.0): the chair's 3rd Edit/Write in a session with no worker spawned is denied once. Forks do not count as delegating. `ORCH_SOLO_EDITS`, `ORCH_SOLO_GUARD`.
- **Naming gate** (ported from upstream v0.16.1): a long unnamed spawn is denied once, so it runs in a visible pane. On only when agent teams are on, or `ORCH_NAME_GATE=1`.
- **Per-prompt reminder** (new UserPromptSubmit hook, ported from upstream v0.16.0): one ~40-token line on every prompt. `ORCH_REMIND=0` disables it.
- **`/orch-stats`** now shows where spawns ran by tier with a warning when heavy + chair pass 35% or cheap never runs, the class/tier mix, route denials by reason, solo and budget events.
- Research pipeline: the scout fetches every source to scratch in one batched call; researchers brief the disk copy.

### Fixed
- **Profile-switch delta only on authoritative evidence** (ported from upstream v0.15.1): a `/model` change in another session moved the global settings default, and the next null-payload resume told a Fable chair its limit was spent. The delta now needs the payload model or `ORCH_PROFILE`. A fire that delivers nothing clears the recorded profile outside `resume`, and the marker is still written when the template is unreadable.

### Not ported, on purpose
- Upstream v0.16.0 removed the Requirements Ledger, the clarify gate and the fresh-eyes verifier. This project keeps them: the loop of clarify, delegate, verify is the product.

## 1.0.0 — 2026-09-16

First release of Claude Code Orchestrator, forked from
[Rylaa/fable5-opus5-orchestrator](https://github.com/Rylaa/fable5-opus5-orchestrator) v0.23.0 (MIT).

### Added
- **Tier map** (`config/tiers.json`): the only file that names a model. `chair` / `heavy` / `bulk` / `cheap` with match patterns and fallback chains; per-machine override at `~/.claude/orchestrator/tiers.json`.
- **Routing table** (`config/routing.json`): task class → tier band, effort, isolation, agent.
- **Route guard**: a spawn over the threshold must carry `Class: <class>` on its first line; the hook denies a spawn below its class's tier, above its ceiling (the top model doing volume), untagged, unknown, or `chair-only`.
- **Verify valve**: a ticked `V.` needs a passing verdict at `.workflow/verify/<ledger>.json`, written by the verifier.
- **Seven agents**: `orch-scout`, `orch-researcher`, `orch-implementer`, `orch-reviewer`, `orch-hard-slice`, `orch-security`, `orch-verifier`, each pinned to its tier's model with a tool allowlist and the report contract baked in.
- **Six commands**: `/orchestrate`, `/orch-ledger`, `/orch-verify`, `/orch-resume`, `/orch-stats`, `/orch-doctor`.
- **Standalone skill** (`skills/orchestrator/SKILL.md`) for claude.ai and any surface that reads skills, no hooks required.
- **Doctor** (`scripts/doctor.py`): diagnoses Python, manifests, hooks, tier map, agents, commands, skills, tmux, metrics, and the current `.workflow/` state.
- Tests for all of the above (69 new, on top of the 232 inherited).

### Changed
- One profile template rendered from the tier map replaces two hardcoded fable/opus profiles.
- Any non-chair tier holding the chair (opus, sonnet, haiku) gets the fallback profile; an unknown model gets the chair profile.
- `FABLE_ORCH_*` env vars are now `ORCH_*`; metrics live at `~/.claude/orchestrator/`; session markers are `orch-*.json`.
- Haiku is no longer banned: it is the `cheap` tier for `scan`-class work.

### Kept
- The clarify gate, the ledger gates, the Stop-hook cadence, teammate reaping, the profile-switch delta, and the full upstream test suite.

# Changelog

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

# Contributing

Thanks for looking. This plugin is small on purpose: an enforcement
layer, not a kitchen sink. Contributions that keep it that way are the
ones most likely to land.

## Run the tests

```bash
pip install pytest
python3 -m pytest tests/ -q
python3 scripts/doctor.py
```

The hooks are stdin/stdout JSON filters, and the tests run them end to
end as subprocesses, exactly as Claude Code does. A change to a hook
without a test that pins its behaviour will be asked for one.

## Where things live

| Want to change | Edit |
|---|---|
| which model a tier uses | `config/tiers.json` (and the matching `model:` line in `agents/*.md`; `scripts/doctor.py` tells you if they disagree) |
| which tier a task class needs | `config/routing.json` |
| what the chair is told at session start | `instructions/profile.md.tmpl` (rendered from the tier map; size-pinned by the tests) |
| the full delegation contract | `skills/playbook/SKILL.md` |
| the question protocol | `skills/clarify/SKILL.md` |
| the no-hooks version for claude.ai | `skills/orchestrator/SKILL.md` |
| a gate | `scripts/ledger_guard_spawn.py` (clarify, ledger, task-list, route) or `scripts/ledger_guard_stop.py` (close, verify valve) |

## Rules of the road

- **Never a dated model id** outside `config/tiers.json`. A test fails if one appears in the prose, the agents, the commands, or the scripts.
- **Hooks fail open.** A hook that cannot resolve something passes the call and records a metric. A config typo must never block a user's work.
- **Every deny names the fix.** If a gate says no, its message says exactly what to do next.
- **Keep the chair's injection small.** The core profile is pinned under 5.5k chars because it is prepended to every session.
- **No personal data, ever.** No real names, emails, paths, client names or keys in fixtures, docs or tests. CI greps for the obvious ones.

## Reporting a problem

Open an issue with the hook's deny text (or the missing deny), the
ledger, and the output of `python3 scripts/doctor.py`. Metrics at
`~/.claude/orchestrator/metrics.jsonl` are local and yours; paste the
relevant lines if they help.

## Licence

MIT. By contributing you agree your contribution is licensed the same
way. Upstream attribution lives in `NOTICE` and stays.

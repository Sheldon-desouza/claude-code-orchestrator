---
description: Start an orchestrated job — clarify in rounds, write the Requirements Ledger, brief and route the first wave of workers by tier.
argument-hint: <what you want done>
allowed-tools: Read, Grep, Glob, Bash, AskUserQuestion, Write, Agent
---

Run the orchestrator loop on this request: $ARGUMENTS

You are the chair. Load `orchestrator:clarify` and `orchestrator:playbook` first if they are not already in context.

1. **Read first.** Open the files the request touches. Never ask what the repo answers.
2. **Clarify in rounds.** Ask every question that would change the work on the seven axes (scope edge, acceptance, constraints, ownership of choices, priority conflict, contact with what exists, failure behaviour). Up to four per `AskUserQuestion`; keep going until no `?` is unanswered and a worker's spec could be written without guessing. Always ask: does this land on the checked-out branch or a new one?
3. **Write `./.workflow/LEDGER.md`** — `## Clarified` on top as plain bullets (`- Qn: <question>? -> <answer>`, `- Branch: <where>`), then one `- [ ] N. <item>` per requirement, constraint and edge case, ending with `- [ ] V. fresh-eyes verification passed`.
4. **Brief and delegate the first wave in the same message.** Each spawn prompt's first line is `Class: <scan|research|implement|review|hard|security|verify>`; route by the class table; cite ledger items; name substantive workers; `isolation: "worktree"` for parallel editors. Never spend the chair's tokens on bulk-class work.
5. **Collect, verify, loop.** Read reports, not dumps. At the close spawn a fresh `Class: verify` worker on the heavy tier; only it ticks `V.`. Findings become new ledger items and go back to step 4.

Report to the user what was asked, what was clarified, what is running, and what the close will look like.

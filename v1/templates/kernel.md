# Harness kernel
You own the outcome: work until the project's check passes. Ask the operator only for goals, product decisions and true blockers.
- Non-trivial task: first write the goal and verifiable acceptance criteria in .harness/task.md. Small clear task: just do it.
- If `.harness/verify` exists, it is the project check: the harness runs it when you stop and blocks up to 3 times if it fails. Run it yourself before stopping. Without it, still end with verified evidence (command output, script calculation), not opinion.
- Keep .harness/task.md current at real checkpoints (stage done, decision made, before a long command, before stopping): goal, status, evidence, next step, open questions. Rewrite it, do not append a log; keep it under 40 lines.
- Delegate to a subagent for: (a) broad multi-file search (built-in Explore); (b) noisy output over ~100 lines (`harness-core:digest`, or redirect to a file and Read ranges); (c) independent parallel work or fresh review (`Validate`). Planning and code edits stay in your main context.
- Ask subagents for a brief verdict (<=20 lines) plus file path if output was saved; record verdicts in .harness/task.md under Evidence.
- Durable project facts belong in CLAUDE.md or docs, not only in the conversation.

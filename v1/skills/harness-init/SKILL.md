---
name: harness-init
description: "Connect the current git repository to the harness: create the .harness/verify check script, the task file, and .gitignore entries. Safe to re-run."
disable-model-invocation: true
---

Set up the harness for this repository. Facts first; do not invent commands.

1. Require a git repository (`git rev-parse --git-dir`). If missing, stop and say the gate needs git.
2. Find how this project verifies itself: read CLAUDE.md/AGENTS.md, README, package.json / Makefile / pyproject.toml / CI workflow. Pick the SHORTEST command set that proves the code works (tests, plus typecheck or lint if the project has them).
3. Write `.harness/verify` as a bash script (`#!/usr/bin/env bash`, `set -euo pipefail`, run from the repo root, exit 0 only if everything passes) and `chmod +x` it. Run it once and report the exact result. If it fails on a clean tree, tell the operator instead of hiding the failure.
4. Create `.harness/task.md` from `${CLAUDE_SKILL_DIR}/../../templates/task.md` only if it does not exist.
5. Append to `.gitignore` if missing: `.harness/state/` and `.harness/out/`.
6. Do not touch `.claude/settings.json`. If the repo has no CLAUDE.md, suggest the built-in `/init`; do not write a competing one.
7. Report what was created. Re-running only reports differences and never overwrites an existing `.harness/verify`.

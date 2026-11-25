# harness-core 1.0

Minimal harness for Claude Code. Two hooks, one subagent, one skill. Everything else is native Claude Code.

- **SessionStart** (startup, resume, clear, compact, fork): prints the kernel, `.harness/task.md` and live state as context.
- **Stop**: runs `.harness/verify` (a script you own; exit 0 = pass). While it fails, the stop is blocked, at most 3 times in a row.
- **digest** subagent: runs noisy commands in an isolated context.
- **/harness-core:harness-init**: creates `.harness/verify`, the task file and `.gitignore` entries.

Install: `claude plugin install` from your marketplace, or `claude --plugin-dir /path/to/harness-core`.
Requires git and python3. Verified on Claude Code 2.1.311: unit tests, `claude plugin validate`, live E2E (`tests/e2e/run.sh`) incl. SessionStart on startup, resume, compact. Kill switch: `HARNESS_GATE=0`. Tests: `python3 -m unittest discover -s tests`.
Local model server: see `examples/local-server.settings.example.json` and pass it with `--settings`.

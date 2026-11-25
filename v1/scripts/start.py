#!/usr/bin/env python3
"""SessionStart hook (every source, compact included). Plain stdout becomes context for Claude (documented).
Prints: kernel + task file + live state. Never raises."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import git, load_state, project_root, save_state, tree_id  # noqa: E402

for _stream in (sys.stdin, sys.stdout):  # Claude Code speaks UTF-8 on hook stdio, whatever the locale
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_MAX = 4000  # hooks' own cap is 10,000 chars; stay far below it


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def age(secs):
    s = int(max(0, secs))
    return "%ds" % s if s < 90 else "%dm" % (s // 60) if s < 5400 else "%dh" % (s // 3600) if s < 172800 else "%dd" % (s // 86400)


def last_gate(root):
    lines = (read(os.path.join(root, ".harness", "state", "gate.jsonl")) or "").splitlines()
    for line in reversed(lines):
        try:
            r = json.loads(line)
            return "%s %s ago" % (r["result"], age(time.time() - r["ts"]))
        except (ValueError, KeyError, TypeError):
            continue
    return "none yet"


def main():
    try:
        payload = json.load(sys.stdin)
        payload = payload if isinstance(payload, dict) else {}
    except Exception:
        payload = {}
    root = project_root(payload)
    out = []
    kernel = read(os.path.join(PLUGIN_ROOT, "templates", "kernel.md"))
    if kernel:
        out.append(kernel.strip())
    task = read(os.path.join(root, ".harness", "task.md"))
    if task is not None:
        if len(task) > TASK_MAX:
            task = task[:TASK_MAX] + "\n[truncated: Read .harness/task.md for the rest]"
        out.append("--- .harness/task.md ---\n" + task.strip())
    branch = (git(root, "symbolic-ref", "--short", "HEAD")
              or git(root, "rev-parse", "--abbrev-ref", "HEAD")
              or b"no-git").decode("utf-8", "replace").strip()
    dirty = len((git(root, "status", "--porcelain", "--", ".", ":(exclude).harness") or b"").splitlines())
    verify_path = os.path.join(root, ".harness", "verify")
    if not os.path.isfile(verify_path):
        gate_desc = "OFF (no .harness/verify; run /harness-core:harness-init)"
    elif not os.access(verify_path, os.X_OK):
        gate_desc = "OFF (.harness/verify is not executable: chmod +x)"
    else:
        gate_desc = ".harness/verify"
    out.append("--- state ---\nbranch=%s dirty_files=%d source=%s\nverify gate: %s; last gate result: %s"
               % (branch, dirty, payload.get("source", "?"), gate_desc, last_gate(root)))
    print("\n\n".join(out))
    sess, tree = payload.get("session_id"), tree_id(root)
    if sess and tree:  # tree at session start: the gate skips a session that changed nothing
        st = load_state(root)
        base = st.setdefault("base", {})
        if sess not in base:
            base[sess] = tree
            save_state(root, st)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)

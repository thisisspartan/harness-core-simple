#!/usr/bin/env python3
"""Stop hook. Runs .harness/verify; while it fails, blocks the stop (at most MAX_BLOCKS times in a row).
No verify script, no git, or HARNESS_GATE=0 -> silent no-op. Never raises: a broken gate must not break the session."""
import json
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import load_state, log, project_root, save_state, tree_id  # noqa: E402

for _stream in (sys.stdin, sys.stdout):  # Claude Code speaks UTF-8 on hook stdio, whatever the locale
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")
MAX_BLOCKS = 3
try:
    TIMEOUT = max(1, min(580, int(os.environ.get("HARNESS_VERIFY_TIMEOUT", "540"))))  # must stay below the hook timeout (600)
except ValueError:
    TIMEOUT = 540
TAIL_LINES = 40
TAIL_CHARS = 4000


def run_verify(root, path):
    """-> (exit_code | None on timeout, last output lines). Output goes to a file, so a background process
    that inherited it cannot delay us. On timeout the whole process group is killed."""
    out = os.path.join(root, ".harness", "state", "verify.out")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        p = subprocess.Popen([path], cwd=root, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT,
                             start_new_session=True)
        try:
            rc = p.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            rc = None
    with open(out, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - 65536))
        data = f.read().decode("utf-8", "replace")
    tail = "\n".join(data.splitlines()[-TAIL_LINES:])
    if len(tail) > TAIL_CHARS:
        tail = "...[truncated]\n" + tail[-TAIL_CHARS:]
    return rc, tail


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return
    except Exception:
        return
    if os.environ.get("HARNESS_GATE") == "0":
        return
    root, sess = project_root(payload), payload.get("session_id") or "?"
    verify = os.path.join(root, ".harness", "verify")
    if not os.path.isfile(verify):
        return
    if not os.access(verify, os.X_OK):
        print(json.dumps({"systemMessage": "harness gate off: .harness/verify is not executable (chmod +x)"}))
        return
    tree = tree_id(root)
    if tree is None:
        return
    st = load_state(root)
    if tree == st.get("pass") or tree == st.get("base", {}).get(sess):
        return  # already verified, or nothing changed in this session: do not re-run
    t0 = time.time()
    rc, tail = run_verify(root, verify)
    secs = round(time.time() - t0, 1)
    fails = st.setdefault("fails", {})
    if rc == 0:
        st["pass"] = tree_id(root) or tree  # AFTER the run: verify may itself create files (build artifacts)
        fails.pop(sess, None)
        log(root, {"session": sess, "result": "PASS", "secs": secs})
        save_state(root, st)
        return
    n = fails.get(sess, 0) + 1
    why = "timed out after %ds" % TIMEOUT if rc is None else "exited %d" % rc
    if n > MAX_BLOCKS:
        fails.pop(sess, None)
        st.setdefault("base", {})[sess] = tree_id(root) or tree  # no new edits -> no more blocking this session
        log(root, {"session": sess, "result": "GAVE_UP", "rc": rc, "secs": secs})
        save_state(root, st)
        print(json.dumps({"systemMessage": "harness gate gave up: .harness/verify still failing after %d attempts" % MAX_BLOCKS}))
        return
    fails[sess] = n
    log(root, {"session": sess, "result": "FAIL", "rc": rc, "secs": secs, "attempt": n})
    save_state(root, st)
    print(json.dumps({"decision": "block",
                      "reason": ".harness/verify %s (attempt %d/%d). Last %d lines:\n%s" % (why, n, MAX_BLOCKS, TAIL_LINES, tail)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print("harness gate error: %s: %s" % (type(e).__name__, e), file=sys.stderr)
    sys.exit(0)

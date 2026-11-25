"""Shared helpers: project root, tree identity, small JSON state file."""
import hashlib
import json
import os
import subprocess
import time

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's empty tree: lets a repo without commits work


def project_root(payload):
    return os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()


def git(root, *args):
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def tree_id(root):
    """Cheap identity of the working tree, used ONLY to skip a redundant run.
    Hashes HEAD commit + changed tracked/untracked files (by mode+size+mtime, no diff generated);
    submodules are fingerprinted recursively. .harness/ is excluded. None = not a git repo."""
    if git(root, "rev-parse", "--git-dir") is None:
        return None
    head_sha = git(root, "rev-parse", "-q", "--verify", "HEAD")
    base = "HEAD" if head_sha is not None else EMPTY_TREE
    tracked = git(root, "diff", base, "--relative", "--name-only", "-z", "--", ".", ":(exclude).harness")
    untracked = git(root, "ls-files", "-o", "--exclude-standard", "-z")
    if tracked is None or untracked is None:
        return None
    h = hashlib.sha1((head_sha or b"no-head").strip() + b"\0")
    for f in sorted(set(tracked.split(b"\0")) | set(untracked.split(b"\0"))):
        if not f or f == b".harness" or f.startswith(b".harness/"):
            continue
        path = os.path.join(root, os.fsdecode(f))
        if os.path.isdir(path) and not os.path.islink(path):  # a submodule work tree
            h.update(f + b"\0" + (tree_id(path) or "-").encode() + b"\0")
            continue
        try:
            st = os.lstat(path)
            h.update(f + b"\0%d:%d:%d\0" % (st.st_mode, st.st_size, st.st_mtime_ns))
        except OSError:
            h.update(f + b"\0gone\0")
    return h.hexdigest()


def state_path(root):
    return os.path.join(root, ".harness", "state", "gate.json")


def load_state(root):
    try:
        with open(state_path(root), encoding="utf-8") as f:
            s = json.load(f)
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(root, state):
    for key in ("base", "fails"):
        m = state.get(key)
        if isinstance(m, dict) and len(m) > 50:
            for k in list(m)[:-50]:
                del m[k]
    p = state_path(root)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, p)
    except OSError:
        pass


def log(root, rec):
    try:
        d = os.path.join(root, ".harness", "state")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "gate.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(rec, ts=time.time())) + "\n")
    except OSError:
        pass

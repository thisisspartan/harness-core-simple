#!/usr/bin/env python3
"""PreToolUse loop guard: blocks 8 identical calls or 3 alternating A-B cycles in a row."""
import hashlib, json, os, re, sys, tempfile

if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

SAME_N = 8
PAIR_CYCLES = 3  # A,B,A,B,A,B
CAP = max(SAME_N, PAIR_CYCLES * 2)  # history must be long enough for the same-loop window

try:
    d = json.load(sys.stdin)
    name = d.get("tool_name") or ""
    inp = d.get("tool_input") or {}
    if name == "Bash":
        payload = (inp.get("command") or "").strip()
        if not payload:
            sys.exit(0)
    else:
        payload = json.dumps(inp, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha256((name + "\0" + payload).encode("utf-8")).hexdigest()
    sid = re.sub(r"[^a-zA-Z0-9_-]", "_", str(d.get("session_id") or "nosess"))
    aid = re.sub(r"[^a-zA-Z0-9_-]", "_", str(d.get("agent_id") or "main"))
except Exception:
    sys.exit(0)

path = os.path.join(tempfile.gettempdir(), "claude-loop-guard", f"{sid}__{aid}.json")
hist = []
try:
    with open(path, encoding="utf-8") as f:
        old = json.load(f)
        if isinstance(old, list):
            hist = old[-CAP:]
except (OSError, ValueError):
    pass

cand = (hist + [h])[-CAP:]
same_loop = len(cand) >= SAME_N and len(set(cand[-SAME_N:])) == 1
ab_len = PAIR_CYCLES * 2
ab_loop = (len(cand) >= ab_len and cand[-2] != cand[-1]
           and cand[-ab_len:] == cand[-2:] * PAIR_CYCLES)

if same_loop or ab_loop:
    kind = f"{SAME_N} identical calls" if same_loop else f"{PAIR_CYCLES} alternating A-B cycles"
    sys.stderr.write(
        f"Loop guard blocked {name} ({kind} in a row). "
        "Stop repeating: use the output you already got, change approach, or ask the operator.\n"
    )
    sys.exit(2)

try:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cand, f)
    os.replace(tmp, path)
except OSError:
    pass
sys.exit(0)

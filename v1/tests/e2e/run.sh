#!/usr/bin/env bash
# Live E2E: the REAL `claude` binary + this plugin against a fake API. No model, no network, ~15 s.
# Needs `claude` on PATH. Scenarios: red verify (3 blocks, then gave up) and green verify (pass, context delivered).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; PLUGIN="$(cd "$HERE/../.." && pwd)"
PORT="${PORT:-18099}"; W="$(mktemp -d)"; MOCK=""
trap '[ -n "$MOCK" ] && kill "$MOCK" 2>/dev/null; rm -rf "$W"' EXIT
python3 "$HERE/mock_api.py" "$PORT" "$W/requests.jsonl" & MOCK=$!
sleep 1
export HOME="$W/home" ANTHROPIC_BASE_URL="http://127.0.0.1:$PORT" ANTHROPIC_API_KEY=dummy ANTHROPIC_MODEL=mock \
       CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_AUTOUPDATER=1
mkdir -p "$HOME"

scenario() {  # $1 = body of .harness/verify
    rm -rf "$W/p" && mkdir -p "$W/p/.harness" && : > "$W/requests.jsonl"
    ( cd "$W/p" && git init -q && git config user.email t@t && git config user.name t \
      && echo base > base.txt && git add -A && git commit -qm init )
    printf '#!/usr/bin/env bash\n%s\n' "$1" > "$W/p/.harness/verify"; chmod +x "$W/p/.harness/verify"
    printf '# Task\nGoal: E2E-MARKER\n' > "$W/p/.harness/task.md"
    ( cd "$W/p" && timeout 120 claude --plugin-dir "$PLUGIN" -p "make a change" --allowedTools Bash >/dev/null 2>&1 ) || true
}
check() {  # $1 = expected gate results (comma list), $2 = expected feedback count, $3 = expected main requests
    python3 - "$W" "$1" "$2" "$3" <<'PY'
import json, sys
w, want, fb, reqs = sys.argv[1], sys.argv[2].split(","), int(sys.argv[3]), int(sys.argv[4])
got = [json.loads(l)["result"] for l in open(w + "/p/.harness/state/gate.jsonl")]
r = [json.loads(l) for l in open(w + "/requests.jsonl") if json.loads(l)["main"]]
assert got == want, ("gate results", got, want)
assert sum(x["feedback"] for x in r) == fb, ("feedback reached model", sum(x["feedback"] for x in r), fb)
assert len(r) == reqs, ("main requests", len(r), reqs)
assert r[0]["kernel"] and r[0]["task"], "kernel/task.md did not reach the model at session start"
print("ok:", got, "feedback=%d main_requests=%d" % (fb, len(r)))
PY
}
echo "[red]";   scenario 'echo "FAKE TEST FAILURE"; exit 1'; check FAIL,FAIL,FAIL,GAVE_UP 3 5
echo "[green]"; scenario 'exit 0';                          check PASS 0 2
echo "E2E passed"

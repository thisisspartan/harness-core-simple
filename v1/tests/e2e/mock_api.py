#!/usr/bin/env python3
"""Fake Anthropic /v1/messages server for the live E2E. Usage: mock_api.py PORT LOGFILE
First main-agent request -> a Bash tool_use that changes the tree; afterwards plain text 'done' (end_turn).
Logs one JSON line per request so run.sh can assert what reached the model."""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT, LOG = int(sys.argv[1]), sys.argv[2]


def sse(events):
    return "".join("event: %s\ndata: %s\n\n" % (e["type"], json.dumps(e)) for e in events).encode()


def message(blocks, stop):
    ev = [{"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant", "model": "mock",
           "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}}]
    for i, b in enumerate(blocks):
        if b["type"] == "text":
            start, delta = {"type": "text", "text": ""}, {"type": "text_delta", "text": b["text"]}
        else:
            start = {"type": "tool_use", "id": b["id"], "name": b["name"], "input": {}}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(b["input"])}
        ev += [{"type": "content_block_start", "index": i, "content_block": start},
               {"type": "content_block_delta", "index": i, "delta": delta},
               {"type": "content_block_stop", "index": i}]
    ev += [{"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 5}},
           {"type": "message_stop"}]
    return sse(ev)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, ctype, body):
        self.send_response(200)
        self.send_header("content-type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        if not self.path.split("?")[0].endswith("/messages"):
            return self.reply("application/json", json.dumps({"input_tokens": 10}).encode())
        raw = json.dumps(body)
        main = bool(body.get("tools"))  # side calls (titles, summaries) carry no tools
        tool_result = "tool_result" in json.dumps(body.get("messages", []))
        with open(LOG, "a") as f:
            f.write(json.dumps({"main": main, "tool_result": tool_result, "feedback": "verify exited" in raw,
                                "kernel": "Harness kernel" in raw, "task": "E2E-MARKER" in raw}) + "\n")
        if main and not tool_result:
            blocks, stop = [{"type": "tool_use", "id": "toolu_1", "name": "Bash",
                             "input": {"command": "echo hi > a.txt", "description": "change the tree"}}], "tool_use"
        else:
            blocks, stop = [{"type": "text", "text": "done"}], "end_turn"
        if body.get("stream"):
            return self.reply("text/event-stream", message(blocks, stop))
        self.reply("application/json", json.dumps({"id": "msg_x", "type": "message", "role": "assistant", "model": "mock",
                   "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "stop_sequence": None,
                   "usage": {"input_tokens": 1, "output_tokens": 1}}).encode())


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()

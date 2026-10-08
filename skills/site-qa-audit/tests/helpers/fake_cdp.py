#!/usr/bin/env python3
"""Fake CDP HTTP endpoint for tabs.py tests: /json/list from a state file, /json/close/<id> removes the page and is logged.

  fake_cdp.py PORT STATE.json      STATE.json: {"pages": [{"id": "A", "type": "page", "url": "…"}], "closed": []}
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT, STATE = int(sys.argv[1]), sys.argv[2]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def reply(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        st = json.load(open(STATE))
        if self.path == "/json/list":
            return self.reply(st["pages"])
        if self.path.startswith("/json/close/"):
            tid = self.path.rsplit("/", 1)[1]
            st["pages"] = [p for p in st["pages"] if p["id"] != tid]
            st.setdefault("closed", []).append(tid)
            json.dump(st, open(STATE, "w"))
            return self.reply("Target is closing")
        return self.reply({"error": "not found"}, 404)


HTTPServer(("127.0.0.1", PORT), H).serve_forever()

# SPDX-License-Identifier: MIT
"""Subprocess HTTP fixture; native DNF may hold the client's Python GIL."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import time

root, control = map(Path, sys.argv[1:])


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(root), **kwargs)

    def do_GET(self):
        state = json.loads(control.read_text())
        blocked = state["blocked"] and (
            state["failure_path"] is None or self.path == state["failure_path"]
        )
        if blocked:
            if state["status"] == "timeout":
                time.sleep(3)
                return
            self.send_error(state["status"])
        elif self.path == "/mirrorlist":
            body = ("http://127.0.0.1:%d/\n" % self.server.server_port).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
print(server.server_port, flush=True)
server.serve_forever()

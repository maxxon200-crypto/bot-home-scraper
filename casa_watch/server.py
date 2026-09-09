"""Local UI server. Only report assets are public; POST can request one bounded scan."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit, unquote


def start_server(directory, wake, port=8765):
    root = Path(directory).resolve()

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_json(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self.valid_host():
                self.send_error(403)
                return
            path = unquote(urlsplit(self.path).path)
            if path == "/api/status":
                try:
                    progress = json.loads((root / "progress.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    progress = {"running": False, "collected": 0}
                self.send_json({**progress, "queued": wake.is_set()})
                return
            target = (root / path.lstrip("/")).resolve()
            if not target.is_relative_to(root) or (path not in ("/", "/index.html", "/homes.json", "/progress.json") and not path.startswith("/assets/")):
                self.send_error(404)
                return
            if target.is_dir() and path != "/":
                self.send_error(404)
                return
            super().do_GET()

        def do_POST(self):
            expected = f"http://{self.headers.get('Host')}"
            if not self.valid_host() or self.headers.get("Origin") != expected:
                self.send_json({"message": "Request origin rejected"}, 403)
                return
            if self.path != "/api/collect" or self.headers.get("Content-Type") != "application/json":
                self.send_json({"message": "Unknown request"}, 400)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    raise ValueError
                body = json.loads(self.rfile.read(length))
                if body != {}:
                    raise ValueError
            except (ValueError, json.JSONDecodeError):
                self.send_json({"message": "Invalid request"}, 400)
                return
            wake.set()
            self.send_json({"message": "Collection requested."}, 202)

    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(root)))
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server

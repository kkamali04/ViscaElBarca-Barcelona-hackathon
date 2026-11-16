"""Loopback-only review HTTP server with fixed routes and bounded video streaming."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit

from .state import ReviewState


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, root, port=8765, demo=False):
        self.app = ReviewState(root, demo)
        super().__init__(("127.0.0.1", port), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "TouchlineLocal/1"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format, *args):
        # Local request paths/tokens and derived timeline never enter console logs.
        pass

    def origin_ok(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        return (self.headers.get("Host") in hosts and
                (self.headers.get("Origin") is None or self.headers.get("Origin") in {"http://" + host for host in hosts}))

    def reply_headers(self, status, mime, length=0, *, attachment=None, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if attachment:
            from urllib.parse import quote
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(attachment, safe=""))
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()

    def json(self, value, status=200):
        data = (json.dumps(value, allow_nan=False) + "\n").encode("utf-8")
        self.reply_headers(status, "application/json; charset=utf-8", len(data))
        if self.command != "HEAD":
            self.wfile.write(data)

    def file(self, path, *, name=None, video=False):
        path = Path(path)
        if not path.is_file():
            return self.json({"error": "This file is not available yet"}, 404)
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        if video and self.headers.get("Range"):
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers["Range"])
            if not match or not any(match.groups()):
                return self.range_error(size)
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                count = int(last)
                if count <= 0:
                    return self.range_error(size)
                start, end = max(0, size - count), size - 1
            if start > end or start >= size:
                return self.range_error(size)
            status = 206
        mime = "video/mp4" if video else (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        extra = {"Accept-Ranges": "bytes"} if video else {}
        if status == 206:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self.reply_headers(status, mime, max(0, end - start + 1), attachment=name, extra=extra)
        if self.command == "HEAD":
            return
        try:
            with path.open("rb") as source:
                source.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    block = source.read(min(65536, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    def range_error(self, size):
        self.reply_headers(416, "text/plain", 0, extra={"Content-Range": f"bytes */{size}"})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.origin_ok():
            return self.json({"error": "Use the local review address"}, 403)
        route = urlsplit(self.path).path
        app = self.server.app
        try:
            if route == "/api/health":
                return self.json({"app": "touchline-local-review", "mode": app.mode, "status": "ready"})
            if route == "/api/state":
                return self.json(app.state())
            if route == "/api/timeline":
                return self.json(app.timeline())
            if route == "/":
                return self.file(app.root / "review_app/static/index.html")
            if route in ("/static/app.js", "/static/app.css"):
                return self.file(app.root / "review_app" / route.lstrip("/"))
            if route == "/media/tactical.mp4":
                if app.demo:
                    return self.json({"error": "Demo has no private video"}, 404)
                return self.file(app.root / "more-than-a-hack-2027-main/data/tactical/BAR-ATH_tactical.mp4", video=True)
            if route == "/download/candidate":
                with app.lock:
                    if not app.current()["valid"]:
                        raise ValueError("Generate a valid CSV before downloading")
                    return self.file(app.csv, name="DEMO-candidate.csv" if app.demo else "candidate.csv")
            if route == "/download/code":
                return self.file(app.code_zip, name="touchline-code.zip")
            if route == "/download/technical":
                return self.file(app.root / "MVP_TECHNICAL.md", name="technical-draft.md")
            if route == "/download/review-pack" and app.bundle:
                return self.file(app.bundle, name="DEMO-review-pack.zip" if app.demo else "review-pack.zip")
            return self.json({"error": "Page not found"}, 404)
        except (ValueError, OSError) as error:
            return self.json({"error": str(error)}, 400)

    def do_POST(self):
        if not self.origin_ok():
            return self.json({"error": "Only the local review page can perform this action"}, 403)
        expected = self.server.app.token
        if not secrets.compare_digest(self.headers.get("X-Review-Token", "").encode("utf-8"), expected.encode("utf-8")):
            return self.json({"error": "Reload the review page before trying this action"}, 403)
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self.json({"error": "Send an application/json request"}, 415)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 8192:
                return self.json({"error": "Request is too large"}, 413)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("Request must be a JSON object")
            route = urlsplit(self.path).path
            app = self.server.app
            if route == "/api/run":
                if not app.start_run():
                    return self.json({"error": "A generation is already running"}, 409)
                return self.json({"status": "running"}, 202)
            if route == "/api/export":
                return self.json(app.export(body.get("team_name", ""), body.get("repository_url", "")))
            if route == "/api/shutdown":
                if app.run["status"] == "running":
                    return self.json({"error": "Wait for the active generation to finish before stopping"}, 409)
                self.json({"status": "stopping"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            return self.json({"error": "Action not found"}, 404)
        except (ValueError, OSError, UnicodeError) as error:
            return self.json({"error": str(error)}, 400)


def make_server(root, port=8765, demo=False):
    return Server(root, port, demo)

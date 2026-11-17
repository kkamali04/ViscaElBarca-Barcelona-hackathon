"""Loopback-only fixed-asset HTTP service for bounded replay windows."""
from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, urlsplit

from .store import CHUNK_FRAMES, ReplayError, ReplayStore, prepare_store


APP = "touchline-tracking-replay"
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/static/app.css": ("app.css", "text/css; charset=utf-8"),
          "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/static/clock.js": ("clock.js", "text/javascript; charset=utf-8")}
INTEGER = re.compile(r"(?:0|[1-9][0-9]{0,9})\Z", flags=re.ASCII)
MAX_RESPONSE_BYTES = 1024 * 1024


class ReplayService:
    def __init__(self, *, demo=False, data_dir=None, predictions=None, cache_dir):
        self.mode = "demo" if demo else "local"
        self._lock = threading.Lock()
        self._status = "building"
        self._message = "Preparing invented tracking." if demo else "Preparing supplied tracking."
        self._progress = {"phase": "starting", "records": 0}
        self._store = None
        self._options = dict(demo=demo, data_dir=data_dir, predictions=predictions,
                             cache_dir=cache_dir, progress=self._update)

    def _update(self, progress):
        with self._lock:
            self._progress = dict(progress)

    def start(self):
        threading.Thread(target=self._prepare, daemon=True, name="replay-prepare").start()

    def _prepare(self):
        try:
            store = prepare_store(**self._options)
        except ReplayError as exc:
            self.fail(str(exc))
        except Exception:
            # Parser/OS exception strings can contain records, filenames or paths.
            self.fail("Could not prepare replay. Check input format, permissions and available disk space.")
        else:
            with self._lock:
                self._store = store
                self._status = "ready"
                self._progress = {"phase": "ready", "records": store.manifest["frames"],
                                  "total": store.manifest["frames"]}

    def fail(self, message):
        with self._lock:
            self._status = "failed"
            self._message = message
            self._store = None

    def health(self):
        with self._lock:
            return {"app": APP, "version": 2, "mode": self.mode, "status": self._status}

    def metadata(self):
        with self._lock:
            if self._status == "ready":
                return self._store.metadata()
            return {"mode": self.mode, "status": self._status,
                    "message": self._message, "progress": dict(self._progress)}

    def store(self) -> ReplayStore | None:
        with self._lock:
            return self._store if self._status == "ready" else None


class ReplayHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, service: ReplayService, shutdown_token: str):
        super().__init__(address, ReplayHandler)
        self.service = service
        self.shutdown_token = shutdown_token
        port = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            self.allowed_hosts.update({"127.0.0.1", "localhost"})
        self.allowed_origins = {"http://" + host for host in self.allowed_hosts}

    def handle_error(self, request, client_address):
        # Do not let socket exceptions or user-controlled requests leak to logs.
        pass


class ReplayHandler(BaseHTTPRequestHandler):
    server_version = "TrackingReplay/2"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        pass

    def _send(self, status, content, content_type="application/json; charset=utf-8", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Connection", "close")
        for key, value in (extra or {}).items():
            self.send_header(key, str(value))
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _json(self, status, value):
        self._send(status, json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8"))

    def _error(self, status, message):
        self._json(status, {"status": "error", "message": message})

    def send_error(self, code, message=None, explain=None):
        # BaseHTTPRequestHandler's default page includes supplied request text.
        self._error(code, "Invalid HTTP request.")

    def _allowed(self):
        hosts, origins = self.headers.get_all("Host", []), self.headers.get_all("Origin", [])
        if (len(hosts) != 1 or hosts[0] not in self.server.allowed_hosts
                or len(origins) > 1 or (origins and origins[0] not in self.server.allowed_origins)
                or self.headers.get("Sec-Fetch-Site", "") == "cross-site"):
            self._error(403, "Only this local replay origin is allowed.")
            return False
        return True

    def _route(self):
        if len(self.path) > 2048:
            self._error(400, "The request URL is invalid.")
            return None
        try:
            parsed = urlsplit(self.path)
        except ValueError:
            self._error(400, "The request URL is invalid.")
            return None
        if parsed.scheme or parsed.netloc or parsed.fragment:
            self._error(400, "The request URL is invalid.")
            return None
        return parsed

    def do_GET(self):
        if not self._allowed():
            return
        route = self._route()
        if route is None:
            return
        if route.path == "/api/frames":
            self._frames(route.query)
            return
        if route.query:
            self._error(400, "This route does not accept query fields.")
            return
        if route.path == "/api/health":
            self._json(200, self.server.service.health())
        elif route.path == "/api/replay":
            self._json(200, self.server.service.metadata())
        elif route.path in ASSETS:
            name, content_type = ASSETS[route.path]
            try:
                content = (Path(__file__).resolve().parent / "static" / name).read_bytes()
            except OSError:
                self._error(503, "The replay interface assets are unavailable.")
                return
            self._send(200, content, content_type)
        else:
            self._error(404, "Unknown replay route.")

    def _frames(self, query):
        try:
            fields = parse_qs(query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
            if set(fields) != {"start", "count"} or any(len(values) != 1 for values in fields.values()):
                raise ValueError
            if any(INTEGER.fullmatch(fields[key][0]) is None for key in fields):
                raise ValueError
            start, count = int(fields["start"][0]), int(fields["count"][0])
            if not 1 <= count <= CHUNK_FRAMES:
                raise ValueError
        except ValueError:
            self._error(400, "Use integer start and count fields; count must be 1..250.")
            return
        store = self.server.service.store()
        if store is None:
            self._error(409, "The replay is not ready.")
            return
        if not 0 <= start < store.manifest["frames"]:
            self._error(400, "The start frame is outside the replay.")
            return
        try:
            content = store.read_window(start, count)
            if len(content) > MAX_RESPONSE_BYTES:
                raise ReplayError("The replay response exceeds the supported size.")
        except Exception:
            self.server.service.fail("The replay cache changed or became unavailable; restart to rebuild it.")
            self._error(409, "The replay cache is unavailable; restart to rebuild it.")
            return
        actual_count = min(count, store.manifest["frames"] - start)
        self._send(200, content, "application/octet-stream",
                   {"X-Start-Frame": start, "X-Frame-Count": actual_count,
                    "X-Row-Floats": store.manifest["row_floats"]})

    def do_POST(self):
        if not self._allowed():
            return
        route = self._route()
        if route is None:
            return
        if route.path != "/api/shutdown" or route.query:
            self._error(404, "Unknown replay route.")
            return
        tokens = self.headers.get_all("X-Replay-Token", [])
        if len(tokens) != 1 or not hmac.compare_digest(tokens[0], self.server.shutdown_token):
            self._error(403, "Local shutdown authentication is required.")
            return
        if self.headers.get("Transfer-Encoding") is not None:
            self._error(400, "The shutdown request body is invalid.")
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 1024:
                raise ValueError
        except ValueError:
            self._error(400, "The shutdown request body is invalid.")
            return
        self.rfile.read(size)
        self._json(200, {"status": "stopping"})
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def do_HEAD(self):
        if self._allowed():
            self._error(405, "Only GET and authenticated local shutdown are supported.")

    do_OPTIONS = do_HEAD
    do_PUT = do_HEAD
    do_DELETE = do_HEAD
    do_PATCH = do_HEAD

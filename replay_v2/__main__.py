"""Start the local tracking replay without running possession inference."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import webbrowser

from .server import APP, ReplayHTTPServer, ReplayService
from .store import ReplayError, _private_directory, atomic_private_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay supplied tracking coordinates locally.")
    parser.add_argument("--demo", action="store_true", help="Use invented moving tracking with missing observations.")
    parser.add_argument("--data-dir", type=Path, help="Read-only input root containing tactical/.")
    parser.add_argument("--predictions", type=Path, help="Optional read-only exact frame,label CSV.")
    parser.add_argument("--cache-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "local" / "replay-v2")
    parser.add_argument("--port", type=int, default=8771)
    parser.add_argument("--open", action="store_true", help="Open the local viewer in the default browser.")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be 1..65535")
    if args.demo and (args.data_dir is not None or args.predictions is not None):
        parser.error("--demo cannot be combined with supplied tracking or predictions")
    if not args.demo and args.data_dir is None:
        parser.error("choose --data-dir or --demo")
    server, state_path, token = None, None, secrets.token_urlsafe(32)
    try:
        # Do not create even a runtime token beneath the read-only input root.
        if args.data_dir is not None:
            data_dir = args.data_dir.resolve()
            selected_cache = args.cache_dir.resolve()
            if selected_cache == data_dir or data_dir in selected_cache.parents:
                raise ReplayError("Choose a cache directory outside the supplied input directory.")
        cache_dir = _private_directory(args.cache_dir)
        service = ReplayService(demo=args.demo, data_dir=args.data_dir,
                                predictions=args.predictions, cache_dir=cache_dir)
        server = ReplayHTTPServer(("127.0.0.1", args.port), service, token)
        state_path = cache_dir / f"runtime-{args.port}.json"
        atomic_private_json(state_path, {"app": APP, "version": 2, "port": args.port,
                                         "pid": os.getpid(), "shutdown_token": token})
        service.start()
        print(f"Tracking replay: http://127.0.0.1:{args.port} ({'Invented tracking' if args.demo else 'Supplied tracking'})", flush=True)
        print("Preparation runs in the background. Stop with Ctrl+C or stop-replay.ps1.", flush=True)
        if args.open:
            threading.Thread(target=lambda: webbrowser.open(f"http://127.0.0.1:{args.port}"), daemon=True).start()
        server.serve_forever(poll_interval=0.25)
        return 0
    except KeyboardInterrupt:
        return 0
    except ReplayError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("Could not start the local replay. Check the port, permissions and cache directory.", file=sys.stderr)
        return 2
    finally:
        if server is not None:
            server.server_close()
        if state_path is not None:
            try:
                if not state_path.is_symlink() and json.loads(state_path.read_text(encoding="utf-8")).get("shutdown_token") == token:
                    state_path.unlink()
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    raise SystemExit(main())

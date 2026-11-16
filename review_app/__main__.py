"""python -m review_app: local-only review, with explicit synthetic demo mode."""
import argparse
from pathlib import Path
import webbrowser

from .server import make_server
from .state import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--demo", action="store_true", help="Invented timeline; never loads private match inputs")
    parser.add_argument("--open", action="store_true", help="Open the local review page in your browser")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    root = Path(__file__).resolve().parents[1]
    server = make_server(root, args.port, args.demo)
    url = f"http://127.0.0.1:{server.server_port}"
    atomic_json(server.app.work / "server.json", {"url": url, "mode": server.app.mode})
    print(f"Touchline review: {url} ({server.app.mode})", flush=True)
    print("Private files stay on this computer. Stop with Ctrl+C or stop-review.ps1.", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

# Which Touchline page to open

The current coordinate viewer is **Touchline · Tracking replay**, launched by
`replay.ps1` or `start-match.ps1`. It draws the supplied tracking observations;
an optional possession CSV supplies the label overlay. The **Invented tracking**
badge identifies its generated demo. **Supplied tracking** identifies a local
match input. Predictions never control marker positions.

The older **Touchline — Possession review** application (`review.ps1`,
`python -m review_app`) is a separate CSV generation/export workflow. Its
**SYNTHETIC DEMO** contains fixed SVG players and a ball moved by a mathematical
animation. That display is an illustration, not a replay of tracking or evidence
about model quality. The legacy application is retained byte-exact for the
106-member standalone export; do not replace its assets with replay assets.

## Start the coordinate viewer

From the full repository with the Python environment already installed:

```powershell
# Invented data only; no match download or possession CSV required.
.\replay.ps1 -Demo -Port 8771

# For supplied tracking: generate fresh predictions, then replay observations.
# Replace this placeholder with the authorized local data directory.
.\start-match.ps1 -DataDir 'C:\path\to\challenge\data' -Port 8767
```

Open the local address printed by the selected launcher and keep that terminal
running. The port is configurable; it does not select an application. The full
repository includes `replay_v2`; the legacy 106-member ZIP does not. See
[README.md](../README.md) for setup and [REPLAY.md](../REPLAY.md) for separate
inference/replay commands and storage details.

## An old illustration or “Request failed (404)” is still visible

1. Check which terminal process owns the address. Stop an obsolete server with
   **Ctrl+C in its own terminal**, then launch the coordinate viewer on that
   port. An occupied port must be resolved before launching another server.
2. Navigate to the printed `http://127.0.0.1:<port>/` address and hard reload
   (**Ctrl+Shift+R**). Opening a saved/static HTML file is not a running viewer.
3. Confirm the title **Touchline · Tracking replay** and its mode badge. Use
   **Play** after preparation finishes. A stationary-player SVG and a moving
   illustrative ball identify the legacy demo, not this coordinate viewer.

The two applications use different APIs. The old page requests `/api/state` and
`/api/timeline`; the coordinate viewer requests `/api/replay` and `/api/frames`.
An old page still running against a different server can therefore receive a
404. A hard reload gets the HTML and scripts from the currently running server;
changing ports alone does not repair an outdated browser document.

Keep supplied tracking, media, CSV rows and derived replay views local. Browser
automation, model-facing screenshots and shared demonstrations must use invented
data. A moving replay and valid CSV format do not establish possession accuracy.

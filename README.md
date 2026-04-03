# Nomad's Game PvP Server

Real multiplayer browser shooter built with FastAPI and WebSockets.

## What this is

- Real player-vs-player online shooter
- Persistent Python server
- WebSocket-based realtime gameplay
- Render-ready deployment config included

## Repo contents

- `server.py`: main FastAPI app and realtime game server
- `requirements.txt`: Python dependencies
- `render.yaml`: Render Blueprint config
- `.python-version`: Python version pin

## Render

This repo is prepared for Render as a persistent web service.

- Runtime: Python
- Build: `pip install -r requirements.txt`
- Start: `python server.py`
- Recommended plan: `starter`

`starter` is used because free web services spin down and are not suitable for a permanent multiplayer game.

## Upload to GitHub

1. Create an empty GitHub repo named `nomads-game-pvp-server`
2. Upload the contents of this folder as the repo root
3. Connect the repo to Render
4. Deploy with the included `render.yaml`

## Local run

```powershell
python server.py
```

Then open `http://127.0.0.1:8000`.

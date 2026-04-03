# Render Deploy

This folder contains the real multiplayer version of the shooter.

Files added for Render:

- `requirements.txt`
- `.python-version`
- `render.yaml`

Official references used:

- Render FastAPI deploy docs
- Render web services docs
- Render Python version docs
- Render free-tier docs

Recommended deploy path:

1. Put this folder in a GitHub, GitLab, or Bitbucket repo.
2. In Render, create a new Web Service or sync the included `render.yaml` as a Blueprint.
3. Keep the runtime as `Python`.
4. Let Render run:
   - Build: `pip install -r requirements.txt`
   - Start: `python server.py`
5. Use the `starter` instance type for a permanent multiplayer host.

Notes:

- The app already binds to `0.0.0.0` and uses port `8000`, which works on Render.
- The included `render.yaml` assumes this folder is the repo root.
- Free Render web services spin down after inactivity, so they are not appropriate for a permanent PvP game.
- The included blueprint is set to `starter` to avoid idle spin-down on deploy.

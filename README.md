# web-testing-assistant
Human-in-the-Loop Web Testing Assistant


## Run with Docker

```bash
docker compose up --build
```

Then open http://localhost:8000.

| Service | What it does |
|---|---|
| `backend` | `uvicorn backend.main:app` on :8000, serves the UI and forwards to the runner |
| `runner` | `uvicorn runner.server:app` on :8001 (internal), headless Chromium via Playwright |
| `ollama` | Ollama server, model store is the host's `~/.ollama` (bind mount) |
| `ollama-pull` | One-shot: pulls `qwen2.5:7b-instruct` only if the store doesn't have it |
| `ollama-warmup` | Sidecar: loads the model and re-loads it if it ever gets unloaded |

Settings (model, store location, ports) are in `.env.example`.
To inspect an app running on your machine, use `http://host.docker.internal:PORT`, not `localhost`.

"""Backend: serves the frontend and forwards inspection requests to the runner.

Start it with:  uv run uvicorn backend.main:app --port 8000
Then open http://localhost:8000
"""
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

RUNNER_URL = os.environ.get("RUNNER_URL", "http://localhost:8001")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Web Testing Assistant")


class InspectRequest(BaseModel):
    url: str
    scope: str | None = None


@app.post("/api/inspect")
def inspect(req: InspectRequest):
    """Ask the runner to inspect the page and return what it observed."""
    try:
        response = httpx.post(f"{RUNNER_URL}/inspect", json=req.model_dump(), timeout=120)
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Runner is not running (port 8001).")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="The runner took too long to respond.")

    if response.status_code != 200:
        detail = response.json().get("detail", "Runner error")
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


# Must come after the API routes, so it only serves files for other paths.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
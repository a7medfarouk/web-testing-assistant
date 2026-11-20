"""Runner API. This is the only process that controls the browser.

Start it with:  uv run uvicorn runner.server:app --port 8001
(Do not use --reload on Windows: Playwright needs to start its own browser process.)
"""
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from runner.inspector import inspect_page

app = FastAPI(title="Runner")

# Containers have no display, so Docker sets RUNNER_HEADLESS=true. Locally the
# default stays a visible browser window.
HEADLESS = os.environ.get("RUNNER_HEADLESS", "").lower() in ("1", "true", "yes")


class InspectRequest(BaseModel):
    url: str
    scope: str | None = None


# Plain `def` on purpose: Playwright's sync API cannot run inside `async def`.
@app.post("/inspect")
def inspect(req: InspectRequest):
    try:
        return inspect_page(req.url, req.scope, headless=HEADLESS)
    except ValueError as err:  # bad URL or scope not found
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:  # browser/navigation problems
        raise HTTPException(status_code=500, detail=f"Inspection failed: {err}")
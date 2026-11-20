"""Backend: serves the frontend, forwards inspections to the runner and calls the model.

Start it with:  uv run uvicorn backend.main:app --port 8000
Then open http://localhost:8000
"""
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import FRONTEND_DIR, RUNNER_URL
from backend.model_client import ModelError, ask_model
from backend.storage import load_inspection, log_model_call, save_inspection

app = FastAPI(title="Web Testing Assistant")


class InspectRequest(BaseModel):
    url: str
    scope: str | None = None


class SummarizeRequest(BaseModel):
    inspection_id: str
    goal: str | None = None
    element_ids: list[int] = []


@app.post("/api/inspect")
def inspect(req: InspectRequest):
    """Ask the runner to inspect the page, save the result and return it."""
    try:
        response = httpx.post(
            f"{RUNNER_URL}/inspect",
            json={"url": req.url, "scope": req.scope},
            timeout=120,
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Runner is not running (port 8001).")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="The runner took too long to respond.")

    if response.status_code != 200:
        detail = response.json().get("detail", "Runner error")
        raise HTTPException(status_code=response.status_code, detail=detail)

    result = response.json()
    return {"inspection_id": save_inspection(result), **result}


@app.post("/api/summarize")
def summarize(req: SummarizeRequest):
    """Ask the model about the selected elements of a saved inspection."""
    inspection = load_inspection(req.inspection_id)
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    elements = inspection["elements"]
    if req.element_ids:
        elements = [e for e in elements if e["id"] in req.element_ids]
        if not elements:
            raise HTTPException(status_code=400, detail="None of the selected elements exist.")

    try:
        answer, usage = ask_model(req.goal, inspection, elements)
    except ModelError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err))

    log_model_call(
        {
            "inspection_id": req.inspection_id,
            "goal": req.goal,
            "elements_used": len(elements),
            **usage,
        }
    )
    return {"answer": answer, "usage": usage, "elements_used": len(elements)}


# Must come after the API routes, so it only serves files for other paths.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from backend.config import DATA_DIR

INSPECTIONS_DIR = DATA_DIR / "inspections"
MODEL_LOG = DATA_DIR / "model_calls.jsonl"


def save_inspection(result):
    """Save an inspection as a JSON file and return its id."""
    INSPECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    host = re.sub(r"[^A-Za-z0-9.-]+", "_", urlparse(result["url"]).netloc) or "page"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    inspection_id = f"{host}_{stamp}"
    path = INSPECTIONS_DIR / f"{inspection_id}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return inspection_id


def load_inspection(inspection_id):
    """Return the saved inspection, or None if the id is unknown."""
    if Path(inspection_id).name != inspection_id or inspection_id.startswith("."):
        return None
    path = INSPECTIONS_DIR / f"{inspection_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def log_model_call(record):
    """Append one model call (tokens, timing, ...) to the usage log."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    with MODEL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RUNNER_URL = os.environ.get("RUNNER_URL", "http://localhost:8001")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
HARDWARE = os.environ.get("HARDWARE", "not set")

DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
FRONTEND_DIR = ROOT / "frontend"

MAX_ELEMENTS_IN_PROMPT = 40

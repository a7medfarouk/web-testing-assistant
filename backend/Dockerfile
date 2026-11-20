# Build context is the project root (see docker-compose.yml).
FROM python:3.14-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so code edits don't invalidate this layer.
# The backend never drives a browser, so skip playwright.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project --no-install-package playwright

ENV PATH="/opt/venv/bin:$PATH"

# main.py serves ../frontend, so both folders must sit side by side.
COPY backend ./backend
COPY frontend ./frontend

RUN useradd --system --uid 10001 app \
    && mkdir /app/data \
    && chown app /app/data
USER app

EXPOSE 8000
# Same command as the docstring in backend/main.py, bound to all interfaces.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

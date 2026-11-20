# Build context is the project root (see docker-compose.yml).
FROM python:3.14-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

ENV PATH="/opt/venv/bin:$PATH"

# Playwright's bundled Node binary needs libatomic, which slim images lack, and it
# must exist before `playwright install` can run at all.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Chromium plus the system libraries it needs. The browser build is tied to the
# playwright version in uv.lock, so this always matches the Python package.
RUN playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

COPY runner ./runner

RUN useradd --system --uid 10001 --create-home app
USER app

ENV RUNNER_HEADLESS=true
EXPOSE 8001
CMD ["uvicorn", "runner.server:app", "--host", "0.0.0.0", "--port", "8001"]
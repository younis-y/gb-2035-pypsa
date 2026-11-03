# syntax=docker/dockerfile:1
# The GB 2035 results explorer. Built, linted and smoke-tested in GitHub Actions only
# (.github/workflows/docker.yml): Docker does not run on the development machine.

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.16 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, in their own layer: they change far less often than the source.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra app
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra app

FROM python:3.13-slim AS runtime
LABEL org.opencontainers.image.source="https://github.com/younis-y/gb-2035-pypsa" \
      org.opencontainers.image.description="GB 2035 power-system model: read-only results explorer" \
      org.opencontainers.image.licenses="MIT"
RUN groupadd --system --gid 1001 gb2035 \
    && useradd --system --uid 1001 --gid gb2035 --create-home gb2035
WORKDIR /app
COPY --from=builder --chown=gb2035:gb2035 /app/.venv /app/.venv
COPY --chown=gb2035:gb2035 src ./src
COPY --chown=gb2035:gb2035 config ./config
COPY --chown=gb2035:gb2035 data/derived ./data/derived
COPY --chown=gb2035:gb2035 data/manifest.json ./data/manifest.json
COPY --chown=gb2035:gb2035 results ./results
COPY --chown=gb2035:gb2035 docs/figures ./docs/figures
COPY --chown=gb2035:gb2035 workflow ./workflow
COPY --chown=gb2035:gb2035 pyproject.toml uv.lock README.md ./
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
USER gb2035
EXPOSE 8501
# No curl in python:3.13-slim, and no reason to add one.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4).status == 200 else 1)"]
CMD ["streamlit", "run", "src/gb2035/app/main.py", "--server.address=0.0.0.0", "--server.port=8501"]

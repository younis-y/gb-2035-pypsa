set shell := ["bash", "-cu"]

default: test

sync:
    uv sync --all-extras --group dev

test:
    uv run pytest

test-all:
    uv run pytest -m "not network" --runslow

lint:
    uv run ruff check . && uv run ruff format --check .

fmt:
    uv run ruff format . && uv run ruff check --fix .

typecheck:
    uv run mypy

run scenario="test":
    uv run gb2035 run --scenario {{scenario}}

# The Streamlit explorer arrives in the next plan; `app/` does not exist on this branch yet.
app:
    @echo "the Streamlit app arrives in phase 3; nothing to run yet"

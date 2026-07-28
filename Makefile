.PHONY: install run test lint format up down

# Use the project's virtualenv interpreter when present, so bare `uvicorn` /
# `pytest` / `ruff` on PATH (e.g. from another venv) can't shadow the project deps.
# Override with `make PY=python ...` to use whatever interpreter is active.
PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python)

install:
	$(PY) -m pip install -r requirements.txt
	@test -f .env || cp .env.example .env

run:
	$(PY) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .

up:
	podman compose up --build

down:
	podman compose down

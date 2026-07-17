.PHONY: install run test lint format docker-up docker-down

install:
	pip install -r requirements.txt
	@test -f .env || cp .env.example .env

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -q

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

docker-up:
	docker compose up --build

docker-down:
	docker compose down

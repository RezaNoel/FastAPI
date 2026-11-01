.PHONY: dev test lint migrate

dev:
	uvicorn app.main:app --reload

test:
	pytest

lint:
	ruff check app tests
	ruff format --check app tests

migrate:
	alembic upgrade head

.PHONY: up down rules test backend-test frontend-test lint

up:
	docker compose up --build

down:
	docker compose down

rules:
	curl -X POST http://localhost:8000/api/rules/seed

test: backend-test frontend-test

backend-test:
	cd backend && pytest

frontend-test:
	cd frontend && npm run lint && npm run typecheck

lint:
	cd backend && ruff check app tests
	cd frontend && npm run lint

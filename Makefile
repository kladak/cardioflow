PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip
API_HOST ?= 127.0.0.1
API_PORT ?= 8010
CARDIOFLOW_API_ORIGIN ?= http://$(API_HOST):$(API_PORT)

.PHONY: setup setup-backend setup-frontend dev api api-start web web-build web-start start check-api-port test test-backend test-frontend lint e2e check gen-api reset-db

setup: setup-backend setup-frontend

setup-backend:
	python3.11 -m venv backend/.venv
	$(PIP) install -q -e "backend[dev]"

setup-frontend:
	@if [ -f frontend/package.json ]; then cd frontend && npm ci; else echo "frontend package not found"; fi

check-api-port:
	@$(PY) scripts/check_port.py $(API_HOST) $(API_PORT)

api: check-api-port
	cd backend && .venv/bin/uvicorn app.main:create_app --factory --reload --host $(API_HOST) --port $(API_PORT)

api-start: check-api-port
	cd backend && .venv/bin/uvicorn app.main:create_app --factory --host $(API_HOST) --port $(API_PORT)

web:
	cd frontend && CARDIOFLOW_API_ORIGIN=$(CARDIOFLOW_API_ORIGIN) npm run dev

web-build:
	cd frontend && CARDIOFLOW_API_ORIGIN=$(CARDIOFLOW_API_ORIGIN) npm run build

web-start:
	cd frontend && CARDIOFLOW_API_ORIGIN=$(CARDIOFLOW_API_ORIGIN) npm run start

dev:
	$(MAKE) -j2 api web

start:
	$(MAKE) -j2 api-start web-start

test-backend:
	cd backend && .venv/bin/pytest -q

test-frontend:
	cd frontend && npm test

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/mypy app
	@if [ -f frontend/package.json ]; then cd frontend && npm run lint && npx tsc --noEmit; fi

e2e:
	cd e2e && npx playwright test

test: test-backend test-frontend

check: lint test

gen-api:
	cd backend && .venv/bin/python -c "import json; from app.main import create_app; print(json.dumps(create_app().openapi(), indent=2))" > ../frontend/openapi.json
	cd frontend && npx openapi-typescript openapi.json -o src/lib/api-types.ts

reset-db:
	rm -f backend/data/cardioflow.db

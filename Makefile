PY ?= backend/.venv/bin/python
URL ?= http://localhost:8000

.PHONY: db dev web test eval seed lint smoke build

db:            ## start Postgres + pgvector
	docker compose up -d db

dev: db        ## API with auto-reload on :8000 (run `make web` in another terminal for the SPA)
	cd backend && ../$(PY) -m alembic upgrade head && ../$(PY) -m uvicorn app.main:app --reload --port 8000

web:           ## Vite dev server on :5173, proxying /api to :8000
	cd frontend && npm run dev

test:          ## unit + DB tests
	cd backend && ../$(PY) -m pytest -q

eval:          ## per-lane precision/recall/latency -> eval/results/
	cd backend && ../$(PY) ../eval/run_eval.py

seed:          ## create a persistent (non-sandbox) workspace with password logins
	cd backend && ../$(PY) -m app.seed.cli

lint:
	cd backend && ../$(PY) -m ruff check app tests
	cd frontend && npx tsc --noEmit

smoke:         ## judge-path smoke test against a running deployment: make smoke URL=https://...
	$(PY) scripts/smoke.py $(URL)

build:
	docker build -t countersign .

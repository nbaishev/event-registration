PNPM ?= corepack pnpm
export PNPM
UV = uv run --frozen --project backend

.PHONY: bootstrap up down migrate api-generate test check e2e verify verify-ci
bootstrap:
	uv sync --frozen --project backend
	$(UV) python scripts/bootstrap.py
	cd frontend && $(PNPM) install --frozen-lockfile
up:
	docker compose up -d --build --wait --wait-timeout 120
down:
	docker compose down
migrate:
	docker compose run --rm backend alembic upgrade head
api-generate:
	$(UV) python scripts/check_api_drift.py --write
test:
	python3 scripts/verification.py test
check:
	$(UV) ruff check backend scripts
	$(UV) ruff format --check backend scripts
	$(UV) mypy --config-file backend/pyproject.toml backend/app scripts
	$(UV) pytest backend/tests/unit -q
	cd frontend && $(PNPM) lint
	cd frontend && $(PNPM) typecheck
	cd frontend && $(PNPM) test
	$(UV) python scripts/check_api_drift.py
e2e:
	python3 scripts/verification.py e2e
verify: check
	python3 scripts/verification.py verify

verify-ci: check
	python3 scripts/verification.py verify-ci

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

# Standalone production commands; .env.prod is read only by Compose.
PROD_COMPOSE = docker compose --env-file .env.prod -f compose.prod.yaml
BOOTSTRAP_COMPOSE = docker compose --env-file .env.prod -f compose.certbot-bootstrap.yaml
CERT_ISSUE = $(BOOTSTRAP_COMPOSE) run --rm --no-deps --entrypoint /bin/sh certbot -ec 'test -n "$$APP_DOMAIN" && test -n "$$CERTBOT_EMAIL"; exec certbot certonly --webroot -w /var/www/certbot --cert-name "$$APP_DOMAIN" -d "$$APP_DOMAIN" --email "$$CERTBOT_EMAIL" --agree-tos --non-interactive "$$@"' --

.PHONY: prod-config prod-up prod-down prod-ps prod-logs prod-nginx-check prod-nginx-reload prod-bootstrap prod-cert-check prod-cert-issue prod-cert-renew prod-cert-renew-check
prod-config:
	$(PROD_COMPOSE) config --quiet
prod-up: prod-config
	$(PROD_COMPOSE) up -d --build --wait --wait-timeout 180
prod-down:
	$(PROD_COMPOSE) down
prod-ps:
	$(PROD_COMPOSE) ps
prod-logs:
	$(PROD_COMPOSE) logs --tail=100 --follow
prod-nginx-check:
	$(PROD_COMPOSE) exec -T nginx nginx -t
prod-nginx-reload: prod-nginx-check
	$(PROD_COMPOSE) exec -T nginx nginx -s reload
prod-bootstrap:
	$(BOOTSTRAP_COMPOSE) config --quiet
	$(BOOTSTRAP_COMPOSE) up -d --wait --wait-timeout 180
prod-cert-check:
	$(CERT_ISSUE) --dry-run
prod-cert-issue:
	$(CERT_ISSUE)
prod-cert-renew:
	./infra/certbot/renew.sh
prod-cert-renew-check:
	./infra/certbot/renew.sh --dry-run

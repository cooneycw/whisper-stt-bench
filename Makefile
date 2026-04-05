.PHONY: install dev lint format test typecheck verify \
       docker-build docker-guard docker-up docker-down docker-clean docker-logs \
       health deploy deploy-stub \
       bench bench-quick bench-report \
       secret-scan dep-audit dockerfile-lint \
       smoke-live-components shared-pipeline-hash-check \
       clean

DOCKER_GUARD_MIN_FREE_GB ?= 20

# --- Dependencies ---
install:
	uv sync

dev:
	uv sync --extra dev --extra bench

# --- Code Quality ---
lint:
	uv run ruff check .

format:
	uv run ruff format .

shared-pipeline-hash-check:
	python3 scripts/check_shared_pipeline_hashes.py

typecheck:
	uv run python -m compileall src tests scripts

test:
	uv run pytest -m "not gpu and not benchmark and not live" -q

verify: shared-pipeline-hash-check lint test typecheck

# --- Docker ---
docker-build:
	docker build --pull -t whisper-stt-bench:latest .

docker-guard:
	DOCKER_GUARD_MIN_FREE_GB=$(DOCKER_GUARD_MIN_FREE_GB) bash scripts/docker_host_guard.sh

docker-up:
	docker compose up --build --force-recreate --remove-orphans -d

docker-down:
	docker compose down

docker-clean:
	docker compose down -v --remove-orphans
	docker image prune -f --filter "label=com.docker.compose.project=whisper-stt-bench"

docker-logs:
	docker compose logs -f

health:
	@echo "Waiting for container health..."
	@CONTAINER="$${WHISPER_BENCH_CONTAINER:-whisper-stt-bench-whisper-bench-1}"; \
	for i in $$(seq 1 45); do \
		STATUS=$$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$$CONTAINER" 2>/dev/null || echo "missing"); \
		if [ "$$STATUS" = "healthy" ]; then \
			echo "Service healthy"; \
			exit 0; \
		fi; \
		echo "  Attempt $$i/45: $$STATUS"; \
		sleep 2; \
	done; \
	echo "Health check timed out. Recent logs:"; \
	docker compose logs --tail=50; \
	exit 1

# --- Deploy ---
deploy: docker-guard docker-up health
	@echo "Deploy (with secrets sidecar) complete."

deploy-stub: docker-up health
	@echo "Deploy (stub, no secrets sidecar) complete."

# --- Benchmark ---
bench:
	uv run python scripts/benchmark.py \
		--corpus-dir $${WHISPER_BENCH_CORPUS_DIR:-.runtime/corpus} \
		--results-dir .runtime/results

bench-quick:
	uv run python scripts/benchmark.py \
		--corpus-dir $${WHISPER_BENCH_CORPUS_DIR:-.runtime/corpus} \
		--models base \
		--results-dir .runtime/results

bench-report:
	@echo "Latest results:"
	@ls -t .runtime/results/benchmark-*.json 2>/dev/null | head -1 | xargs cat 2>/dev/null | python3 -m json.tool || echo "No results found. Run 'make bench' first."

# --- Security ---
secret-scan:
	@if command -v gitleaks > /dev/null 2>&1; then \
		gitleaks detect --source . -v; \
	else \
		echo "gitleaks not installed — skipping"; \
	fi

dep-audit:
	@if command -v pip-audit > /dev/null 2>&1; then \
		uv run pip-audit; \
	else \
		echo "pip-audit not installed — skipping"; \
	fi

dockerfile-lint:
	@if command -v hadolint > /dev/null 2>&1; then \
		hadolint Dockerfile; \
	else \
		echo "hadolint not installed — skipping"; \
	fi

# --- Smoke (live) ---
smoke-live-components:
	@echo "Smoke-testing bearer auth on live Whisper endpoint..."
	@WHISPER_HOST=$${WHISPER_HOST:-http://localhost:5000}; \
	TOKEN=$${WHISPER_BENCH_BEARER_TOKEN:-}; \
	echo "1) Unauthenticated request → expect 401"; \
	STATUS=$$(curl -s -o /dev/null -w '%{http_code}' "$$WHISPER_HOST/v1/transcribe" -X POST -F "file=@/dev/null"); \
	if [ "$$STATUS" = "401" ]; then echo "   PASS ($$STATUS)"; else echo "   FAIL ($$STATUS)"; exit 1; fi; \
	echo "2) Health endpoint → expect 200 (no auth required)"; \
	STATUS=$$(curl -s -o /dev/null -w '%{http_code}' "$$WHISPER_HOST/health"); \
	if [ "$$STATUS" = "200" ]; then echo "   PASS ($$STATUS)"; else echo "   FAIL ($$STATUS)"; exit 1; fi; \
	if [ -n "$$TOKEN" ]; then \
		echo "3) Authenticated request → expect 200 or 422"; \
		STATUS=$$(curl -s -o /dev/null -w '%{http_code}' "$$WHISPER_HOST/v1/transcribe" -X POST -F "file=@/dev/null" -H "Authorization: Bearer $$TOKEN"); \
		if [ "$$STATUS" = "200" ] || [ "$$STATUS" = "422" ]; then echo "   PASS ($$STATUS)"; else echo "   FAIL ($$STATUS)"; exit 1; fi; \
	else \
		echo "3) Skipped — WHISPER_BENCH_BEARER_TOKEN not set"; \
	fi; \
	echo "Smoke test complete."

# --- Cleanup ---
clean:
	rm -rf .runtime/results/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

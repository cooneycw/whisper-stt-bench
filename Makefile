.PHONY: install dev lint format test typecheck verify \
       docker-build docker-up docker-down docker-clean docker-logs \
       health bench bench-quick bench-report \
       secret-scan dep-audit dockerfile-lint \
       clean

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

typecheck:
	uv run python -m compileall src tests scripts

test:
	uv run pytest -m "not gpu and not benchmark and not live" -q

verify: lint test typecheck

# --- Docker ---
docker-build:
	docker build --no-cache -t whisper-stt-bench:latest .

docker-up:
	docker compose up --build --force-recreate -d

docker-down:
	docker compose down

docker-clean:
	docker compose down -v --remove-orphans
	docker image prune -f --filter "label=com.docker.compose.project=whisper-stt-bench"

docker-logs:
	docker compose logs -f

health:
	@echo "Waiting for /health..."
	@for i in $$(seq 1 30); do \
		if curl -sf http://localhost:5000/health > /dev/null 2>&1; then \
			echo "Service healthy"; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "Health check timed out"; exit 1

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

# --- Cleanup ---
clean:
	rm -rf .runtime/results/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

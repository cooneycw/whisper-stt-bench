# whisper-stt-bench

GPU Whisper benchmark service — compare self-hosted faster-whisper vs AWS Transcribe.

## Tech Stack

- Python 3.12+ / FastAPI / faster-whisper
- NVIDIA CUDA (RTX 3080 16GB target)
- uv for dependency management
- Docker Compose with NVIDIA runtime

## Project Layout

```text
src/whisper_bench/     Application code (server, transcriber, config)
scripts/               Benchmark runner and corpus preparation
tests/                 Unit tests (CPU-only by default)
.woodpecker/           CI/CD pipeline
```

## Development Commands

```bash
make install       # Install dependencies
make dev           # Install with dev + bench extras
make lint          # Run ruff linter
make test          # Run pytest (excludes gpu/benchmark/live tests)
make typecheck     # Compile-check src/tests/scripts
make format        # Auto-format with ruff
make verify        # Full quality gate (lint + test + typecheck)
```

## Docker / Deployment

```bash
make docker-build  # Build NVIDIA CUDA-based image
make docker-up     # Start with GPU access
make docker-down   # Stop
make health        # Wait for /health endpoint
```

## Benchmark

```bash
make bench         # Full benchmark (all model sizes)
make bench-quick   # Quick benchmark (base model only)
make bench-report  # Show latest results
```

Corpus source: `voice-bot-acs/.runtime/local-talk-artifacts/`
Prepare with: `python scripts/prepare_corpus.py --source <path>`

## Authentication

Bearer token auth protects `/v1/transcribe`. Configure via:
- `WHISPER_BENCH_BEARER_TOKEN` — set token directly, or
- `WHISPER_BENCH_AWS_SECRET_NAME` — fetch from AWS Secrets Manager (key: `whisper_bearer_token`)

When no token is configured, the endpoint is unprotected (dev mode).

```bash
make smoke-live-components  # Verify auth end-to-end against running service
```

## Security Scanning

```bash
make secret-scan       # gitleaks
make dep-audit         # pip-audit
make dockerfile-lint   # hadolint
```

## CI/CD

Pipeline runs in Woodpecker CI via `.woodpecker/ci.yml`:
- lint + secret-scan + dockerfile-lint (parallel)
- test + typecheck + dependency-audit (after lint)
- deploy-remote (main branch only, SSH to 192.168.7.61)

## Deployment Target

- **Host:** 192.168.7.61 (local lab GPU VM)
- **GPU:** NVIDIA RTX 3080 16GB VRAM
- **Deploy:** SSH pull + docker compose rebuild

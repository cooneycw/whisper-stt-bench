# whisper-stt-bench

GPU Whisper benchmark service — compare self-hosted faster-whisper vs AWS Transcribe.

## Tech Stack

- Python 3.12+ / FastAPI / faster-whisper
- NVIDIA CUDA (RTX 3080 16GB target)
- uv for dependency management
- Docker Compose with NVIDIA runtime

## Project Layout

```text
src/whisper_bench/              Application code (server, transcriber, config, auth)
scripts/                        Benchmark runner and corpus preparation
tests/                          Unit tests (CPU-only by default)
infra/secrets-manager-agent/    AWS Secrets Manager Agent sidecar Dockerfile
woodpecker-agent/               Woodpecker CI agent setup for GPU VM
.woodpecker/                    CI/CD pipelines (ci.yml, deploy-local.yml)
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

## Deployment Gateway

**voice-bot-acs is the master deployment entry point for the full stack.**
Do not deploy whisper-stt-bench in isolation during normal operations. Instead,
run `make deploy-all` (or `make deploy-all-stub`) from the `voice-bot-acs`
directory — it chains whisper-stt-bench, personas-service, and voice-bot-acs
in the correct order. The standalone `make deploy` targets here are still
available for debugging or CI, but the preferred workflow is through
voice-bot-acs.

### Multi-Repo Deployment Matrix

| Repository | Woodpecker label | Deployed via | Secrets agent |
|---|---|---|---|
| whisper-stt-bench | `deploy-host=gpu-vm` | voice-bot-acs `deploy-all` | Yes |
| personas-service | `deploy-host=proxVMvoice18` | voice-bot-acs `deploy-all` | Yes |
| voice-bot-acs | `deploy-host=proxVMvoice18` | self (`deploy-all`) | Yes |

**Deploy order:** whisper-stt-bench -> personas-service -> voice-bot-acs

## Docker / Deployment

```bash
make docker-build  # Build NVIDIA CUDA-based image
make docker-up     # Start with GPU access
make docker-down   # Stop
make health        # Wait for /health endpoint
make deploy        # docker-up + health (with secrets sidecar profile)
make deploy-stub   # docker-up + health (no secrets sidecar)
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

Pipeline runs in Woodpecker CI via `.woodpecker/`:
- **ci.yml**: lint + secret-scan + dockerfile-lint (parallel) -> test + typecheck + dependency-audit
- **deploy-local.yml**: main-only local Docker deploy, depends on `ci`, pinned to `deploy-host=gpu-vm` agent

## Deployment Target

- **Host:** 192.168.7.61 (local lab GPU VM)
- **GPU:** NVIDIA RTX 3080 16GB VRAM
- **Agent:** Woodpecker agent with label `deploy-host=gpu-vm` (see `woodpecker-agent/`)
- **Deploy:** Local Docker via Woodpecker agent (no SSH)
- **Secrets:** AWS Secrets Manager Agent sidecar (`infra/secrets-manager-agent/`)

## Woodpecker Agent (GPU VM)

The `woodpecker-agent/` directory contains the agent setup for the GPU VM.
This agent serves all three projects on the host: whisper-stt-bench, voice-bot-acs, personas-service.

```bash
cd woodpecker-agent
./bootstrap-agent.sh          # Fetch creds from AWS SM + start agent
docker compose logs -f        # Check agent logs
```

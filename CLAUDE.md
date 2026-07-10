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

`whisper-stt-bench` owns its own production deployment on `proxVMwhisper43`.
Normal operations use this repo's Woodpecker deploy workflow plus sibling
fanout, not a nested deploy from `voice-bot-acs`.

### Multi-Repo Deployment Matrix

| Repository | Woodpecker label | Deployed via | Secrets agent |
|---|---|---|---|
| whisper-stt-bench | `deploy-host=gpu-vm` | own deploy workflow + sibling fanout | Yes |
| personas-service | `deploy-host=proxVMvoice18` | own deploy workflow + sibling fanout | Yes |
| voice-bot-acs | `deploy-host=proxVMvoice18` | own deploy workflow + sibling fanout | Yes |

Host ownership:

- `whisper-stt-bench` -> `proxVMwhisper43`
- `personas-service` -> `proxVMvoice18`
- `voice-bot-acs` -> `proxVMvoice18`

## Docker / Deployment

```bash
make docker-build  # Build NVIDIA CUDA-based image
make docker-up     # Start with GPU access
make docker-down   # Stop
make deploy        # Production deploy: docker-guard -> docker-up -> health
make health        # Wait for /health endpoint
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

Both pipelines are pinned to the `deploy-host=gpu-vm` agent, so whisper
CI/CD is fully self-contained on proxVMwhisper43 and has no dependency on
any other host being up. (CI was previously pinned to proxVMvoice18; when
that VM went down, whisper pipelines queued forever and blocked deploys.)

Deploy steps run in the `ghcr.io/cooneycw/ci-deploy:3.12` tooling image
(bash/git/make/python3.12/docker CLI + compose). Its Dockerfile lives in
`infra/ci-deploy/`. Pipelines use `pull: false`, so the image must exist
locally on the GPU VM; the agent watchdog rebuilds it if pruned.

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
sudo ./install-watchdog.sh    # Install systemd watchdog timer (5 min)
```

### Agent Watchdog

`woodpecker-agent/watchdog.sh` runs every 5 minutes via systemd timer
(`woodpecker-watchdog.timer`) and auto-recovers known failure modes:

1. **Agent container stopped** -> `docker start`
2. **gRPC queue desync** (agent looks "healthy" but stops claiming jobs;
   pipelines sit "pending" forever) -> `docker restart` (15 min cooldown)
3. **`ci-deploy:3.12` image pruned** by `docker_host_guard.sh` disk cleanup
   -> rebuild from `infra/ci-deploy/`

## CI/CD Troubleshooting

- **Pipeline stuck "pending" (yellow)**: no agent with matching labels is
  claiming it. Check `docker logs woodpecker-agent` for
  `queue: task not found` / `extending pipeline deadline failed`
  (desync -> restart agent), and confirm the pipeline's `labels:` match a
  live agent. Retrigger by pushing a new commit (an orphaned queued task
  may never be picked up even after the agent recovers).
- **deploy-local fails with `error from registry: denied`**: the
  `ci-deploy:3.12` image is missing locally and the registry copy is
  unavailable. Rebuild:
  `docker build -t ghcr.io/cooneycw/ci-deploy:3.12 infra/ci-deploy`
- **Break-glass deploy** (Woodpecker down entirely): SSH to the GPU VM and
  run `make deploy` from `/home/cooneycw/Projects/whisper-stt-bench`.

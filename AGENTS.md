# AGENTS.md

## Scope

These instructions apply to the whole repository.

## Commands

- `make dev` installs the app with development and benchmark tooling.
- `make lint` runs Ruff.
- `make test` runs pytest (excludes gpu/benchmark/live tests).
- `make typecheck` runs a compile check across src, tests, and scripts.
- `make secret-scan` runs `gitleaks` when available.
- `make docker-up` starts the Whisper service with GPU access.
- `make docker-down` stops the Whisper service.
- `make deploy` runs `docker-up` + `health` (with secrets sidecar profile).
- `make deploy-stub` runs `docker-up` + `health` (no secrets sidecar).
- `make health` waits for the `/health` endpoint.

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

### CI Deploy Safety

The CI `deploy-local` workflow (`.woodpecker/deploy-local.yml`) is an ephemeral
smoke test — it starts the Docker stack, runs a health check, and exits. It is
NOT a production deployment. The following safety guards are implemented:

- **Stale-commit guard** — skips deploy if a newer commit has landed on main
- **Label pinning** — `deploy-host=gpu-vm` ensures deploy runs on the GPU VM agent
- **AWS credential injection** — `from_secret` in Woodpecker, never hardcoded

## Expectations

- Keep the Whisper service behind bearer token auth in all non-dev deployments.
- AWS Secrets Manager is the single source of truth for the bearer token (`whisper_bearer_token` key).
- Never commit `.runtime/` files or live credentials.
- The GPU VM Woodpecker agent (`woodpecker-agent/`) serves all three projects; coordinate agent config changes with voice-bot-acs and personas-service.

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

`whisper-stt-bench` owns its own production deploy on `proxVMwhisper43`. A
push to `main` here runs CI, deploys Whisper from its canonical GPU-host
checkout, then fans out Woodpecker deploys to `voice-bot-acs` and
`personas-service` so the ecosystem is rebuilt on every merge.

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

### CI Deploy Safety

The deploy workflow in `.woodpecker/deploy-local.yml` is a production
deployment for the GPU host. The following safety guards are implemented:

- `ci.yml` intentionally runs on `proxVMvoice18`, not the GPU VM, to keep
  inference capacity free for Whisper workloads.
- Because `.woodpecker/deploy-local.yml` has `depends_on: ci`, an outage on
  `proxVMvoice18` blocks the normal deploy path even though deploy-local itself
  runs on `deploy-host=gpu-vm`.
- Break-glass: SSH to `proxVMwhisper43` and run `make deploy` directly from the
  canonical checkout.
- **Stale-commit guard** — skips deploy if a newer commit has landed on main
- **Label pinning** — `deploy-host=gpu-vm` ensures deploy runs on the GPU VM agent
- **Canonical checkout sync** — updates `/home/cooneycw/Projects/whisper-stt-bench` to the target SHA
- **Per-host deploy lock** — prevents overlapping deploys against the Docker daemon
- **Docker disk guard** — prunes reclaimable Docker data before deploy if free space is low
- **GitHub auth bootstrap** — host `~/.config/gh` mounted read-only; deploy script synthesizes `.netrc` from `gh/hosts.yml` before any `git ls-remote` or `git fetch`, failing hard if no auth source exists in CI
- **AWS credential mount** — host `~/.aws` mounted read-only into the deploy runner

## Expectations

- Keep the Whisper service behind bearer token auth in all non-dev deployments.
- AWS Secrets Manager is the single source of truth for the bearer token (`whisper_bearer_token` key).
- Never commit `.runtime/` files or live credentials.
- The GPU VM Woodpecker agent is dedicated to Whisper deploy work. Do not use it to deploy `voice-bot-acs` or `personas-service`.

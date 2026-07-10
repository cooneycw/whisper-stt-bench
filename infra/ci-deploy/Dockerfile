# CI deploy tooling image used by .woodpecker/deploy-local.yml and
# .woodpecker/docker-cleanup.yml (ghcr.io/cooneycw/ci-deploy:3.12).
#
# Provides everything scripts/woodpecker_deploy.sh needs:
#   bash, git, make, curl, python3.12 (stdlib only), docker CLI + compose
#   plugin (daemon access via the mounted /var/run/docker.sock).
#
# Rebuild + publish (from repo root):
#   docker build -t ghcr.io/cooneycw/ci-deploy:3.12 infra/ci-deploy
#   docker push ghcr.io/cooneycw/ci-deploy:3.12
#
# NOTE: docker_host_guard.sh prunes unused images under disk pressure, and
# the pipelines use `pull: false`. If this image disappears from the host,
# the agent watchdog (woodpecker-agent/watchdog.sh) re-pulls it; worst case
# rebuild it with the commands above.
FROM python:3.12-slim-bookworm

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        gnupg \
        make \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        docker-ce-cli \
        docker-compose-plugin \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

CMD ["bash"]

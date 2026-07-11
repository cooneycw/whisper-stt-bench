#!/usr/bin/env bash
# Entrypoint for the AWS Secrets Manager Agent sidecar.
#
# The agent requires its SSRF token via AWS_TOKEN (or AWS_SESSION_TOKEN /
# AWS_CONTAINER_AUTHORIZATION_TOKEN); nothing generates that token file by
# itself. Generate a random token into the shared awssmatoken volume so the
# whisper-bench app (which reads AWS_TOKEN=file:///run/awssmatoken/token)
# and the agent agree on it, then exec the agent.
set -euo pipefail

TOKEN_FILE="${AWS_TOKEN_FILE_PATH:-/run/awssmatoken/token}"

mkdir -p "$(dirname "$TOKEN_FILE")"
if [ ! -s "$TOKEN_FILE" ]; then
    od -An -tx1 -N32 /dev/urandom | tr -d ' \n' > "$TOKEN_FILE"
fi
chmod 0644 "$TOKEN_FILE"

export AWS_TOKEN="file://$TOKEN_FILE"

exec /usr/local/bin/secrets-manager-agent "$@"

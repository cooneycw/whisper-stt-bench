#!/usr/bin/env bash
# Bootstrap the Woodpecker agent on the GPU VM.
#
# Fetches WOODPECKER_AGENT_SECRET and WOODPECKER_SERVER from AWS Secrets
# Manager and writes agent.env, then starts the agent container.
#
# Usage:
#   ./bootstrap-agent.sh [--secret-name essent-ai] [--region us-east-1]

set -euo pipefail

SECRET_NAME="${1:-essent-ai}"
REGION="${2:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Fetching Woodpecker credentials from AWS Secrets Manager ($SECRET_NAME)..."

SECRET_JSON=$(aws secretsmanager get-secret-value \
    --secret-id "$SECRET_NAME" \
    --region "$REGION" \
    --query SecretString \
    --output text)

AGENT_SECRET=$(echo "$SECRET_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['WOODPECKER_AGENT_SECRET'])")
SERVER=$(echo "$SECRET_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['WOODPECKER_HOST'])")

cat > "$SCRIPT_DIR/agent.env" <<EOF
WOODPECKER_AGENT_SECRET=$AGENT_SECRET
WOODPECKER_SERVER=$SERVER
EOF

echo "agent.env written."
echo "Starting Woodpecker agent..."

docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d

echo "Agent started. Verify with: docker logs woodpecker-agent-gpu-vm"

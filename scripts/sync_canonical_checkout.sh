#!/usr/bin/env bash
set -euo pipefail

if [ $# -gt 0 ]; then
  HOST_CANONICAL_WORKSPACE="$1"
fi

: "${HOST_CANONICAL_WORKSPACE:?HOST_CANONICAL_WORKSPACE is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
HOST_PROJECTS_ROOT="$(dirname "$HOST_CANONICAL_WORKSPACE")"

# Clean up orphaned netrc files from crashed deploys (>60min old)
find "$HOST_PROJECTS_ROOT" -maxdepth 1 -name '.ci-netrc-*' -mmin +60 -delete 2>/dev/null || true

NETRC_CONTENT=""
NETRC_HOST_PATH=""
GIT_NETRC_ARGS=()

for p in /root/.netrc "$HOME/.netrc"; do
  if [ -f "$p" ]; then
    NETRC_CONTENT="$(cat "$p")"
    echo "Found .netrc at $p"
    NETRC_HOST_PATH="$HOST_PROJECTS_ROOT/.ci-netrc-$$"
    GIT_NETRC_ARGS=(-v "$NETRC_HOST_PATH:/root/.netrc:ro")
    break
  fi
done

cleanup() {
  if [ -n "$NETRC_HOST_PATH" ]; then
    docker run --rm \
      -v "$HOST_PROJECTS_ROOT:$HOST_PROJECTS_ROOT" \
      --entrypoint sh alpine -c "rm -f '$NETRC_HOST_PATH'" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

if [ -n "$NETRC_CONTENT" ]; then
  docker run --rm \
    -v "$HOST_PROJECTS_ROOT:$HOST_PROJECTS_ROOT" \
    -e NETRC_CONTENT="$NETRC_CONTENT" \
    -e NETRC_PATH="$NETRC_HOST_PATH" \
    --entrypoint sh alpine -c '
      printf "%s\n" "$NETRC_CONTENT" > "$NETRC_PATH"
      chmod 600 "$NETRC_PATH"
    '
else
  echo "No .netrc found; attempting anonymous git fetch from origin"
fi

docker run --rm \
  -v "$HOST_PROJECTS_ROOT:$HOST_PROJECTS_ROOT" \
  "${GIT_NETRC_ARGS[@]}" \
  -w "$HOST_CANONICAL_WORKSPACE" \
  -e DEPLOY_SHA="$DEPLOY_SHA" \
  -e DEPLOY_BRANCH="$DEPLOY_BRANCH" \
  --entrypoint sh alpine/git -c '
    if [ ! -d .git ]; then
      echo "FATAL: canonical checkout missing at $(pwd)" >&2
      exit 1
    fi
    git config --global --add safe.directory "*"
    find .git -maxdepth 1 -name "*.lock" -delete 2>/dev/null || true
    if ! git fsck --no-dangling --connectivity-only 2>/dev/null; then
      echo "Corrupted repo detected; pruning broken objects..."
      rm -f .git/shallow
      git fsck --no-dangling 2>&1 | grep "missing\|broken" | awk "{print \$NF}" | while read obj; do
        obj_dir=$(printf "%s" "$obj" | cut -c1-2)
        obj_file=$(printf "%s" "$obj" | cut -c3-)
        rm -f ".git/objects/$obj_dir/$obj_file" 2>/dev/null || true
      done
      git reflog expire --expire=now --all 2>/dev/null || true
      git gc --prune=now 2>/dev/null || true
    fi
    git fetch origin "$DEPLOY_BRANCH"
    git checkout -B "$DEPLOY_BRANCH"
    git reset --hard "$DEPLOY_SHA"
  '

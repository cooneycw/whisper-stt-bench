#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: $0 <url> [--max-wait seconds] [--body-match pattern]" >&2
    exit 2
fi

URL="$1"
shift
MAX_WAIT=60
BODY_MATCH='"status"'

while [ $# -gt 0 ]; do
    case "$1" in
        --max-wait)
            MAX_WAIT="$2"
            shift 2
            ;;
        --body-match)
            BODY_MATCH="$2"
            shift 2
            ;;
        *)
            echo "unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

START_TS=$(date +%s)
ATTEMPT=1

while true; do
    HTTP_CODE="$(curl -sS -o /tmp/health-check.out -w '%{http_code}' "$URL" || true)"
    BODY="$(cat /tmp/health-check.out 2>/dev/null || true)"
    if [ "$HTTP_CODE" = "200" ] && printf '%s' "$BODY" | tr -d ' \n\r\t' | grep -q "$BODY_MATCH"; then
        echo "health check passed on attempt $ATTEMPT"
        exit 0
    fi

    NOW_TS=$(date +%s)
    if [ $((NOW_TS - START_TS)) -ge "$MAX_WAIT" ]; then
        echo "health check timed out after ${MAX_WAIT}s (last HTTP $HTTP_CODE)" >&2
        [ -n "$BODY" ] && echo "last response: $BODY" >&2
        exit 1
    fi

    echo "waiting for health endpoint (attempt $ATTEMPT, HTTP $HTTP_CODE)"
    ATTEMPT=$((ATTEMPT + 1))
    sleep 2
done

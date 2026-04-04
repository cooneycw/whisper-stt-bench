"""Bearer token authentication for the Whisper service."""

from __future__ import annotations

import hmac
import json
import logging

from fastapi import HTTPException, Request

from whisper_bench.config import settings

logger = logging.getLogger(__name__)

_bearer_token: str = ""


def load_bearer_token() -> None:
    """Load the bearer token from config or AWS Secrets Manager.

    Priority: WHISPER_BENCH_BEARER_TOKEN env var > AWS Secrets Manager lookup.
    """
    global _bearer_token

    if settings.bearer_token:
        _bearer_token = settings.bearer_token
        logger.info("Bearer token loaded from environment")
        return

    if settings.aws_secret_name:
        _bearer_token = _fetch_from_secrets_manager(
            settings.aws_secret_name,
            settings.aws_region,
        )
        logger.info("Bearer token loaded from AWS Secrets Manager")
        return

    logger.warning("No bearer token configured — /v1/transcribe is UNPROTECTED")


def _fetch_from_secrets_manager(secret_name: str, region: str) -> str:
    """Retrieve the bearer token from AWS Secrets Manager."""
    import boto3

    client = boto3.client("secretsmanager", region_name=region)
    resp = client.get_secret_value(SecretId=secret_name)
    payload = json.loads(resp["SecretString"])
    token = payload.get("whisper_bearer_token", "")
    if not token:
        raise RuntimeError(
            f"Secret '{secret_name}' missing key 'whisper_bearer_token'"
        )
    return token


async def verify_bearer_token(request: Request) -> None:
    """Validate the Authorization header using constant-time comparison.

    Skipped when no token is configured (dev/local mode).
    """
    if not _bearer_token:
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    provided = auth_header[7:]  # strip "Bearer "
    if not hmac.compare_digest(provided, _bearer_token):
        raise HTTPException(status_code=401, detail="Invalid bearer token")

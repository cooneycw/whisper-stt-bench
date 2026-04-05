"""Bearer token authentication for the Whisper service."""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import HTTPException, Request

from whisper_bench.config import settings

logger = logging.getLogger(__name__)

_bearer_token: str = ""
DEFAULT_AGENT_ENDPOINT = "http://127.0.0.1:2773"
DEFAULT_AGENT_TIMEOUT = 5.0
DEFAULT_AGENT_ATTEMPTS = 10
DEFAULT_AGENT_RETRY_DELAY = 0.5


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
        token = _fetch_from_agent(settings.aws_secret_name)
        if token:
            _bearer_token = token
            logger.info("Bearer token loaded from AWS Secrets Manager agent")
            return

        _bearer_token = _fetch_from_secrets_manager(
            settings.aws_secret_name,
            settings.aws_region,
        )
        logger.info("Bearer token loaded from AWS Secrets Manager")
        return

    logger.warning("No bearer token configured — /v1/transcribe is UNPROTECTED")


def _agent_endpoint() -> str:
    return os.getenv(
        "AWS_SECRETSMANAGER_AGENT_ENDPOINT",
        DEFAULT_AGENT_ENDPOINT,
    ).rstrip("/")


def _agent_attempts() -> int:
    raw = os.getenv("AWS_SECRETSMANAGER_AGENT_ATTEMPTS", str(DEFAULT_AGENT_ATTEMPTS))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_AGENT_ATTEMPTS


def _agent_retry_delay() -> float:
    raw = os.getenv(
        "AWS_SECRETSMANAGER_AGENT_RETRY_DELAY",
        str(DEFAULT_AGENT_RETRY_DELAY),
    )
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_AGENT_RETRY_DELAY


def _agent_timeout() -> float:
    raw = os.getenv("AWS_SECRETSMANAGER_AGENT_TIMEOUT", str(DEFAULT_AGENT_TIMEOUT))
    try:
        return max(0.1, float(raw))
    except ValueError:
        return DEFAULT_AGENT_TIMEOUT


def _agent_token() -> str:
    for raw in (
        os.getenv("AWS_SECRETSMANAGER_TOKEN", ""),
        os.getenv("AWS_TOKEN", ""),
    ):
        token = raw.strip()
        if not token:
            continue
        if token.startswith("file://"):
            try:
                return Path(token[len("file://") :]).read_text(encoding="utf-8").strip()
            except OSError:
                return ""
        return token

    for fallback in (
        Path("/run/awssmatoken/token"),
        Path("/var/run/awssmatoken"),
    ):
        try:
            return fallback.read_text(encoding="utf-8").strip()
        except OSError:
            continue

    return ""


def _fetch_from_agent(secret_name: str) -> str:
    attempts = _agent_attempts()
    retry_delay = _agent_retry_delay()
    timeout = _agent_timeout()

    for attempt in range(1, attempts + 1):
        token = _agent_token()
        if not token:
            if attempt < attempts:
                time.sleep(retry_delay)
            continue

        secret_id = urllib.parse.quote(secret_name, safe="")
        url = f"{_agent_endpoint()}/secretsmanager/get?secretId={secret_id}"
        request = urllib.request.Request(
            url,
            headers={"X-Aws-Parameters-Secrets-Token": token},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            secret_string = payload.get("SecretString", "{}")
            data = json.loads(secret_string)
            token_value = data.get("whisper_bearer_token", "")
            if token_value:
                return str(token_value)
            raise RuntimeError(
                f"Secret '{secret_name}' missing key 'whisper_bearer_token'"
            )
        except (
            OSError,
            TimeoutError,
            RuntimeError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ) as exc:
            if attempt == attempts:
                logger.warning(
                    "Could not fetch AWS secret '%s' from agent at %s: %s",
                    secret_name,
                    _agent_endpoint(),
                    exc,
                )
                break
            time.sleep(retry_delay)

    return ""


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

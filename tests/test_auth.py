"""Tests for bearer-token resolution helpers."""

from __future__ import annotations

import json
from pathlib import Path

from whisper_bench import auth


class _FakeResponse:
    def __init__(self, payload: dict[str, str]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_agent_token_reads_file_url_env(monkeypatch, tmp_path: Path):
    token_path = tmp_path / "token"
    token_path.write_text("agent-token\n", encoding="utf-8")

    monkeypatch.setenv("AWS_TOKEN", f"file://{token_path}")
    monkeypatch.delenv("AWS_SECRETSMANAGER_TOKEN", raising=False)

    assert auth._agent_token() == "agent-token"


def test_fetch_from_agent_parses_secret(monkeypatch):
    monkeypatch.setattr(auth, "_agent_token", lambda: "secret-token")
    monkeypatch.setenv("AWS_SECRETSMANAGER_AGENT_ENDPOINT", "http://127.0.0.1:2773")

    def fake_urlopen(request, timeout):
        assert request.full_url.endswith("secretId=voice-bot")
        headers = dict(request.header_items())
        assert headers["X-aws-parameters-secrets-token"] == "secret-token"
        assert timeout == auth.DEFAULT_AGENT_TIMEOUT
        return _FakeResponse(
            {"SecretString": json.dumps({"whisper_bearer_token": "bearer-123"})}
        )

    monkeypatch.setattr(auth.urllib.request, "urlopen", fake_urlopen)

    assert auth._fetch_from_agent("voice-bot") == "bearer-123"


def test_load_bearer_token_prefers_agent_before_boto3(monkeypatch):
    monkeypatch.setattr(auth.settings, "bearer_token", "")
    monkeypatch.setattr(auth.settings, "aws_secret_name", "voice-bot")
    monkeypatch.setattr(auth.settings, "aws_region", "us-east-1")
    monkeypatch.setattr(auth, "_fetch_from_agent", lambda secret_name: "agent-token")
    def fail_fetch(secret_name, region):
        raise AssertionError("boto3 fallback should not run")

    monkeypatch.setattr(auth, "_fetch_from_secrets_manager", fail_fetch)

    auth._bearer_token = ""
    auth.load_bearer_token()

    assert auth._bearer_token == "agent-token"


def test_load_bearer_token_falls_back_to_boto3(monkeypatch):
    monkeypatch.setattr(auth.settings, "bearer_token", "")
    monkeypatch.setattr(auth.settings, "aws_secret_name", "voice-bot")
    monkeypatch.setattr(auth.settings, "aws_region", "us-east-1")
    monkeypatch.setattr(auth, "_fetch_from_agent", lambda secret_name: "")
    monkeypatch.setattr(
        auth,
        "_fetch_from_secrets_manager",
        lambda secret_name, region: "boto3-token",
    )

    auth._bearer_token = ""
    auth.load_bearer_token()

    assert auth._bearer_token == "boto3-token"

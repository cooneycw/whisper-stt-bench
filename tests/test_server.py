"""Tests for the FastAPI server (no model loading required)."""

from __future__ import annotations

import io
from unittest.mock import patch

from fastapi import Depends, FastAPI, UploadFile
from fastapi.testclient import TestClient

from whisper_bench import auth


def _build_test_app() -> FastAPI:
    """Build a minimal FastAPI app matching server routes, without model loading."""

    test_app = FastAPI()

    @test_app.get("/health")
    async def health():
        return {"status": "loading", "model": "base"}

    @test_app.get("/v1/models")
    async def list_models():
        from whisper_bench.transcriber import Transcriber

        return [m.__dict__ for m in Transcriber.available_models()]

    @test_app.post("/v1/transcribe", dependencies=[Depends(auth.verify_bearer_token)])
    async def transcribe(file: UploadFile):
        return {"text": "hello"}

    return test_app


class TestHealthEndpoint:
    def test_health_returns_200(self):
        app = _build_test_app()
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "model" in data

    def test_health_shows_status(self):
        app = _build_test_app()
        with TestClient(app) as client:
            response = client.get("/health")
            data = response.json()
            assert data["status"] in ("ok", "loading")


class TestModelsEndpoint:
    def test_list_models(self):
        app = _build_test_app()
        with TestClient(app) as client:
            response = client.get("/v1/models")
            assert response.status_code == 200
            models = response.json()
            assert isinstance(models, list)
            assert len(models) > 0
            assert any(m["name"] == "base" for m in models)


class TestBearerAuth:
    """Bearer token authentication tests for /v1/transcribe."""

    def _upload(self, client: TestClient, headers: dict | None = None):
        """POST a dummy WAV to /v1/transcribe."""
        return client.post(
            "/v1/transcribe",
            files={"file": ("test.wav", io.BytesIO(b"RIFF"), "audio/wav")},
            headers=headers or {},
        )

    def test_no_token_configured_allows_request(self):
        """When no token is set, requests pass through (dev mode)."""
        with patch.object(auth, "_bearer_token", ""):
            app = _build_test_app()
            with TestClient(app) as client:
                resp = self._upload(client)
                assert resp.status_code == 200

    def test_valid_token_allows_request(self):
        with patch.object(auth, "_bearer_token", "secret-token-123"):
            app = _build_test_app()
            with TestClient(app) as client:
                resp = self._upload(
                    client, {"Authorization": "Bearer secret-token-123"}
                )
                assert resp.status_code == 200

    def test_missing_token_returns_401(self):
        with patch.object(auth, "_bearer_token", "secret-token-123"):
            app = _build_test_app()
            with TestClient(app) as client:
                resp = self._upload(client)
                assert resp.status_code == 401

    def test_wrong_token_returns_401(self):
        with patch.object(auth, "_bearer_token", "secret-token-123"):
            app = _build_test_app()
            with TestClient(app) as client:
                resp = self._upload(client, {"Authorization": "Bearer wrong"})
                assert resp.status_code == 401

    def test_health_unprotected_when_token_set(self):
        """Health endpoint must remain open regardless of auth config."""
        with patch.object(auth, "_bearer_token", "secret-token-123"):
            app = _build_test_app()
            with TestClient(app) as client:
                resp = client.get("/health")
                assert resp.status_code == 200

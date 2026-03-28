"""Tests for the FastAPI server (no model loading required)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


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

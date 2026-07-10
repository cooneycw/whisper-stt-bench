"""Tests for the FastAPI server (no model loading required)."""

from __future__ import annotations

import io
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI, UploadFile
from httpx import ASGITransport, AsyncClient

from whisper_bench import auth

pytestmark = pytest.mark.anyio


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


@asynccontextmanager
async def _client(app: FastAPI):
    """Create an async test client compatible with the installed Starlette stack."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


class TestHealthEndpoint:
    async def test_health_returns_200(self):
        app = _build_test_app()
        async with _client(app) as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "model" in data

    async def test_health_shows_status(self):
        app = _build_test_app()
        async with _client(app) as client:
            response = await client.get("/health")
            data = response.json()
            assert data["status"] in ("ok", "loading")


class TestModelsEndpoint:
    async def test_list_models(self):
        app = _build_test_app()
        async with _client(app) as client:
            response = await client.get("/v1/models")
            assert response.status_code == 200
            models = response.json()
            assert isinstance(models, list)
            assert len(models) > 0
            assert any(m["name"] == "base" for m in models)

class _FakeTranscriber:
    """Records the prompt and returns a fixed result with confidence fields."""

    def __init__(self):
        self.last_prompt: str | None = "UNSET"

    def transcribe(self, audio_bytes, initial_prompt=None):
        from whisper_bench.transcriber import Segment, TranscriptionResult

        self.last_prompt = initial_prompt
        return TranscriptionResult(
            text="hello",
            language="en",
            duration_audio_s=1.0,
            duration_process_s=0.1,
            rtf=0.1,
            segments=[
                Segment(
                    start=0.0,
                    end=1.0,
                    text="hello",
                    avg_logprob=-0.2,
                    no_speech_prob=0.01,
                )
            ],
        )


class TestTranscribeContract:
    """API contract for issue #23: initial_prompt + segment confidence fields."""

    async def _post(self, client: AsyncClient, data: dict | None = None):
        return await client.post(
            "/v1/transcribe",
            files={"file": ("test.wav", io.BytesIO(b"RIFF"), "audio/wav")},
            data=data or {},
        )

    async def test_forwards_prompt_and_returns_confidence(self):
        from whisper_bench import server

        fake = _FakeTranscriber()
        with patch.object(server, "transcriber", fake), patch.object(
            auth, "_bearer_token", ""
        ):
            async with _client(server.app) as client:
                resp = await self._post(client, {"initial_prompt": "Alice Bob"})
                assert resp.status_code == 200
                assert fake.last_prompt == "Alice Bob"
                seg = resp.json()["segments"][0]
                assert seg["avg_logprob"] == -0.2
                assert seg["no_speech_prob"] == 0.01

    async def test_without_prompt_stays_compatible(self):
        from whisper_bench import server

        fake = _FakeTranscriber()
        with patch.object(server, "transcriber", fake), patch.object(
            auth, "_bearer_token", ""
        ):
            async with _client(server.app) as client:
                resp = await self._post(client)
                assert resp.status_code == 200
                assert fake.last_prompt is None

    async def test_openapi_documents_new_fields(self):
        from whisper_bench import server

        schema = server.app.openapi()
        segment = schema["components"]["schemas"]["TranscribeSegment"]["properties"]
        assert "avg_logprob" in segment
        assert "no_speech_prob" in segment
        request_body = (
            schema["paths"]["/v1/transcribe"]["post"]["requestBody"]["content"][
                "multipart/form-data"
            ]["schema"]["$ref"]
        )
        form_name = request_body.rsplit("/", 1)[-1]
        form_props = schema["components"]["schemas"][form_name]["properties"]
        assert "initial_prompt" in form_props


class TestBearerAuth:
    """Bearer token authentication tests for /v1/transcribe."""

    async def _upload(self, client: AsyncClient, headers: dict | None = None):
        """POST a dummy WAV to /v1/transcribe."""
        return await client.post(
            "/v1/transcribe",
            files={"file": ("test.wav", io.BytesIO(b"RIFF"), "audio/wav")},
            headers=headers or {},
        )

    async def test_no_token_configured_allows_request(self):
        """When no token is set, requests pass through (dev mode)."""
        with patch.object(auth, "_bearer_token", ""):
            app = _build_test_app()
            async with _client(app) as client:
                resp = await self._upload(client)
                assert resp.status_code == 200

    async def test_valid_token_allows_request(self):
        with patch.object(auth, "_bearer_token", "secret-token-123"):
            app = _build_test_app()
            async with _client(app) as client:
                resp = await self._upload(
                    client, {"Authorization": "Bearer secret-token-123"}
                )
                assert resp.status_code == 200

    async def test_missing_token_returns_401(self):
        with patch.object(auth, "_bearer_token", "secret-token-123"):
            app = _build_test_app()
            async with _client(app) as client:
                resp = await self._upload(client)
                assert resp.status_code == 401

    async def test_wrong_token_returns_401(self):
        with patch.object(auth, "_bearer_token", "secret-token-123"):
            app = _build_test_app()
            async with _client(app) as client:
                resp = await self._upload(client, {"Authorization": "Bearer wrong"})
                assert resp.status_code == 401

    async def test_health_unprotected_when_token_set(self):
        """Health endpoint must remain open regardless of auth config."""
        with patch.object(auth, "_bearer_token", "secret-token-123"):
            app = _build_test_app()
            async with _client(app) as client:
                resp = await client.get("/health")
                assert resp.status_code == 200

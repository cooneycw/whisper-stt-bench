"""FastAPI application for the Whisper benchmark service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, UploadFile
from pydantic import BaseModel

from whisper_bench.config import settings
from whisper_bench.transcriber import ModelInfo, Transcriber, TranscriptionResult

logger = logging.getLogger(__name__)

transcriber: Transcriber | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global transcriber
    logging.basicConfig(level=settings.log_level)
    logger.info(
        "Loading whisper model=%s device=%s compute=%s",
        settings.whisper_model,
        settings.whisper_device,
        settings.whisper_compute_type,
    )
    transcriber = Transcriber(
        model_size=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    logger.info("Model loaded")
    yield
    transcriber = None


app = FastAPI(title="whisper-stt-bench", version="0.1.0", lifespan=lifespan)


class HealthResponse(BaseModel):
    status: str
    model: str


class TranscribeResponse(BaseModel):
    text: str
    language: str
    duration_audio_s: float
    duration_process_s: float
    rtf: float
    segments: list[dict[str, Any]]


@app.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok" if transcriber is not None else "loading",
        model=settings.whisper_model,
    )


@app.get("/v1/models")
async def list_models() -> list[ModelInfo]:
    return Transcriber.available_models()


@app.post("/v1/transcribe")
async def transcribe(file: UploadFile) -> TranscribeResponse:
    assert transcriber is not None, "Model not loaded"
    audio_bytes = await file.read()
    result: TranscriptionResult = transcriber.transcribe(audio_bytes)
    return TranscribeResponse(
        text=result.text,
        language=result.language,
        duration_audio_s=result.duration_audio_s,
        duration_process_s=result.duration_process_s,
        rtf=result.rtf,
        segments=[
            {"start": s.start, "end": s.end, "text": s.text} for s in result.segments
        ],
    )

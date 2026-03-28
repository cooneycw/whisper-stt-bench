"""faster-whisper wrapper for transcription and model management."""

from __future__ import annotations

import io
import time
import wave
from dataclasses import dataclass, field

import numpy as np
from faster_whisper import WhisperModel

AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large-v3", "distil-large-v3"]


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration_audio_s: float
    duration_process_s: float
    rtf: float
    segments: list[Segment] = field(default_factory=list)


@dataclass
class ModelInfo:
    name: str
    loaded: bool


class Transcriber:
    """Wraps faster-whisper for batch transcription."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        self.model_size = model_size
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_bytes: bytes) -> TranscriptionResult:
        """Transcribe audio bytes (WAV or raw PCM16 mono 16kHz).

        Returns TranscriptionResult with text, timing, and segments.
        """
        audio_array = self._decode_audio(audio_bytes)
        duration_audio = len(audio_array) / 16000.0

        t0 = time.perf_counter()
        segments_iter, info = self.model.transcribe(audio_array, beam_size=5)
        segments = []
        text_parts = []
        for seg in segments_iter:
            segments.append(Segment(start=seg.start, end=seg.end, text=seg.text.strip()))
            text_parts.append(seg.text.strip())
        elapsed = time.perf_counter() - t0

        return TranscriptionResult(
            text=" ".join(text_parts),
            language=info.language,
            duration_audio_s=duration_audio,
            duration_process_s=elapsed,
            rtf=elapsed / duration_audio if duration_audio > 0 else 0.0,
            segments=segments,
        )

    @staticmethod
    def available_models() -> list[ModelInfo]:
        return [ModelInfo(name=m, loaded=False) for m in AVAILABLE_MODELS]

    @staticmethod
    def _decode_audio(audio_bytes: bytes) -> np.ndarray:
        """Decode WAV or raw PCM16 mono 16kHz to float32 numpy array."""
        try:
            buf = io.BytesIO(audio_bytes)
            with wave.open(buf, "rb") as wf:
                assert wf.getnchannels() == 1, f"Expected mono, got {wf.getnchannels()} channels"
                assert wf.getsampwidth() == 2, f"Expected 16-bit, got {wf.getsampwidth() * 8}-bit"
                frames = wf.readframes(wf.getnframes())
                arr = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                return arr
        except (wave.Error, EOFError, AssertionError):
            # Assume raw PCM16 mono 16kHz
            arr = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            return arr

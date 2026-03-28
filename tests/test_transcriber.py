"""Tests for the transcriber module (CPU-only, no GPU required)."""

from __future__ import annotations

import io
import wave

import numpy as np


def _make_wav(samples: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Create a WAV file in memory from float32 samples."""
    pcm = (samples * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _make_pcm(samples: np.ndarray) -> bytes:
    """Create raw PCM16 bytes from float32 samples."""
    pcm = (samples * 32767).astype(np.int16)
    return pcm.tobytes()


class TestDecodeAudio:
    """Test audio decoding without loading a Whisper model."""

    def test_decode_wav(self):
        from whisper_bench.transcriber import Transcriber

        # 1 second of silence
        samples = np.zeros(16000, dtype=np.float32)
        wav_bytes = _make_wav(samples)

        result = Transcriber._decode_audio(wav_bytes)
        assert result.shape == (16000,)
        assert result.dtype == np.float32
        np.testing.assert_allclose(result, 0.0, atol=1e-4)

    def test_decode_pcm(self):
        from whisper_bench.transcriber import Transcriber

        samples = np.zeros(16000, dtype=np.float32)
        pcm_bytes = _make_pcm(samples)

        result = Transcriber._decode_audio(pcm_bytes)
        assert result.shape == (16000,)
        assert result.dtype == np.float32

    def test_decode_wav_with_tone(self):
        from whisper_bench.transcriber import Transcriber

        # 440Hz sine wave, 0.5 seconds
        t = np.linspace(0, 0.5, 8000, dtype=np.float32)
        samples = 0.5 * np.sin(2 * np.pi * 440 * t)
        wav_bytes = _make_wav(samples)

        result = Transcriber._decode_audio(wav_bytes)
        assert result.shape == (8000,)
        assert np.max(np.abs(result)) > 0.1  # Not silence


class TestAvailableModels:
    def test_lists_models(self):
        from whisper_bench.transcriber import Transcriber

        models = Transcriber.available_models()
        assert len(models) > 0
        names = [m.name for m in models]
        assert "base" in names
        assert "large-v3" in names


class TestComputeWer:
    def test_identical(self):
        from scripts.benchmark import compute_wer

        assert compute_wer("hello world", "hello world") == 0.0

    def test_completely_wrong(self):
        from scripts.benchmark import compute_wer

        wer = compute_wer("hello world", "foo bar")
        assert wer > 0.0

    def test_empty_reference(self):
        from scripts.benchmark import compute_wer

        assert compute_wer("", "some text") == 0.0

    def test_partial_match(self):
        from scripts.benchmark import compute_wer

        wer = compute_wer("the quick brown fox", "the quick brown")
        assert 0 < wer < 1.0

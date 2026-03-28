# whisper-stt-bench

GPU Whisper benchmark service — compare self-hosted [faster-whisper](https://github.com/SYSTRAN/faster-whisper) vs AWS Transcribe.

## Overview

FastAPI service + benchmark tooling for evaluating Whisper model performance on a local GPU (NVIDIA RTX 3080 16GB). Uses audio corpus from voice-bot-acs local-talk-artifacts.

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Readiness check |
| `/v1/models` | GET | List available Whisper models |
| `/v1/transcribe` | POST | Transcribe uploaded audio (WAV/PCM) |

### Benchmark Metrics

- **WER** — Word Error Rate against reference transcripts
- **RTF** — Real-Time Factor (processing time / audio duration)
- **Latency** — Time-to-result per utterance
- **GPU Memory** — Peak VRAM usage per model size

## Quick Start

```bash
# Install
make dev

# Run service locally
uvicorn whisper_bench.server:app --port 5000

# Prepare corpus from voice-bot-acs artifacts
python scripts/prepare_corpus.py --source ../voice-bot-acs/.runtime/local-talk-artifacts

# Run benchmark (single model)
make bench-quick

# Run full benchmark (all model sizes)
make bench
```

## Docker (GPU)

```bash
make docker-build
make docker-up
make health
```

Requires NVIDIA Container Toolkit (`nvidia-docker2`).

## Development

```bash
make dev          # Install with dev extras
make lint         # Ruff linter
make test         # Pytest (CPU-only tests)
make typecheck    # Compile check
make verify       # All quality gates
```

## VM Target

- **Host:** 192.168.7.61
- **GPU:** NVIDIA RTX 3080 16GB VRAM
- **RAM:** 32GB, 6 CPU cores
- **OS:** Ubuntu 24.04, CUDA 13.0

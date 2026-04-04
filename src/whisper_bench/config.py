"""Application settings via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WHISPER_BENCH_",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 5000
    log_level: str = "INFO"

    # Whisper model
    whisper_model: str = "distil-large-v3"
    whisper_device: str = "auto"  # auto | cuda | cpu
    whisper_compute_type: str = "auto"  # auto | float16 | int8 | float32

    # Corpus
    corpus_dir: str = ""  # path to directory with WAV/PCM files

    # Results
    results_dir: str = ".runtime/results"

    # Auth
    bearer_token: str = ""  # set directly or fetched from Secrets Manager
    aws_secret_name: str = ""  # AWS Secrets Manager secret name
    aws_region: str = "us-east-1"


settings = Settings()

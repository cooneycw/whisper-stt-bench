"""Tests for Woodpecker fanout repo resolution."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "woodpecker_fanout.py"
SPEC = importlib.util.spec_from_file_location("woodpecker_fanout", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
fanout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fanout)


def test_parse_repo_ids_parses_mapping_string():
    repo_ids = fanout.parse_repo_ids(
        "cooneycw/voice-bot-acs=6,cooneycw/whisper-stt-bench=7"
    )

    assert repo_ids == {
        "cooneycw/voice-bot-acs": 6,
        "cooneycw/whisper-stt-bench": 7,
    }


def test_parse_repo_ids_rejects_invalid_entries():
    with pytest.raises(SystemExit, match="Invalid repo id mapping"):
        fanout.parse_repo_ids("cooneycw/voice-bot-acs")


def test_resolve_repos_uses_configured_ids_without_api_lookup(monkeypatch):
    def fail_repo_map(base_url: str, token: str) -> dict[str, dict[str, object]]:
        raise AssertionError("repo discovery should not run when repo ids are configured")

    monkeypatch.setattr(fanout, "repo_map", fail_repo_map)

    repos = fanout.resolve_repos(
        "https://woodpecker.example.com",
        "token-123",
        ["cooneycw/voice-bot-acs", "cooneycw/personas-service"],
        {"cooneycw/voice-bot-acs": 6, "cooneycw/personas-service": 8},
    )

    assert repos == {
        "cooneycw/voice-bot-acs": {"full_name": "cooneycw/voice-bot-acs", "id": 6},
        "cooneycw/personas-service": {
            "full_name": "cooneycw/personas-service",
            "id": 8,
        },
    }


def test_resolve_repos_falls_back_to_api_lookup(monkeypatch):
    monkeypatch.setattr(
        fanout,
        "repo_map",
        lambda base_url, token: {
            "cooneycw/personas-service": {"full_name": "cooneycw/personas-service", "id": 8}
        },
    )

    repos = fanout.resolve_repos(
        "https://woodpecker.example.com",
        "token-123",
        ["cooneycw/personas-service"],
        {},
    )

    assert repos == {
        "cooneycw/personas-service": {"full_name": "cooneycw/personas-service", "id": 8}
    }

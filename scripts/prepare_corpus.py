#!/usr/bin/env python3
"""Extract and prepare test audio corpus from voice-bot-acs local-talk-artifacts.

Copies WAV files and reference transcripts into a standalone corpus directory
that can be used independently of voice-bot-acs.

Usage:
    python scripts/prepare_corpus.py \
        --source ../voice-bot-acs/.runtime/local-talk-artifacts \
        --output .runtime/corpus
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def prepare_corpus(source_dir: str, output_dir: str, max_files: int | None = None) -> None:
    """Copy WAV files and extract reference transcripts into a corpus directory."""
    src = Path(source_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        print(f"Source directory not found: {src}")
        return

    count = 0
    for run_dir in sorted(src.iterdir()):
        if not run_dir.is_dir():
            continue
        if max_files and count >= max_files:
            break

        wav_file = run_dir / "inbound.wav"
        pcm_file = run_dir / "inbound.raw.pcm"
        audio_file = wav_file if wav_file.exists() else (pcm_file if pcm_file.exists() else None)

        if audio_file is None:
            continue

        # Create output subdirectory
        dest_dir = out / run_dir.name
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Copy audio
        shutil.copy2(audio_file, dest_dir / audio_file.name)

        # Extract and save reference transcript
        messages_file = run_dir / "messages.json"
        if messages_file.exists():
            try:
                messages = json.loads(messages_file.read_text())
                user_texts = [
                    m["text"] for m in messages if m.get("sender") == "user" and m.get("text")
                ]
                reference = " ".join(user_texts)
                (dest_dir / "reference.txt").write_text(reference)
            except (json.JSONDecodeError, KeyError):
                pass

        # Copy session metadata
        session_file = run_dir / "session.json"
        if session_file.exists():
            shutil.copy2(session_file, dest_dir / "session.json")

        count += 1
        print(f"  [{count}] {run_dir.name} -> {dest_dir}")

    print(f"\nCorpus prepared: {count} utterances in {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare test corpus from local-talk-artifacts")
    parser.add_argument(
        "--source",
        default="../voice-bot-acs/.runtime/local-talk-artifacts",
        help="Source artifacts directory",
    )
    parser.add_argument("--output", default=".runtime/corpus", help="Output corpus directory")
    parser.add_argument("--max-files", type=int, default=None, help="Limit number of files")
    args = parser.parse_args()

    prepare_corpus(args.source, args.output, args.max_files)


if __name__ == "__main__":
    main()

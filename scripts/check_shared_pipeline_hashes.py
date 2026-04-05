#!/usr/bin/env python3
"""Validate the shared pipeline utility contract across repos."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate_hash(files: dict[str, str]) -> str:
    payload = "".join(f"{rel}:{digest}\n" for rel, digest in sorted(files.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / ".woodpecker" / "shared-pipeline-hashes.json"
    manifest = json.loads(manifest_path.read_text())
    expected_files = manifest["files"]

    actual_files: dict[str, str] = {}
    mismatches: list[tuple[str, str, str]] = []
    missing: list[str] = []

    for rel_path, expected_hash in sorted(expected_files.items()):
        path = repo_root / rel_path
        if not path.is_file():
            missing.append(rel_path)
            continue
        actual_hash = sha256_file(path)
        actual_files[rel_path] = actual_hash
        if actual_hash != expected_hash:
            mismatches.append((rel_path, expected_hash, actual_hash))

    actual_aggregate = aggregate_hash(actual_files)

    print(f"shared-pipeline-contract-version={manifest['version']}")
    print(f"shared-pipeline-contract-sha256={actual_aggregate}")
    for rel_path, actual_hash in sorted(actual_files.items()):
        print(f"{rel_path} {actual_hash}")

    if missing:
        for rel_path in missing:
            print(f"missing shared pipeline file: {rel_path}", file=sys.stderr)
        return 1

    if actual_aggregate != manifest["aggregate_sha256"]:
        print(
            "shared pipeline aggregate mismatch: "
            f"expected {manifest['aggregate_sha256']} got {actual_aggregate}",
            file=sys.stderr,
        )
        return 1

    if mismatches:
        for rel_path, expected_hash, actual_hash in mismatches:
            print(
                f"shared pipeline hash mismatch: {rel_path} "
                f"expected={expected_hash} actual={actual_hash}",
                file=sys.stderr,
            )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

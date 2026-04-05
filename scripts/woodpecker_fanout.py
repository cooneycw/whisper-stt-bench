#!/usr/bin/env python3
"""Trigger manual Woodpecker pipelines in sibling repos and wait for completion."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

SUCCESS_STATES = {"success", "skipped"}
RUNNING_STATES = {"pending", "running", "blocked", "created"}


def fetch_essent_secret(region: str, secret_id: str) -> dict[str, object]:
    output = subprocess.check_output(
        [
            "aws",
            "secretsmanager",
            "get-secret-value",
            "--region",
            region,
            "--secret-id",
            secret_id,
            "--query",
            "SecretString",
            "--output",
            "text",
        ],
        text=True,
    )
    return json.loads(output)


def parse_repo_ids(raw: str) -> dict[str, int]:
    repo_ids: dict[str, int] = {}
    for item in raw.split(","):
        entry = item.strip()
        if not entry:
            continue
        repo_name, sep, repo_id = entry.partition("=")
        if not sep or not repo_name.strip() or not repo_id.strip():
            raise SystemExit(
                "Invalid repo id mapping. Expected comma-separated entries like "
                "'cooneycw/voice-bot-acs=6'."
            )
        try:
            repo_ids[repo_name.strip()] = int(repo_id.strip())
        except ValueError as exc:
            raise SystemExit(
                f"Invalid repo id for {repo_name.strip()!r}: {repo_id.strip()!r}"
            ) from exc
    return repo_ids


def api_request(
    base_url: str,
    token: str,
    path: str,
    method: str = "GET",
    body: dict[str, object] | None = None,
) -> object:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
    )
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def repo_map(base_url: str, token: str) -> dict[str, dict[str, object]]:
    repos = api_request(base_url, token, "/api/user/repos?all=true")
    assert isinstance(repos, list)
    return {str(repo["full_name"]): repo for repo in repos}


def resolve_repos(
    base_url: str,
    token: str,
    targets: list[str],
    configured_repo_ids: dict[str, int],
) -> dict[str, dict[str, object]]:
    resolved: dict[str, dict[str, object]] = {}
    unresolved: list[str] = []

    for target in targets:
        repo_id = configured_repo_ids.get(target)
        if repo_id is None:
            unresolved.append(target)
            continue
        resolved[target] = {"full_name": target, "id": repo_id}

    if not unresolved:
        return resolved

    discovered = repo_map(base_url, token)
    for target in unresolved:
        repo = discovered.get(target)
        if repo is None:
            raise SystemExit(f"Unknown Woodpecker repo: {target}")
        resolved[target] = repo

    return resolved


def wait_for_pipeline(
    base_url: str,
    token: str,
    repo_id: int,
    pipeline_number: int,
    timeout_s: int,
    poll_s: int,
) -> tuple[str, dict[str, object]]:
    deadline = time.time() + timeout_s
    last_status = "unknown"
    while time.time() < deadline:
        payload = api_request(base_url, token, f"/api/repos/{repo_id}/pipelines/{pipeline_number}")
        assert isinstance(payload, dict)
        last_status = str(payload.get("status", "unknown"))
        if last_status in SUCCESS_STATES:
            return last_status, payload
        if last_status not in RUNNING_STATES:
            return last_status, payload
        time.sleep(poll_s)
    raise TimeoutError(
        f"Timed out waiting for pipeline #{pipeline_number}; "
        f"last status={last_status}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", required=True, help="Comma-separated repo full names")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--secret-id", default="essent-ai")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--poll", type=int, default=10)
    parser.add_argument("--source", default=os.environ.get("CI_REPO", ""))
    parser.add_argument(
        "--repo-ids",
        default=os.environ.get("WOODPECKER_FANOUT_REPO_IDS", ""),
        help=(
            "Optional comma-separated repo=id mappings to avoid "
            "/api/user/repos discovery for known targets"
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    secret = fetch_essent_secret(args.region, args.secret_id)
    base_url = str(
        secret.get("WOODPECKER_URL") or secret.get("WOODPECKER_HOST") or ""
    ).rstrip("/")
    token = str(secret.get("WOODPECKER_API_TOKEN") or "")
    if not base_url or not token:
        raise SystemExit("Missing WOODPECKER_URL/WOODPECKER_API_TOKEN in essent-ai secret")

    targets = [item.strip() for item in args.targets.split(",") if item.strip()]
    repos = resolve_repos(base_url, token, targets, parse_repo_ids(args.repo_ids))
    current_repo = args.source.strip()

    triggered: list[tuple[str, int, int]] = []
    for target in targets:
        if target == current_repo:
            print(f"fanout: skipping self target {target}")
            continue
        repo = repos.get(target)
        if repo is None:
            raise SystemExit(f"Unknown Woodpecker repo: {target}")
        repo_id = int(repo["id"])
        body = {
            "branch": args.branch,
            "variables": {
                "WOODPECKER_SKIP_FANOUT": "true",
                "WOODPECKER_FANOUT_SOURCE": current_repo or "manual",
            },
        }
        print(f"fanout: triggering manual pipeline for {target} on {args.branch}")
        if args.dry_run:
            continue
        payload = api_request(
            base_url,
            token,
            f"/api/repos/{repo_id}/pipelines",
            method="POST",
            body=body,
        )
        assert isinstance(payload, dict)
        pipeline_number = int(payload["number"])
        triggered.append((target, repo_id, pipeline_number))
        print(f"fanout: {target} pipeline #{pipeline_number} created")

    for target, repo_id, pipeline_number in triggered:
        print(f"fanout: waiting for {target} pipeline #{pipeline_number}")
        status, payload = wait_for_pipeline(
            base_url,
            token,
            repo_id,
            pipeline_number,
            args.timeout,
            args.poll,
        )
        if status not in SUCCESS_STATES:
            print(json.dumps(payload, indent=2))
            raise SystemExit(
                f"fanout: {target} pipeline #{pipeline_number} "
                f"finished with status={status}"
            )
        print(f"fanout: {target} pipeline #{pipeline_number} finished with status={status}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        print(body, file=sys.stderr)
        raise

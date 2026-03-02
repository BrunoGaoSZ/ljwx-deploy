#!/usr/bin/env python3
"""Release queue promoter for Bid-MVP dev auto-promotion."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json_like(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    return json.loads(text)


def write_json_like(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_queue_shape(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    queue = {
        "pending": list(payload.get("pending", [])),
        "promoted": list(payload.get("promoted", [])),
        "failed": list(payload.get("failed", [])),
    }
    return queue


def normalize_repo_for_v2(repository: str, harbor_host: str) -> str:
    repo = repository.strip()
    host = harbor_host.replace("https://", "").replace("http://", "").strip("/")
    if repo.startswith(host + "/"):
        return repo.split("/", 1)[1]
    if repo.startswith("https://") or repo.startswith("http://"):
        stripped = repo.split("//", 1)[1]
        return stripped.split("/", 1)[1]
    return repo


def fetch_manifest_digest(
    harbor_url: str,
    repository: str,
    reference: str,
    username: str | None,
    password: str | None,
    timeout: float,
) -> str:
    repo_path = normalize_repo_for_v2(repository, harbor_url)
    base = harbor_url.rstrip("/")
    url = f"{base}/v2/{repo_path}/manifests/{reference}"
    headers = {
        "Accept": ", ".join(
            [
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.docker.distribution.manifest.v2+json",
                "application/vnd.docker.distribution.manifest.list.v2+json",
                "application/vnd.oci.image.index.v1+json",
            ]
        )
    }

    if username and password:
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"

    methods = ["HEAD", "GET"]
    last_error: Exception | None = None
    for method in methods:
        req = urllib.request.Request(url, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                digest = resp.headers.get("Docker-Content-Digest")
                if digest and DIGEST_RE.match(digest):
                    return digest
                if DIGEST_RE.match(reference):
                    return reference
                if method == "GET":
                    raise RuntimeError("manifest found but digest header missing")
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 404:
                raise RuntimeError(f"manifest not found in Harbor: {repository}:{reference}") from exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    raise RuntimeError(f"failed to query Harbor manifest {repository}:{reference}: {last_error}")


def choose_latest_pending(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep only latest pending per service and mark older as superseded."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        service = str(entry.get("service", "")).strip()
        grouped.setdefault(service, []).append(entry)

    survivors: list[dict[str, Any]] = []
    superseded: list[dict[str, Any]] = []

    for service, service_entries in grouped.items():
        service_entries.sort(key=lambda it: str(it.get("created_at", "")))
        if not service_entries:
            continue

        latest = service_entries[-1]
        survivors.append(latest)

        for stale in service_entries[:-1]:
            stale_copy = deepcopy(stale)
            stale_copy["status"] = "superseded"
            stale_copy["last_error"] = "superseded by newer pending entry for same service"
            stale_copy["updated_at"] = now_utc()
            superseded.append(stale_copy)

    return survivors, superseded


def get_deploy_commit() -> str:
    env_sha = os.getenv("GITHUB_SHA")
    if env_sha:
        return env_sha

    try:
        output = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
        return output.decode("utf-8").strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def upsert_env_manifest(env_dir: Path, service: str, environment: str, image_ref: str, queue_id: str, dry_run: bool) -> str:
    path = env_dir / f"{service}.yaml"
    payload = read_json_like(path)

    payload.update(
        {
            "service": service,
            "environment": environment,
            "image": image_ref,
            "source_queue_id": queue_id,
            "updated_at": now_utc(),
        }
    )

    if not dry_run:
        write_json_like(path, payload)

    return str(path)


def upsert_evidence_record(
    evidence_dir: Path,
    entry: dict[str, Any],
    outcome_status: str,
    error: str,
    digest: str | None,
    env_manifest_path: str,
    dry_run: bool,
) -> str:
    queue_id = str(entry.get("id", "unknown"))
    service = str(entry.get("service", "unknown"))
    environment = str(entry.get("environment", "dev"))
    record_id = f"{service}-{environment}-{queue_id}".lower()
    path = evidence_dir / f"{record_id}.json"
    existing = read_json_like(path)

    created_at = existing.get("timestamps", {}).get("created_at", now_utc())
    commit = get_deploy_commit()

    image = entry.get("image", {})
    repository = str(image.get("repository", ""))
    tag = str(image.get("tag", ""))
    existing_smoke = existing.get("tests", {}).get("smoke") or existing.get("smoke") or {"status": "unknown"}

    payload: dict[str, Any] = {
        "record_id": record_id,
        "service": service,
        "environment": environment,
        "status": outcome_status,
        "image": {
            "repository": repository,
            "tag": tag,
        },
        "deploy": {
            "queue_id": queue_id,
            "promoter": "deploy-promoter",
            "commit": commit,
            "promoted_at": now_utc() if outcome_status == "promoted" else existing.get("deploy", {}).get("promoted_at"),
        },
        "tests": {
            "smoke": existing_smoke,
        },
        "attempts": int(entry.get("attempts", 0)),
        "error": error,
        "links": {
            "queue": "release/queue.yaml",
            "env_manifest": env_manifest_path,
            "pr": str(entry.get("pr", "")),
        },
        "timestamps": {
            "created_at": created_at,
            "updated_at": now_utc(),
        },
    }

    if digest:
        payload["image"]["digest"] = digest

    if not dry_run:
        write_json_like(path, payload)

    return str(path)


def promote(
    queue: dict[str, list[dict[str, Any]]],
    args: argparse.Namespace,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    logs: list[str] = []
    pending = list(queue["pending"])

    survivors, superseded = choose_latest_pending(pending)
    if superseded:
        logs.append(f"superseded {len(superseded)} stale pending entr(y/ies)")
        queue["failed"].extend(superseded)

    queue["pending"] = []

    for entry in survivors:
        service = str(entry.get("service", "")).strip()
        environment = str(entry.get("environment", "dev")).strip()
        queue_id = str(entry.get("id", ""))
        attempts = int(entry.get("attempts", 0))
        max_attempts = int(entry.get("max_attempts", args.max_attempts))

        image = entry.get("image", {})
        repository = str(image.get("repository", "")).strip()
        ref = str(image.get("digest") or image.get("tag") or "").strip()

        logs.append(f"processing queue item {queue_id} ({service}/{environment})")

        if not repository or not ref:
            attempts += 1
            entry["attempts"] = attempts
            entry["last_error"] = "missing image.repository or image.tag/image.digest"
            entry["updated_at"] = now_utc()
            upsert_evidence_record(
                args.evidence_dir,
                entry,
                "failed" if attempts >= max_attempts else "pending",
                entry["last_error"],
                None,
                f"{args.env_dir}/{service}.yaml",
                args.dry_run,
            )
            if attempts >= max_attempts:
                entry["status"] = "failed"
                queue["failed"].append(entry)
            else:
                queue["pending"].append(entry)
            continue

        digest: str | None = None
        error = ""

        try:
            if args.skip_registry_check:
                if DIGEST_RE.match(ref):
                    digest = ref
                else:
                    digest = "sha256:" + "0" * 64
                logs.append(f"registry check skipped for {queue_id}")
            else:
                digest = fetch_manifest_digest(
                    harbor_url=args.harbor_url,
                    repository=repository,
                    reference=ref,
                    username=args.harbor_username,
                    password=args.harbor_password,
                    timeout=args.timeout,
                )
                logs.append(f"manifest available for {queue_id}: {digest}")

            image_ref = f"{repository}@{digest}"
            env_manifest_path = upsert_env_manifest(args.env_dir, service, environment, image_ref, queue_id, args.dry_run)

            entry["attempts"] = attempts + 1
            entry["status"] = "promoted"
            entry["promoted_at"] = now_utc()
            entry["digest"] = digest
            entry["last_error"] = ""
            entry["updated_at"] = now_utc()

            upsert_evidence_record(
                args.evidence_dir,
                entry,
                "promoted",
                "",
                digest,
                env_manifest_path,
                args.dry_run,
            )

            queue["promoted"].append(entry)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            attempts += 1
            entry["attempts"] = attempts
            entry["last_error"] = error
            entry["updated_at"] = now_utc()

            outcome = "failed" if attempts >= max_attempts else "pending"
            env_manifest_path = f"{args.env_dir}/{service}.yaml"
            upsert_evidence_record(
                args.evidence_dir,
                entry,
                outcome,
                error,
                None,
                env_manifest_path,
                args.dry_run,
            )

            if attempts >= max_attempts:
                entry["status"] = "failed"
                queue["failed"].append(entry)
                logs.append(f"{queue_id} failed after {attempts} attempt(s): {error}")
            else:
                queue["pending"].append(entry)
                logs.append(f"{queue_id} retry scheduled ({attempts}/{max_attempts}): {error}")

    return queue, logs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-promote pending queue items for dev")
    parser.add_argument("--queue", default="release/queue.yaml", type=Path)
    parser.add_argument("--env-dir", default="envs/dev", type=Path)
    parser.add_argument("--evidence-dir", default="evidence/records", type=Path)
    parser.add_argument("--max-attempts", default=3, type=int)
    parser.add_argument("--harbor-url", default=os.getenv("HARBOR_URL", "https://harbor.omniverseai.net"))
    parser.add_argument("--harbor-username", default=os.getenv("HARBOR_USERNAME"))
    parser.add_argument("--harbor-password", default=os.getenv("HARBOR_PASSWORD"))
    parser.add_argument("--timeout", default=8.0, type=float)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-registry-check", action="store_true", help="use synthetic digest in non-network dry runs")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    raw = read_json_like(args.queue)
    queue = ensure_queue_shape(raw)

    updated, logs = promote(queue, args)

    if not args.dry_run:
        write_json_like(args.queue, updated)

    for line in logs:
        print(line)

    print(
        "summary:",
        json.dumps(
            {
                "pending": len(updated["pending"]),
                "promoted": len(updated["promoted"]),
                "failed": len(updated["failed"]),
                "dry_run": args.dry_run,
            }
        ),
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

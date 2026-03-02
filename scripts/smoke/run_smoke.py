#!/usr/bin/env python3
"""Smoke runner that updates evidence records after promotion."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_iso(value: str) -> str:
    return value or ""


def record_files(evidence_dir: Path) -> list[Path]:
    return sorted([p for p in evidence_dir.glob("*.json") if p.is_file()])


def find_record_path(evidence_dir: Path, service: str, environment: str, queue_id: str | None) -> Path | None:
    candidates: list[tuple[str, Path]] = []
    for path in record_files(evidence_dir):
        try:
            record = read_json(path)
        except Exception:  # noqa: BLE001
            continue

        if record.get("service") != service or record.get("environment") != environment:
            continue

        deploy = record.get("deploy", {})
        if queue_id and deploy.get("queue_id") != queue_id:
            continue

        if record.get("status") != "promoted":
            continue

        updated = parse_iso(record.get("timestamps", {}).get("updated_at", ""))
        candidates.append((updated, path))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def http_get(url: str, headers: dict[str, str] | None = None, timeout: float = 5.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(4096).decode("utf-8", errors="ignore")
        return int(resp.getcode() or 0), body


def wait_for_argocd_health(
    server: str,
    token: str,
    app: str,
    timeout_seconds: int,
    interval_seconds: int,
) -> tuple[bool, str]:
    if not server or not token or not app:
        return True, "argocd check skipped"

    end = time.time() + timeout_seconds
    app_encoded = urllib.parse.quote(app, safe="")
    url = f"{server.rstrip('/')}/api/v1/applications/{app_encoded}"
    headers = {"Authorization": f"Bearer {token}"}

    last = ""
    while time.time() < end:
        try:
            code, body = http_get(url, headers=headers, timeout=8.0)
            if code < 300:
                data = json.loads(body)
                status = data.get("status", {})
                sync = status.get("sync", {}).get("status")
                health = status.get("health", {}).get("status")
                last = f"sync={sync},health={health}"
                if sync == "Synced" and health == "Healthy":
                    return True, last
        except Exception as exc:  # noqa: BLE001
            last = str(exc)

        time.sleep(interval_seconds)

    return False, f"argocd wait timeout: {last}"


def wait_for_endpoint(endpoint: str, timeout_seconds: int, interval_seconds: int) -> tuple[bool, str]:
    end = time.time() + timeout_seconds
    last = ""

    while time.time() < end:
        try:
            code, body = http_get(endpoint, timeout=8.0)
            if 200 <= code < 400:
                snippet = body[:120].replace("\n", " ")
                return True, f"endpoint={code} body='{snippet}'"
            last = f"http={code}"
        except urllib.error.HTTPError as exc:
            last = f"http={exc.code}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)

        time.sleep(interval_seconds)

    return False, f"endpoint wait timeout: {last}"


def update_smoke_record(path: Path, ok: bool, details: str, dry_run: bool) -> None:
    record = read_json(path)
    tests = record.setdefault("tests", {})
    smoke = tests.setdefault("smoke", {})
    smoke["status"] = "pass" if ok else "fail"
    smoke["checked_at"] = now_utc()
    smoke["details"] = details

    timestamps = record.setdefault("timestamps", {})
    if "created_at" not in timestamps:
        timestamps["created_at"] = now_utc()
    timestamps["updated_at"] = now_utc()

    if not dry_run:
        write_json(path, record)


def run_target(target: dict[str, Any], args: argparse.Namespace) -> tuple[str, str]:
    service = str(target.get("service", "")).strip()
    environment = str(target.get("environment", "dev")).strip()
    queue_id = target.get("queue_id")
    app = str(target.get("argocd_app", "")).strip()
    endpoint = str(target.get("endpoint", "")).strip()

    if not service or not endpoint:
        return "fail", f"invalid target: {target}"

    record_path = find_record_path(args.evidence_dir, service, environment, queue_id)
    if not record_path:
        return "skip", f"{service}: no promoted evidence record for {service}/{environment}"

    ok_argocd, argocd_details = wait_for_argocd_health(
        server=args.argocd_server,
        token=args.argocd_token,
        app=app,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.interval_seconds,
    )
    if not ok_argocd:
        update_smoke_record(record_path, False, argocd_details, args.dry_run)
        return "fail", f"{service}: {argocd_details}"

    ok_endpoint, endpoint_details = wait_for_endpoint(
        endpoint=endpoint,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.interval_seconds,
    )

    details = f"{argocd_details}; {endpoint_details}"
    update_smoke_record(record_path, ok_endpoint, details, args.dry_run)
    if ok_endpoint:
        return "pass", f"{service}: {details}"
    return "fail", f"{service}: {details}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run smoke checks and write evidence results")
    parser.add_argument("--targets", type=Path, default=Path("scripts/smoke/targets.json"))
    parser.add_argument("--evidence-dir", type=Path, default=Path("evidence/records"))
    parser.add_argument("--argocd-server", default=os.getenv("ARGOCD_SERVER", ""))
    parser.add_argument("--argocd-token", default=os.getenv("ARGOCD_TOKEN", ""))
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--interval-seconds", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = read_json(args.targets)
    targets = list(config.get("targets", []))

    passed = 0
    failed = 0
    skipped = 0
    for target in targets:
        outcome, message = run_target(target, args)
        print(message)
        if outcome == "pass":
            passed += 1
        elif outcome == "fail":
            failed += 1
        else:
            skipped += 1

    print(json.dumps({"passed": passed, "failed": failed, "skipped": skipped, "dry_run": args.dry_run}))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate evidence records without external dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
STATUS_ALLOWED = {"pending", "promoted", "failed", "superseded"}
SMOKE_ALLOWED = {"unknown", "pass", "fail"}


class ValidationError(Exception):
    pass


def _expect(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _is_iso8601_z(value: str) -> bool:
    if not ISO_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return True
    except ValueError:
        return False


def validate_record(record: dict[str, Any], path: Path) -> list[str]:
    errors: list[str] = []

    required_root = [
        "record_id",
        "service",
        "environment",
        "status",
        "image",
        "deploy",
        "tests",
        "attempts",
        "timestamps",
    ]
    for field in required_root:
        _expect(field in record, f"missing root field: {field}", errors)

    if errors:
        return errors

    _expect(isinstance(record["record_id"], str) and len(record["record_id"]) >= 3, "record_id must be string length>=3", errors)
    _expect(isinstance(record["service"], str) and len(record["service"]) >= 2, "service must be string length>=2", errors)
    _expect(isinstance(record["environment"], str) and len(record["environment"]) >= 2, "environment must be string length>=2", errors)
    _expect(record["status"] in STATUS_ALLOWED, f"status must be one of {sorted(STATUS_ALLOWED)}", errors)

    image = record.get("image")
    _expect(isinstance(image, dict), "image must be object", errors)
    if isinstance(image, dict):
        _expect(isinstance(image.get("repository"), str) and len(image["repository"]) >= 3, "image.repository must be string length>=3", errors)
        digest = image.get("digest")
        if digest is not None:
            _expect(isinstance(digest, str) and bool(DIGEST_RE.match(digest)), "image.digest must match sha256:<64-hex>", errors)

    deploy = record.get("deploy")
    _expect(isinstance(deploy, dict), "deploy must be object", errors)
    if isinstance(deploy, dict):
        _expect(isinstance(deploy.get("queue_id"), str) and len(deploy["queue_id"]) >= 2, "deploy.queue_id must be string length>=2", errors)
        promoted_at = deploy.get("promoted_at")
        if promoted_at is not None:
            _expect(isinstance(promoted_at, str) and _is_iso8601_z(promoted_at), "deploy.promoted_at must be ISO8601 UTC (YYYY-MM-DDTHH:MM:SSZ)", errors)

    tests = record.get("tests")
    _expect(isinstance(tests, dict), "tests must be object", errors)
    smoke = None
    if isinstance(tests, dict):
        smoke = tests.get("smoke")
        _expect(isinstance(smoke, dict), "tests.smoke must be object", errors)

    if isinstance(smoke, dict):
        _expect(smoke.get("status") in SMOKE_ALLOWED, f"tests.smoke.status must be one of {sorted(SMOKE_ALLOWED)}", errors)
        checked_at = smoke.get("checked_at")
        if checked_at is not None:
            _expect(
                isinstance(checked_at, str) and _is_iso8601_z(checked_at),
                "tests.smoke.checked_at must be ISO8601 UTC (YYYY-MM-DDTHH:MM:SSZ)",
                errors,
            )

    _expect(isinstance(record["attempts"], int) and record["attempts"] >= 0, "attempts must be integer >= 0", errors)

    timestamps = record.get("timestamps")
    _expect(isinstance(timestamps, dict), "timestamps must be object", errors)
    if isinstance(timestamps, dict):
        for field in ("created_at", "updated_at"):
            value = timestamps.get(field)
            _expect(isinstance(value, str) and _is_iso8601_z(value), f"timestamps.{field} must be ISO8601 UTC (YYYY-MM-DDTHH:MM:SSZ)", errors)

    return errors


def iter_records(records_dir: Path) -> list[Path]:
    return sorted([p for p in records_dir.glob("*.json") if p.is_file()])


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid json: {exc}") from exc


def run(records_dir: Path, quiet: bool = False) -> int:
    files = iter_records(records_dir)
    if not files:
        if not quiet:
            print(f"no record files found under {records_dir}")
        return 0

    failed = 0
    for path in files:
        try:
            record = load_json(path)
            errs = validate_record(record, path)
        except ValidationError as exc:
            errs = [str(exc)]

        if errs:
            failed += 1
            print(f"FAIL {path}")
            for err in errs:
                print(f"  - {err}")
        elif not quiet:
            print(f"OK   {path}")

    if failed:
        print(f"validation failed: {failed}/{len(files)} file(s) invalid")
        return 1

    if not quiet:
        print(f"validation passed: {len(files)} file(s)")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate evidence records")
    parser.add_argument("--records-dir", default="evidence/records", help="directory containing record json files")
    parser.add_argument("--quiet", action="store_true", help="only print failures")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run(Path(args.records_dir), quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build queue health metrics for ops visibility."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # noqa: BLE001
    raise SystemExit(
        f"PyYAML is required. Install with: uvx --with pyyaml python <script>\n{exc}"
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_rfc3339() -> str:
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"queue root must be mapping: {path}")
    return payload


def ensure_queue_shape(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for key in ("pending", "promoted", "failed", "superseded"):
        raw = payload.get(key, [])
        if not isinstance(raw, list):
            raise ValueError(f"queue key must be list: {key}")
        out[key] = [entry for entry in raw if isinstance(entry, dict)]
    return out


def ts_from_entry(entry: dict[str, Any], fields: list[str]) -> datetime:
    for field in fields:
        parsed = parse_ts(entry.get(field))
        if parsed != datetime.min.replace(tzinfo=timezone.utc):
            return parsed
    return datetime.min.replace(tzinfo=timezone.utc)


def service_env_key(entry: dict[str, Any]) -> str:
    service = str(entry.get("service", "unknown")).strip() or "unknown"
    env = str(entry.get("env", "unknown")).strip() or "unknown"
    return f"{service}/{env}"


def grouped_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        key = service_env_key(entry)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def build_metrics(
    queue: dict[str, list[dict[str, Any]]], stale_threshold_seconds: int
) -> dict[str, Any]:
    current = now_utc()
    pending = queue["pending"]
    promoted = queue["promoted"]
    failed = queue["failed"]
    superseded = queue["superseded"]

    pending_times: list[datetime] = [
        ts
        for ts in (ts_from_entry(item, ["createdAt"]) for item in pending)
        if ts != datetime.min.replace(tzinfo=timezone.utc)
    ]
    oldest_pending = min(pending_times) if pending_times else None
    max_pending_age_seconds = (
        int((current - oldest_pending).total_seconds()) if oldest_pending else 0
    )

    stale_ids = []
    for item in pending:
        created = ts_from_entry(item, ["createdAt"])
        if created == datetime.min.replace(tzinfo=timezone.utc):
            continue
        age_seconds = int((current - created).total_seconds())
        if age_seconds >= stale_threshold_seconds:
            stale_ids.append(str(item.get("id", "")))

    recent_failed_cutoff = current - timedelta(hours=24)
    failed_24h = 0
    for item in failed:
        failed_at = ts_from_entry(item, ["failedAt", "createdAt"])
        if failed_at >= recent_failed_cutoff:
            failed_24h += 1

    superseded_denominator = len(promoted) + len(superseded)
    superseded_ratio = (
        round(len(superseded) / superseded_denominator, 4)
        if superseded_denominator > 0
        else 0.0
    )

    pending_attempts = [int(item.get("attempts", 0)) for item in pending]
    failed_attempts = [int(item.get("attempts", 0)) for item in failed]

    return {
        "generatedAt": now_rfc3339(),
        "counts": {
            "pending": len(pending),
            "promoted": len(promoted),
            "failed": len(failed),
            "superseded": len(superseded),
        },
        "pending": {
            "oldestCreatedAt": oldest_pending.strftime("%Y-%m-%dT%H:%M:%SZ")
            if oldest_pending
            else "",
            "maxAgeSeconds": max_pending_age_seconds,
            "staleThresholdSeconds": stale_threshold_seconds,
            "staleIds": stale_ids,
            "byServiceEnv": grouped_counts(pending),
        },
        "failed": {
            "last24h": failed_24h,
            "byServiceEnv": grouped_counts(failed),
        },
        "retries": {
            "pendingMaxAttempts": max(pending_attempts) if pending_attempts else 0,
            "failedMaxAttempts": max(failed_attempts) if failed_attempts else 0,
        },
        "ratios": {
            "supersededVsPromoted": superseded_ratio,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate release queue health metrics"
    )
    parser.add_argument("--queue", type=Path, default=Path("release/queue.yaml"))
    parser.add_argument(
        "--out", type=Path, default=Path("evidence/metrics/queue-health.json")
    )
    parser.add_argument("--stale-threshold-seconds", type=int, default=1800)
    args = parser.parse_args()

    if args.stale_threshold_seconds < 1:
        raise SystemExit("stale-threshold-seconds must be positive integer")

    queue_payload = ensure_queue_shape(load_yaml(args.queue))
    metrics = build_metrics(queue_payload, args.stale_threshold_seconds)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写入队列健康指标: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

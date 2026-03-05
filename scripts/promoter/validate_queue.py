#!/usr/bin/env python3
"""Validate release/queue.yaml structure and state contracts."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # noqa: BLE001
    raise SystemExit(
        f"PyYAML is required. Install with: uvx --with pyyaml python <script>\n{exc}"
    )


QUEUE_STATES = ("pending", "promoted", "failed", "superseded")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_yaml(path: Path) -> Any:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {} if data is None else data


def parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def validate_entry(
    state: str,
    index: int,
    entry: dict[str, Any],
    seen_ids: set[str],
    pending_service_env: set[tuple[str, str]],
) -> list[str]:
    errors: list[str] = []
    prefix = f"{state}[{index}]"

    required = [
        "id",
        "service",
        "env",
        "source",
        "createdAt",
        "status",
        "attempts",
        "lastError",
        "promotedAt",
        "supersededAt",
        "failedAt",
    ]
    for field in required:
        if field not in entry:
            errors.append(f"{prefix} 缺少字段: {field}")

    entry_id = as_non_empty_str(entry.get("id"))
    if not entry_id:
        errors.append(f"{prefix}.id 必须是非空字符串")
    elif entry_id in seen_ids:
        errors.append(f"{prefix}.id 重复: {entry_id}")
    else:
        seen_ids.add(entry_id)

    service = as_non_empty_str(entry.get("service"))
    env = as_non_empty_str(entry.get("env"))
    if not service:
        errors.append(f"{prefix}.service 必须是非空字符串")
    if not env:
        errors.append(f"{prefix}.env 必须是非空字符串")

    status = as_non_empty_str(entry.get("status"))
    if not status:
        errors.append(f"{prefix}.status 必须是非空字符串")
    elif status not in QUEUE_STATES:
        errors.append(f"{prefix}.status 非法: {status}")
    elif status != state:
        errors.append(f"{prefix}.status 与所在队列不一致: {status} != {state}")

    attempts = entry.get("attempts")
    if not isinstance(attempts, int) or attempts < 0:
        errors.append(f"{prefix}.attempts 必须是 >= 0 的整数")

    created_at = parse_rfc3339(entry.get("createdAt"))
    if created_at is None:
        errors.append(f"{prefix}.createdAt 必须是 RFC3339 时间戳")

    for ts_field in ("promotedAt", "supersededAt", "failedAt"):
        value = entry.get(ts_field)
        if value in ("", None):
            continue
        if parse_rfc3339(value) is None:
            errors.append(f"{prefix}.{ts_field} 必须是 RFC3339 时间戳或空字符串")

    # State timestamp contract
    if state == "pending":
        for ts_field in ("promotedAt", "supersededAt", "failedAt"):
            if as_non_empty_str(entry.get(ts_field)):
                errors.append(f"{prefix}.{ts_field} 在 pending 状态必须为空")
        if service and env:
            key = (service, env)
            if key in pending_service_env:
                errors.append(
                    f"{prefix} 同一 service/env 存在多个 pending: {service}/{env}"
                )
            else:
                pending_service_env.add(key)
    elif state == "promoted":
        if parse_rfc3339(entry.get("promotedAt")) is None:
            errors.append(f"{prefix}.promotedAt 在 promoted 状态必须为 RFC3339 时间")
    elif state == "failed":
        if parse_rfc3339(entry.get("failedAt")) is None:
            errors.append(f"{prefix}.failedAt 在 failed 状态必须为 RFC3339 时间")
    elif state == "superseded":
        if parse_rfc3339(entry.get("supersededAt")) is None:
            errors.append(
                f"{prefix}.supersededAt 在 superseded 状态必须为 RFC3339 时间"
            )

    source = entry.get("source", {})
    if not isinstance(source, dict):
        errors.append(f"{prefix}.source 必须是 mapping")
        return errors

    ghcr = as_non_empty_str(source.get("ghcr"))
    tag = as_non_empty_str(source.get("tag"))
    digest = as_non_empty_str(source.get("digest"))
    if not ghcr:
        errors.append(f"{prefix}.source.ghcr 必须是非空字符串")
    if not tag:
        errors.append(f"{prefix}.source.tag 必须是非空字符串")
    if not digest:
        errors.append(f"{prefix}.source.digest 必须是非空字符串")
    elif not DIGEST_PATTERN.match(digest):
        errors.append(f"{prefix}.source.digest 格式非法: {digest}")

    if ghcr and "@" in ghcr:
        _, ghcr_digest = ghcr.rsplit("@", 1)
        if digest and ghcr_digest != digest:
            errors.append(
                f"{prefix}.source.ghcr 与 source.digest 不一致: {ghcr_digest} != {digest}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate release queue shape")
    parser.add_argument("--queue", default="release/queue.yaml", type=Path)
    args = parser.parse_args()

    data = load_yaml(args.queue)
    if not isinstance(data, dict):
        print("queue 根节点必须是 mapping")
        return 1

    for key in QUEUE_STATES:
        if key not in data or not isinstance(data[key], list):
            print(f"缺少队列列表字段: {key}")
            return 1

    all_errors: list[str] = []
    seen_ids: set[str] = set()
    pending_service_env: set[tuple[str, str]] = set()
    for state in QUEUE_STATES:
        entries = data.get(state, [])
        for idx, item in enumerate(entries):
            if not isinstance(item, dict):
                all_errors.append(f"{state}[{idx}] 必须是 mapping")
                continue
            all_errors.extend(
                validate_entry(
                    state=state,
                    index=idx,
                    entry=item,
                    seen_ids=seen_ids,
                    pending_service_env=pending_service_env,
                )
            )

    if all_errors:
        print("release queue 校验失败:")
        for message in all_errors:
            print(f"- {message}")
        return 1

    print("release queue 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Collect evidence YAML records into JSON feed + markdown summary."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # noqa: BLE001
    raise SystemExit(f"PyYAML is required. Install with: pip3 install pyyaml\n{exc}")


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"record root must be mapping: {path}")
    return data


def parse_ts(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def record_timestamp(record: dict[str, Any]) -> datetime:
    deploy = record.get("deploy", {})
    synced_at = deploy.get("syncedAt") if isinstance(deploy, dict) else None
    promoted_at = record.get("promotedAt")
    return parse_ts(synced_at) if parse_ts(synced_at) != datetime.min.replace(tzinfo=timezone.utc) else parse_ts(promoted_at)


def short_digest(image_ref: str) -> str:
    if "@sha256:" in image_ref:
        return image_ref.split("@sha256:", 1)[1][:16]
    if "sha256:" in image_ref:
        return image_ref.split("sha256:", 1)[1][:16]
    return ""


def links_cell(record: dict[str, Any]) -> str:
    links: list[str] = []
    src = record.get("source", {})
    approvals = record.get("approvals", {})
    if isinstance(src, dict) and src.get("workflowRun"):
        links.append(f"[run]({src['workflowRun']})")

    if isinstance(approvals, dict):
        for key in ["specPr", "archPr", "demoPr", "uatPr", "releasePr"]:
            val = approvals.get(key)
            if val:
                links.append(f"[{key}]({val})")
        prs = approvals.get("prs")
        if isinstance(prs, list):
            for idx, pr in enumerate(prs, start=1):
                if isinstance(pr, str) and pr:
                    links.append(f"[pr{idx}]({pr})")

    return " ".join(links) if links else "-"


def write_summary(records: list[dict[str, Any]], out_path: Path) -> None:
    lines = [
        "# Latest Evidence Summary",
        "",
        "| service | env | harbor digest | syncedAt | smoke | links |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for record in records[:50]:
        service = str(record.get("service", "-"))
        env = str(record.get("env", "-"))
        image = record.get("image", {})
        harbor = image.get("harbor", "") if isinstance(image, dict) else ""
        digest = short_digest(str(harbor)) or "-"
        deploy = record.get("deploy", {})
        synced_at = deploy.get("syncedAt", "-") if isinstance(deploy, dict) else "-"
        tests = record.get("tests", {})
        smoke = "unknown"
        if isinstance(tests, dict):
            smoke_obj = tests.get("smoke", {})
            if isinstance(smoke_obj, dict):
                smoke = str(smoke_obj.get("status", "unknown"))

        lines.append(f"| {service} | {env} | `{digest}` | {synced_at} | {smoke} | {links_cell(record)} |")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect evidence YAML records into JSON index")
    parser.add_argument("--records-dir", default="evidence/records", type=Path)
    parser.add_argument("--out", default="evidence/index.json", type=Path)
    parser.add_argument("--summary", default="evidence/summary/latest.md", type=Path)
    args = parser.parse_args()

    records: list[dict[str, Any]] = []
    for path in sorted(args.records_dir.glob("*.yaml")):
        if not path.is_file():
            continue
        try:
            record = load_yaml(path)
            record["_recordPath"] = str(path)
            records.append(record)
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"failed to load {path}: {exc}")

    records.sort(key=record_timestamp, reverse=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_summary(records, args.summary)

    print(f"wrote {args.out} ({len(records)} records)")
    print(f"wrote {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

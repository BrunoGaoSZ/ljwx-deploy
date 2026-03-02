#!/usr/bin/env python3
"""Collect evidence records into evidence/index.json feed."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_records(records_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(records_dir.glob("*.json")):
        if not path.is_file():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        record["_record_path"] = str(path)
        records.append(record)
    return records


def sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(record: dict[str, Any]) -> str:
        timestamps = record.get("timestamps", {})
        return timestamps.get("updated_at") or timestamps.get("created_at") or ""

    return sorted(records, key=key, reverse=True)


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_service: dict[str, int] = {}
    by_status: dict[str, int] = {}

    for record in records:
        service = str(record.get("service", "unknown"))
        status = str(record.get("status", "unknown"))
        by_service[service] = by_service.get(service, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "by_service": by_service,
        "by_status": by_status,
    }


def build_index(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "generated_at": now_utc(),
        "source": {
            "repository": os.getenv("GITHUB_REPOSITORY", "local/ljwx-deploy"),
            "ref": os.getenv("GITHUB_REF", "local"),
        },
        "total_records": len(records),
        "summary": summarize(records),
        "records": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect evidence records into index feed")
    parser.add_argument("--records-dir", default="evidence/records", help="directory containing record json files")
    parser.add_argument("--out", default="evidence/index.json", help="output feed path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records_dir = Path(args.records_dir)
    out_path = Path(args.out)

    records = read_records(records_dir)
    records = sort_records(records)
    index = build_index(records)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path} with {len(records)} record(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

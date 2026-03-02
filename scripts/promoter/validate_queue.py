#!/usr/bin/env python3
"""Validate release/queue.yaml structure for gate checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # noqa: BLE001
    raise SystemExit(f"PyYAML is required. Install with: pip3 install pyyaml\n{exc}")


def load_yaml(path: Path) -> Any:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {} if data is None else data


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate release queue shape")
    parser.add_argument("--queue", default="release/queue.yaml", type=Path)
    args = parser.parse_args()

    data = load_yaml(args.queue)
    if not isinstance(data, dict):
        print("queue root must be mapping")
        return 1

    for key in ["pending", "promoted", "failed", "superseded"]:
        if key not in data or not isinstance(data[key], list):
            print(f"missing list key: {key}")
            return 1

    required = ["id", "service", "env", "source", "createdAt", "status", "attempts", "lastError", "promotedAt", "supersededAt", "failedAt"]
    for state in ["pending", "promoted", "failed", "superseded"]:
        for idx, item in enumerate(data[state]):
            if not isinstance(item, dict):
                print(f"{state}[{idx}] must be mapping")
                return 1
            for field in required:
                if field not in item:
                    print(f"{state}[{idx}] missing field: {field}")
                    return 1
            source = item.get("source", {})
            if not isinstance(source, dict):
                print(f"{state}[{idx}].source must be mapping")
                return 1
            for sf in ["ghcr", "tag", "digest"]:
                if sf not in source:
                    print(f"{state}[{idx}].source missing field: {sf}")
                    return 1

    print("release queue validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

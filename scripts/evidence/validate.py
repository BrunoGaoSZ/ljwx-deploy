#!/usr/bin/env python3
"""Validate YAML evidence records against minimal schema constraints."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # noqa: BLE001
    raise SystemExit(f"PyYAML is required. Install with: pip3 install pyyaml\n{exc}")

try:
    import jsonschema
except Exception:  # noqa: BLE001
    jsonschema = None


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("record root must be a YAML mapping")
    return data


def record_files(records_dir: Path) -> list[Path]:
    return sorted([p for p in records_dir.glob("*.yaml") if p.is_file()])


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate evidence YAML records")
    parser.add_argument("--records-dir", default="evidence/records", type=Path)
    parser.add_argument("--schema", default="evidence/schema/evidence.schema.json", type=Path)
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    files = record_files(args.records_dir)

    bad: list[tuple[Path, str]] = []

    for path in files:
        try:
            data = load_yaml(path)
            if jsonschema is not None:
                jsonschema.validate(instance=data, schema=schema)
            else:
                # Fallback minimal checks if jsonschema package is unavailable locally.
                required = [
                    ("evidenceId",),
                    ("service",),
                    ("env",),
                    ("source", "repo"),
                    ("source", "commit"),
                    ("image", "harbor"),
                    ("deploy", "deployRepoCommit"),
                ]
                for key_path in required:
                    node: Any = data
                    for key in key_path:
                        if not isinstance(node, dict) or key not in node:
                            raise ValueError(f"missing required field: {'.'.join(key_path)}")
                        node = node[key]
                    if node in ("", None):
                        raise ValueError(f"empty required field: {'.'.join(key_path)}")
        except Exception as exc:  # noqa: BLE001
            bad.append((path, str(exc)))

    if bad:
        print("Evidence validation failed for the following files:")
        for file_path, error in bad:
            print(f"- {file_path}: {error}")
        return 1

    print(f"Evidence validation passed ({len(files)} file(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

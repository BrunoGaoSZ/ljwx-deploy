#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROTECTED_PREFIXES: tuple[str, ...] = (
    "argocd-apps/",
    "cluster/",
    "cluster-prod/",
    "envs/",
    "infra/",
    "k8s/",
    "scripts/github/",
)
PLATFORM_ADMIN_LABEL = "platform-admin"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check deploy repo path gate.")
    parser.add_argument(
        "--changed-files", required=True, help="Path to the changed files list."
    )
    parser.add_argument(
        "--event-path", required=True, help="Path to the GitHub event payload."
    )
    return parser.parse_args()


def load_changed_files(changed_files_path: Path) -> list[str]:
    return [
        line.strip()
        for line in changed_files_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_labels(event_path: Path) -> set[str]:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    pull_request = event.get("pull_request", {})
    labels = pull_request.get("labels", [])
    return {str(label.get("name", "")).strip() for label in labels if label.get("name")}


def requires_platform_admin(path: str) -> bool:
    return path.startswith(PROTECTED_PREFIXES)


def main() -> int:
    args = parse_args()
    changed_files = load_changed_files(Path(args.changed_files))
    labels = load_labels(Path(args.event_path))

    protected_changes = [
        path for path in changed_files if requires_platform_admin(path)
    ]
    if protected_changes and PLATFORM_ADMIN_LABEL not in labels:
        print("检测到受保护路径变更，缺少 platform-admin label：")
        for path in protected_changes:
            print(f"- {path}")
        return 1

    print("路径 gate 校验通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

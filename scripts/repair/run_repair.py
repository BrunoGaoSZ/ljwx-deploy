#!/usr/bin/env python3
"""Auto-repair loop for common CI failures."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
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


def run_check_command(check_cmd: str, log_path: Path) -> tuple[int, str]:
    proc = subprocess.run(check_cmd, shell=True, text=True, capture_output=True)
    output = f"$ {check_cmd}\n\nstdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}\n"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")
    return proc.returncode, output


def iter_files(root: Path, extensions: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "/.git/" in f"/{path.as_posix()}/":
            continue
        if path.suffix in extensions:
            files.append(path)
    return files


def action_format_json(repo_root: Path) -> int:
    changed = 0
    for path in iter_files(repo_root, (".json", ".yaml")):
        if path.suffix == ".yaml":
            text = path.read_text(encoding="utf-8").strip()
            if not text.startswith("{"):
                continue
        try:
            payload = read_json(path)
        except Exception:  # noqa: BLE001
            continue

        normalized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        current = path.read_text(encoding="utf-8")
        if current != normalized:
            path.write_text(normalized, encoding="utf-8")
            changed += 1

    return changed


def action_strip_trailing_whitespace(repo_root: Path) -> int:
    changed = 0
    pattern = re.compile(r"[ \t]+$", re.MULTILINE)
    for path in iter_files(repo_root, (".py", ".sh", ".md", ".yaml", ".yml", ".js", ".ts")):
        text = path.read_text(encoding="utf-8")
        updated = pattern.sub("", text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    return changed


def action_regenerate_evidence_index(repo_root: Path) -> int:
    cmd = [sys.executable, "scripts/evidence/collect.py", "--out", "evidence/index.json"]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"collect.py failed: {proc.stderr.strip()}")
    return 1


def action_normalize_queue_shape(repo_root: Path) -> int:
    queue_path = repo_root / "release/queue.yaml"
    if not queue_path.exists():
        payload = {"pending": [], "promoted": [], "failed": []}
        write_json(queue_path, payload)
        return 1

    payload = read_json(queue_path)
    changed = 0
    for key in ("pending", "promoted", "failed"):
        if key not in payload or not isinstance(payload[key], list):
            payload[key] = []
            changed = 1

    if changed:
        write_json(queue_path, payload)
    return changed


ACTION_MAP = {
    "format_json": action_format_json,
    "strip_trailing_whitespace": action_strip_trailing_whitespace,
    "regenerate_evidence_index": action_regenerate_evidence_index,
    "normalize_queue_shape": action_normalize_queue_shape,
}


def select_recipes(recipes: list[dict[str, Any]], check_output: str) -> list[dict[str, Any]]:
    text = check_output.lower()
    selected: list[dict[str, Any]] = []

    for recipe in recipes:
        keywords = [str(v).lower() for v in recipe.get("trigger_keywords", [])]
        if any(keyword in text for keyword in keywords):
            selected.append(recipe)

    if selected:
        return selected

    return [recipe for recipe in recipes if bool(recipe.get("default_on_unknown", True))]


def run_recipes(recipes: list[dict[str, Any]], repo_root: Path) -> tuple[int, list[str]]:
    total_changed = 0
    logs: list[str] = []
    for recipe in recipes:
        action_name = str(recipe.get("action"))
        action = ACTION_MAP.get(action_name)
        if not action:
            logs.append(f"skip unknown action: {action_name}")
            continue

        changed = action(repo_root)
        total_changed += int(changed)
        logs.append(f"applied {recipe.get('id')} ({action_name}), changed={changed}")

    return total_changed, logs


def open_issue(repo: str, title: str, body: str, labels: list[str], dry_run: bool) -> str:
    if dry_run:
        return "dry-run: issue creation skipped"

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        return "issue skipped: missing GITHUB_TOKEN/GH_TOKEN"

    payload = json.dumps({"title": title, "body": body, "labels": labels}).encode("utf-8")
    url = f"https://api.github.com/repos/{repo}/issues"
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            body_obj = json.loads(resp.read().decode("utf-8"))
            return f"issue created: {body_obj.get('html_url', 'unknown')}"
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        return f"issue creation failed: http {exc.code} {details}"
    except Exception as exc:  # noqa: BLE001
        return f"issue creation failed: {exc}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-repair common failures and retry checks")
    parser.add_argument("--recipes", type=Path, default=Path("repairs/recipes.yaml"))
    parser.add_argument("--check-cmd", default="bash scripts/ci/run_checks.sh")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--log-dir", type=Path, default=Path(".factory/repair"))
    parser.add_argument("--issue-repo", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--issue-title", default="Auto-repair exhausted")
    parser.add_argument("--issue-labels", default="automation,auto-repair")
    parser.add_argument("--open-issue-on-failure", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    if not args.recipes.exists():
        legacy = Path("scripts/repair/recipes.yaml")
        if legacy.exists():
            args.recipes = legacy

    config = read_json(args.recipes)
    recipes = list(config.get("recipes", []))
    if not recipes:
        print("no recipes configured")
        return 1

    last_output = ""
    all_logs: list[str] = []

    for attempt in range(1, args.max_attempts + 1):
        log_path = args.log_dir / f"attempt-{attempt}-check.log"
        code, output = run_check_command(args.check_cmd, log_path)
        last_output = output
        all_logs.append(f"attempt={attempt} check_exit={code} log={log_path}")

        if code == 0:
            print(f"checks passed on attempt {attempt}")
            return 0

        selected = select_recipes(recipes, output)
        changed, repair_logs = run_recipes(selected, repo_root)
        all_logs.extend(repair_logs)
        print(f"attempt {attempt} failed; applied {len(selected)} recipe(s), changed={changed}")
        for line in repair_logs:
            print(f"  {line}")

    failure_note = args.log_dir / "failure-summary.md"
    issue_body = "\n".join(
        [
            f"# Auto-repair exhausted at {now_utc()}",
            "",
            "## Minimal Repro",
            f"- Command: `{args.check_cmd}`",
            f"- Max attempts: `{args.max_attempts}`",
            f"- Last log dir: `{args.log_dir}`",
            "",
            "## Attempt Log",
            *[f"- {line}" for line in all_logs],
            "",
            "## Last Check Output (truncated)",
            "```text",
            last_output[-6000:],
            "```",
        ]
    )
    failure_note.parent.mkdir(parents=True, exist_ok=True)
    failure_note.write_text(issue_body + "\n", encoding="utf-8")
    print(f"repair failed after {args.max_attempts} attempts; summary: {failure_note}")

    if args.open_issue_on_failure and args.issue_repo:
        labels = [label.strip() for label in args.issue_labels.split(",") if label.strip()]
        result = open_issue(
            repo=args.issue_repo,
            title=args.issue_title,
            body=issue_body,
            labels=labels,
            dry_run=args.dry_run,
        )
        print(result)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

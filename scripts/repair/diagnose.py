#!/usr/bin/env python3
"""Diagnose failing checks from local logs + GitHub PR checks summary."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def gh_checks_summary(pr_url: str) -> dict[str, Any]:
    if not pr_url:
        return {"available": False, "reason": "no_pr_url"}
    if not shutil.which("gh"):
        return {"available": False, "reason": "gh_not_found"}

    # Prefer structured output; fallback to plain text when gh version lacks --json.
    cmd_json = ["gh", "pr", "checks", pr_url, "--json", "name,state,link,workflow"]
    proc_json = subprocess.run(cmd_json, text=True, capture_output=True)
    if proc_json.returncode == 0:
        try:
            payload = json.loads(proc_json.stdout)
            failures = [item for item in payload if str(item.get("state", "")).lower() not in {"success", "passed"}]
            return {
                "available": True,
                "mode": "json",
                "items": payload,
                "failures": failures,
            }
        except json.JSONDecodeError:
            pass

    cmd_text = ["gh", "pr", "checks", pr_url]
    proc_text = subprocess.run(cmd_text, text=True, capture_output=True)
    return {
        "available": proc_text.returncode == 0,
        "mode": "text",
        "stdout": proc_text.stdout,
        "stderr": proc_text.stderr,
        "returncode": proc_text.returncode,
    }


def select_recipes(recipes: list[dict[str, Any]], merged_text: str) -> list[str]:
    text = merged_text.lower()
    selected: list[str] = []
    for recipe in recipes:
        recipe_id = str(recipe.get("id", ""))
        keywords = [str(item).lower() for item in recipe.get("trigger_keywords", [])]
        if any(keyword in text for keyword in keywords):
            selected.append(recipe_id)

    if selected:
        return selected

    return [str(recipe.get("id", "")) for recipe in recipes if bool(recipe.get("default_on_unknown", True))]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose failed checks and recommend repair recipes")
    parser.add_argument("--check-log", type=Path, required=True, help="path to local check log")
    parser.add_argument("--recipes", type=Path, default=Path("repairs/recipes.yaml"))
    parser.add_argument("--pr-url", default="", help="GitHub PR URL for gh checks summary")
    parser.add_argument("--out", type=Path, default=Path(".factory/repair/diagnose.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    recipes_obj = read_json(args.recipes)
    recipes = list(recipes_obj.get("recipes", []))

    check_text = read_text(args.check_log)
    gh_summary = gh_checks_summary(args.pr_url)

    gh_text = ""
    if gh_summary.get("mode") == "text":
        gh_text = f"{gh_summary.get('stdout', '')}\n{gh_summary.get('stderr', '')}"
    elif gh_summary.get("mode") == "json":
        gh_text = json.dumps(gh_summary.get("items", []), ensure_ascii=False)

    merged = f"{check_text}\n\n{gh_text}"
    recommended = select_recipes(recipes, merged)

    result = {
        "generated_at": now_utc(),
        "check_log": str(args.check_log),
        "recipes_file": str(args.recipes),
        "pr_url": args.pr_url,
        "recommended_recipe_ids": recommended,
        "gh_checks": gh_summary,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"recommended_recipe_ids": recommended, "diagnose_out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

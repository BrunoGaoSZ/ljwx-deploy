#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "[rollback-drill] 准备临时仓库副本: $TMP_DIR/repo"
cp -R . "$TMP_DIR/repo"
cd "$TMP_DIR/repo"

echo "[rollback-drill] 选择最近 promoted 条目并构造回滚入列项"
python3 - <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import copy
import yaml

queue_path = Path("release/queue.yaml")
payload = yaml.safe_load(queue_path.read_text(encoding="utf-8")) or {}
promoted = payload.get("promoted", [])
if not isinstance(promoted, list) or not promoted:
    raise SystemExit("promoted 列表为空，无法执行回滚演练")

def parse_ts(value: str) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)

candidates = [item for item in promoted if isinstance(item, dict)]
if not candidates:
    raise SystemExit("promoted 无有效条目")

candidates.sort(
    key=lambda item: parse_ts(str(item.get("promotedAt", ""))) or parse_ts(str(item.get("createdAt", ""))),
    reverse=True,
)
base = candidates[0]
service = str(base.get("service", "")).strip()
env = str(base.get("env", "")).strip()
source = copy.deepcopy(base.get("source", {}))
if not service or not env or not isinstance(source, dict):
    raise SystemExit("最近 promoted 条目字段不完整，无法演练")

now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
entry = {
    "id": f"{now}-{service}-{env}-rollback-drill",
    "service": service,
    "env": env,
    "source": source,
    "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "status": "pending",
    "attempts": 0,
    "lastError": "",
    "promotedAt": "",
    "supersededAt": "",
    "failedAt": "",
}

pending = payload.get("pending", [])
if not isinstance(pending, list):
    pending = []
pending.append(entry)
payload["pending"] = pending

queue_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
print(f"rollback drill entry created: {entry['id']}")
PY

echo "[rollback-drill] 校验队列结构"
uvx --with pyyaml python scripts/promoter/validate_queue.py --queue release/queue.yaml

echo "[rollback-drill] 执行 promoter dry-run（仅模拟，不提交）"
uvx --with pyyaml --with jsonschema python scripts/promoter/promote.py \
  --dry-run \
  --local-repo-dir .

echo "[rollback-drill] 演练完成"

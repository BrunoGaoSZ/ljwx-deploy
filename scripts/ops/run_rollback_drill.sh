#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
KNOWLEDGE_REPO="${KNOWLEDGE_REPO:-$(cd "$ROOT_DIR/.." && pwd)/ljwx-knowledge}"
CORE_API_REPO="${CORE_API_REPO:-$(cd "$ROOT_DIR/.." && pwd)/ljwx-core-api}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

DEPLOY_COPY="$TMP_DIR/ljwx-deploy"
KNOWLEDGE_COPY="$TMP_DIR/ljwx-knowledge"
CORE_API_COPY="$TMP_DIR/ljwx-core-api"

echo "[rollback-drill] 准备临时副本"
cp -R "$ROOT_DIR" "$DEPLOY_COPY"
if [[ -d "$KNOWLEDGE_REPO" ]]; then
  cp -R "$KNOWLEDGE_REPO" "$KNOWLEDGE_COPY"
fi
if [[ -d "$CORE_API_REPO" ]]; then
  cp -R "$CORE_API_REPO" "$CORE_API_COPY"
fi

echo "[rollback-drill] 路由配置回滚演练"
python3 - "$DEPLOY_COPY" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

import yaml

repo = Path(sys.argv[1])
path = repo / "platform" / "routing" / "routes.dev.yaml"
original = path.read_text(encoding="utf-8")
payload = yaml.safe_load(original)
routes = payload.get("routes", [])
if not isinstance(routes, list) or not routes:
    raise SystemExit("routes.dev.yaml 缺少 routes")

for route in routes:
    if isinstance(route, dict) and route.get("id") == "general_chat":
        route["tool_policy"] = "capability_registry"
        break
else:
    raise SystemExit("未找到 general_chat route")

path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
(repo / ".rollback-route-original.yaml").write_text(original, encoding="utf-8")
print("route mutation prepared")
PY

(
  cd "$DEPLOY_COPY"
  uvx --with pyyaml --with jsonschema python scripts/platform/validate_router_contracts.py
)

python3 - "$DEPLOY_COPY" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

repo = Path(sys.argv[1])
path = repo / "platform" / "routing" / "routes.dev.yaml"
original = (repo / ".rollback-route-original.yaml").read_text(encoding="utf-8")
path.write_text(original, encoding="utf-8")
if path.read_text(encoding="utf-8") != original:
    raise SystemExit("路由配置未成功恢复到原始内容")
print("route rollback restored")
PY

(
  cd "$DEPLOY_COPY"
  uvx --with pyyaml --with jsonschema python scripts/platform/validate_router_contracts.py
)

echo "[rollback-drill] 知识撤回演练"
if [[ ! -d "$KNOWLEDGE_COPY" ]]; then
  echo "[rollback-drill] 跳过知识演练：未找到仓库 $KNOWLEDGE_REPO"
else
  (
    cd "$KNOWLEDGE_COPY"
    uv run ljwx-knowledge --deploy-root "$DEPLOY_COPY" run --env dev >/tmp/knowledge-run-before.json
    uv run ljwx-knowledge --deploy-root "$DEPLOY_COPY" invalidate --env dev \
      --document-id public-routing-faq --reason rollback_drill >/tmp/knowledge-invalidate.json
  )

  python3 - "$KNOWLEDGE_COPY" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

repo = Path(sys.argv[1])
dataset_path = repo / "datasets" / "dev" / "public-knowledge.jsonl"
rows = [
    json.loads(line)
    for line in dataset_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
if any(row.get("document_id") == "public-routing-faq" for row in rows):
    raise SystemExit("invalidate 后 public-routing-faq 仍然存在于 dataset")
print("knowledge invalidate verified")
PY

  (
    cd "$KNOWLEDGE_COPY"
    uv run ljwx-knowledge --deploy-root "$DEPLOY_COPY" run --env dev >/tmp/knowledge-run-after.json
  )

  python3 - "$KNOWLEDGE_COPY" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

repo = Path(sys.argv[1])
dataset_path = repo / "datasets" / "dev" / "public-knowledge.jsonl"
rows = [
    json.loads(line)
    for line in dataset_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
if not any(row.get("document_id") == "public-routing-faq" for row in rows):
    raise SystemExit("重新 publish 后 public-routing-faq 未恢复")
print("knowledge rollback restored")
PY
fi

echo "[rollback-drill] gateway profile 回滚演练"
if [[ ! -d "$CORE_API_COPY" ]]; then
  echo "[rollback-drill] 跳过 gateway 演练：未找到仓库 $CORE_API_REPO"
else
  python3 - "$CORE_API_COPY" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

import yaml

repo = Path(sys.argv[1])
path = repo / "config" / "tool_profiles.yaml"
original = path.read_text(encoding="utf-8")
payload = yaml.safe_load(original)
profiles = payload.get("profiles", {})
default = profiles.get("default")
if not isinstance(default, dict):
    raise SystemExit("tool_profiles.yaml 缺少 default profile")
default["allowed_capabilities"] = ["customer.lookup"]
path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
(repo / ".rollback-gateway-original.yaml").write_text(original, encoding="utf-8")
print("gateway whitelist mutation prepared")
PY

  python3 - "$CORE_API_COPY" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

import yaml

repo = Path(sys.argv[1])
payload = yaml.safe_load((repo / "config" / "tool_profiles.yaml").read_text(encoding="utf-8"))
capabilities = payload["profiles"]["default"]["allowed_capabilities"]
if "conversation.audit.write" in capabilities:
    raise SystemExit("gateway 白名单变更未生效")
print("gateway mutation verified")
PY

  python3 - "$CORE_API_COPY" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

repo = Path(sys.argv[1])
path = repo / "config" / "tool_profiles.yaml"
original = (repo / ".rollback-gateway-original.yaml").read_text(encoding="utf-8")
path.write_text(original, encoding="utf-8")
print("gateway rollback restored")
PY

  (
    cd "$CORE_API_COPY"
    uv run pytest tests/test_capability_gateway.py -q
  )
fi

echo "[rollback-drill] 三段演练完成"

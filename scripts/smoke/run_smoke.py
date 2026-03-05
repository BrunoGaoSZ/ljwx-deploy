#!/usr/bin/env python3
"""Smoke runner that updates YAML evidence records after promotion."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # noqa: BLE001
    raise SystemExit(
        f"PyYAML is required. Install with: uvx --with pyyaml python <script>\n{exc}"
    )


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


QUEUE_STATES = ("pending", "promoted", "failed", "superseded")


@dataclass(frozen=True)
class TargetResult:
    outcome: str
    message: str
    service: str
    source_env: str
    source_queue_id: str


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"evidence record root must be mapping: {path}")
    return raw


def read_queue(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"queue root must be mapping: {path}")
    return raw


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def ensure_queue_shape(queue_payload: dict[str, Any]) -> dict[str, Any]:
    for state in QUEUE_STATES:
        if not isinstance(queue_payload.get(state), list):
            queue_payload[state] = []
    return queue_payload


def parse_ts(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    txt = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def record_timestamp(record: dict[str, Any]) -> datetime:
    deploy = record.get("deploy", {})
    synced_at = deploy.get("syncedAt") if isinstance(deploy, dict) else None
    promoted_at = record.get("promotedAt")
    ts = parse_ts(synced_at)
    if ts != datetime.min.replace(tzinfo=timezone.utc):
        return ts
    return parse_ts(promoted_at)


def record_files(evidence_dir: Path) -> list[Path]:
    return sorted([p for p in evidence_dir.glob("*.yaml") if p.is_file()])


def find_record_path(
    evidence_dir: Path,
    service: str,
    environment: str,
    queue_id: str | None,
    prefer_pending: bool,
) -> Path | None:
    candidates: list[tuple[datetime, Path]] = []
    for path in record_files(evidence_dir):
        try:
            record = read_yaml(path)
        except Exception:  # noqa: BLE001
            continue

        if record.get("service") != service or record.get("env") != environment:
            continue

        deploy = record.get("deploy", {})
        if (
            queue_id
            and isinstance(deploy, dict)
            and str(deploy.get("queueId", "")) != str(queue_id)
        ):
            continue

        smoke_status = (
            record.get("tests", {}).get("smoke", {}).get("status")
            if isinstance(record.get("tests"), dict)
            else None
        )
        if smoke_status not in {"pending", "pass", "fail", "unknown", None}:
            continue
        if prefer_pending and smoke_status != "pending":
            continue

        candidates.append((record_timestamp(record), path))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def latest_promoted_queue_id(
    queue_payload: dict[str, Any], service: str, env: str
) -> str:
    promoted = queue_payload.get("promoted", [])
    if not isinstance(promoted, list):
        return ""

    candidates: list[tuple[datetime, str]] = []
    for item in promoted:
        if not isinstance(item, dict):
            continue
        if str(item.get("service", "")).strip() != service:
            continue
        if str(item.get("env", "")).strip() != env:
            continue
        queue_id = str(item.get("id", "")).strip()
        if not queue_id:
            continue
        promoted_at = parse_ts(item.get("promotedAt"))
        created_at = parse_ts(item.get("createdAt"))
        ts = (
            promoted_at
            if promoted_at > datetime.min.replace(tzinfo=timezone.utc)
            else created_at
        )
        candidates.append((ts, queue_id))

    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def entry_id(entry: dict[str, Any]) -> str:
    return str(entry.get("id", "")).strip()


def entry_digest(entry: dict[str, Any]) -> str:
    source = entry.get("source", {}) if isinstance(entry.get("source"), dict) else {}
    digest = str(source.get("digest", "")).strip()
    if digest:
        return digest

    ghcr = str(source.get("ghcr", "")).strip()
    if "@" in ghcr:
        return ghcr.rsplit("@", 1)[1]
    return ""


def queue_entry_by_id(
    queue_payload: dict[str, Any], queue_id: str
) -> dict[str, Any] | None:
    for state in QUEUE_STATES:
        items = queue_payload.get(state, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if entry_id(item) == queue_id:
                return item
    return None


def has_release_with_digest(
    queue_payload: dict[str, Any], service: str, target_env: str, digest: str
) -> bool:
    for state in ("pending", "promoted"):
        items = queue_payload.get(state, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("service", "")).strip() != service:
                continue
            if str(item.get("env", "")).strip() != target_env:
                continue
            if entry_digest(item) == digest:
                return True
    return False


def safe_token(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "-", value.strip())
    return cleaned or "unknown"


def build_prod_pending_entry(
    service: str, target_env: str, source_entry: dict[str, Any]
) -> dict[str, Any]:
    source = (
        source_entry.get("source", {})
        if isinstance(source_entry.get("source"), dict)
        else {}
    )
    tag = str(source.get("tag", "")).strip() or "sha-unknown"
    digest = entry_digest(source_entry)
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    queue_id = (
        f"{compact_ts}-{safe_token(service)}-{safe_token(tag)}-{safe_token(target_env)}"
    )

    source_payload: dict[str, str] = {
        "ghcr": str(source.get("ghcr", "")).strip(),
        "tag": tag,
        "digest": digest,
    }
    git_sha = str(source.get("gitSha", "")).strip()
    if git_sha:
        source_payload["gitSha"] = git_sha

    return {
        "id": queue_id,
        "service": service,
        "env": target_env,
        "source": source_payload,
        "createdAt": now_utc(),
        "status": "pending",
        "attempts": 0,
        "lastError": "",
        "promotedAt": "",
        "supersededAt": "",
        "failedAt": "",
        "meta": {
            "autoPromoteBySmoke": True,
            "sourceQueueId": entry_id(source_entry),
        },
    }


def enqueue_prod_from_smoke(
    queue_payload: dict[str, Any], results: list[TargetResult], target_env: str
) -> tuple[int, list[str]]:
    pending = queue_payload.get("pending", [])
    if not isinstance(pending, list):
        raise ValueError("queue.pending 必须是列表")

    messages: list[str] = []
    enqueued = 0
    for result in results:
        if result.outcome != "pass":
            continue
        if result.source_env == target_env:
            continue
        if not result.source_queue_id:
            messages.append(f"[auto-prod] 跳过 {result.service}: 缺少来源 queue_id")
            continue

        source_entry = queue_entry_by_id(queue_payload, result.source_queue_id)
        if source_entry is None:
            messages.append(
                f"[auto-prod] 跳过 {result.service}: 未找到来源 queue_id={result.source_queue_id}"
            )
            continue

        digest = entry_digest(source_entry)
        if not digest:
            messages.append(f"[auto-prod] 跳过 {result.service}: 来源 digest 为空")
            continue

        if has_release_with_digest(
            queue_payload=queue_payload,
            service=result.service,
            target_env=target_env,
            digest=digest,
        ):
            messages.append(
                f"[auto-prod] 已存在 {result.service}/{target_env} 同 digest 记录，跳过"
            )
            continue

        entry = build_prod_pending_entry(
            service=result.service, target_env=target_env, source_entry=source_entry
        )
        base_id = str(entry["id"])
        index = 1
        while queue_entry_by_id(queue_payload, str(entry["id"])) is not None:
            index += 1
            entry["id"] = f"{base_id}-r{index}"

        pending.append(entry)
        enqueued += 1
        messages.append(
            f"[auto-prod] 已入队 {result.service}/{target_env}: {entry['id']}"
        )

    return enqueued, messages


def load_service_map(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {"services": {}}
    if not isinstance(raw, dict):
        raise ValueError(f"service map root must be mapping: {path}")
    services = raw.get("services", {})
    if not isinstance(services, dict):
        raise ValueError(f"service map requires 'services' mapping: {path}")
    raw["services"] = services
    return raw


def resolve_service_target(
    service_map: dict[str, Any], service: str, env: str
) -> dict[str, Any]:
    services = service_map.get("services", {})
    if not isinstance(services, dict):
        return {}
    svc = services.get(service, {})
    if not isinstance(svc, dict):
        return {}
    envs = svc.get("envs", {})
    if not isinstance(envs, dict):
        return {}
    target = envs.get(env, {})
    return target if isinstance(target, dict) else {}


def image_without_reference(image_ref: str) -> str:
    image = image_ref.strip()
    if "@" in image:
        image = image.split("@", 1)[0]
    slash = image.rfind("/")
    colon = image.rfind(":")
    if colon > slash:
        image = image[:colon]
    return image


def image_registry_and_repo(image_ref: str) -> tuple[str, str]:
    image = image_without_reference(image_ref)
    if not image:
        return "", ""

    if image.startswith("https://") or image.startswith("http://"):
        stripped = image.split("//", 1)[1]
        parts = stripped.split("/", 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]

    first = image.split("/", 1)[0]
    if "." in first or ":" in first or first == "localhost":
        return first, image.split("/", 1)[1] if "/" in image else ""
    return "", image


def harbor_repo_path(harbor_image: str) -> str:
    _, image_repo = image_registry_and_repo(harbor_image)
    return image_repo


def harbor_project_and_repository(repo_path: str) -> tuple[str, str]:
    parts = [segment for segment in repo_path.split("/") if segment]
    if len(parts) < 2:
        return "", ""
    project = parts[0]
    repository = "/".join(parts[1:])
    return project, repository


def basic_auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("utf-8")
    return f"Basic {token}"


def http_request(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None,
    timeout: float,
) -> tuple[int, str]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(8192).decode("utf-8", errors="ignore")
            return int(resp.getcode() or 0), body
    except urllib.error.HTTPError as exc:
        body = exc.read(8192).decode("utf-8", errors="ignore")
        return int(exc.code), body


def build_prod_ready_tag(source_entry: dict[str, Any], prefix: str) -> str:
    normalized_prefix = safe_token(prefix or "prod-")
    if not normalized_prefix.endswith("-"):
        normalized_prefix = f"{normalized_prefix}-"

    source = (
        source_entry.get("source", {})
        if isinstance(source_entry.get("source"), dict)
        else {}
    )
    source_tag_raw = str(source.get("tag", "")).strip()
    if source_tag_raw:
        source_tag = safe_token(source_tag_raw)
        if source_tag.startswith(normalized_prefix):
            return source_tag
        return f"{normalized_prefix}{source_tag}"

    digest = entry_digest(source_entry)
    digest_token = safe_token(digest.replace(":", "-")) if digest else "unknown"
    return f"{normalized_prefix}{digest_token[:48]}"


def harbor_tag_digest(
    harbor_url: str,
    harbor_user: str,
    harbor_pass: str,
    repo_path: str,
    digest: str,
    target_tag: str,
    dry_run: bool,
) -> tuple[bool, str]:
    if not harbor_url.strip():
        return False, "缺少本地 Harbor 地址"
    if not digest:
        return False, "缺少 digest"

    project, repository = harbor_project_and_repository(repo_path)
    if not project or not repository:
        return False, f"无法解析 Harbor 仓库路径: {repo_path}"

    if dry_run:
        return (
            True,
            f"[auto-prod-tag] dry-run {project}/{repository}@{digest} -> {target_tag}",
        )

    project_encoded = urllib.parse.quote(project, safe="")
    repo_encoded = urllib.parse.quote(repository, safe="")
    digest_encoded = urllib.parse.quote(digest, safe="")
    artifact_endpoint = (
        f"{harbor_url.rstrip('/')}/api/v2.0/projects/{project_encoded}/repositories/"
        f"{repo_encoded}/artifacts/{digest_encoded}"
    )

    headers = {"Accept": "application/json"}
    if harbor_user or harbor_pass:
        headers["Authorization"] = basic_auth_header(harbor_user, harbor_pass)

    check_code, check_body = http_request(
        method="GET",
        url=artifact_endpoint,
        headers=headers,
        payload=None,
        timeout=8.0,
    )
    if check_code != 200:
        snippet = check_body[:160].replace("\n", " ")
        return False, f"artifact 检查失败 http={check_code} body={snippet}"

    tag_endpoint = f"{artifact_endpoint}/tags"
    create_code, create_body = http_request(
        method="POST",
        url=tag_endpoint,
        headers={**headers, "Content-Type": "application/json"},
        payload={"name": target_tag},
        timeout=8.0,
    )
    if create_code in {200, 201, 202}:
        return True, f"[auto-prod-tag] 已创建 {project}/{repository}:{target_tag}"
    if create_code == 409:
        return True, f"[auto-prod-tag] 已存在 {project}/{repository}:{target_tag}"

    snippet = create_body[:160].replace("\n", " ")
    return False, f"创建 tag 失败 http={create_code} body={snippet}"


def tag_local_harbor_from_smoke(
    queue_payload: dict[str, Any],
    results: list[TargetResult],
    service_map: dict[str, Any],
    target_env: str,
    harbor_url: str,
    harbor_user: str,
    harbor_pass: str,
    tag_prefix: str,
    dry_run: bool,
) -> tuple[list[TargetResult], int, int, list[str]]:
    tagged_results: list[TargetResult] = []
    messages: list[str] = []
    tagged_count = 0
    failed_count = 0

    for result in results:
        if result.outcome != "pass":
            continue
        if result.source_env == target_env:
            continue

        if not harbor_url.strip():
            failed_count += 1
            messages.append("[auto-prod-tag] 缺少 local Harbor 配置，无法执行打标")
            continue
        if not result.source_queue_id:
            failed_count += 1
            messages.append(f"[auto-prod-tag] 失败 {result.service}: 缺少来源 queue_id")
            continue

        source_entry = queue_entry_by_id(queue_payload, result.source_queue_id)
        if source_entry is None:
            failed_count += 1
            messages.append(
                f"[auto-prod-tag] 失败 {result.service}: 未找到来源 queue_id={result.source_queue_id}"
            )
            continue

        digest = entry_digest(source_entry)
        if not digest:
            failed_count += 1
            messages.append(f"[auto-prod-tag] 失败 {result.service}: 来源 digest 为空")
            continue

        target = resolve_service_target(service_map, result.service, result.source_env)
        harbor_image = str(target.get("harborImage", "")).strip()
        repo_path = harbor_repo_path(harbor_image)
        if not repo_path:
            # Fallback to default naming convention used by new onboarded services.
            repo_path = f"ljwx/{safe_token(result.service)}"

        tag_name = build_prod_ready_tag(source_entry, prefix=tag_prefix)
        ok, detail = harbor_tag_digest(
            harbor_url=harbor_url,
            harbor_user=harbor_user,
            harbor_pass=harbor_pass,
            repo_path=repo_path,
            digest=digest,
            target_tag=tag_name,
            dry_run=dry_run,
        )
        if ok:
            tagged_results.append(result)
            tagged_count += 1
            messages.append(
                f"{detail} (service={result.service}, env={result.source_env}, queue={result.source_queue_id})"
            )
        else:
            failed_count += 1
            messages.append(
                f"[auto-prod-tag] 失败 {result.service}/{result.source_env}: {detail}"
            )

    return tagged_results, tagged_count, failed_count, messages


def http_get(
    url: str, headers: dict[str, str] | None = None, timeout: float = 5.0
) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(4096).decode("utf-8", errors="ignore")
        return int(resp.getcode() or 0), body


def wait_for_argocd_health(
    server: str,
    token: str,
    app: str,
    timeout_seconds: int,
    interval_seconds: int,
) -> tuple[bool, str]:
    if not server or not token or not app:
        return True, "argocd check skipped"

    end = time.time() + timeout_seconds
    app_encoded = urllib.parse.quote(app, safe="")
    url = f"{server.rstrip('/')}/api/v1/applications/{app_encoded}"
    headers = {"Authorization": f"Bearer {token}"}

    last = ""
    while time.time() < end:
        try:
            code, body = http_get(url, headers=headers, timeout=8.0)
            if code < 300:
                data = json.loads(body)
                status = data.get("status", {})
                sync = status.get("sync", {}).get("status")
                health = status.get("health", {}).get("status")
                last = f"sync={sync},health={health}"
                if sync == "Synced" and health == "Healthy":
                    return True, last
        except Exception as exc:  # noqa: BLE001
            last = str(exc)

        time.sleep(interval_seconds)

    return False, f"argocd wait timeout: {last}"


def wait_for_endpoint(
    endpoint: str, timeout_seconds: int, interval_seconds: int
) -> tuple[bool, str]:
    end = time.time() + timeout_seconds
    last = ""

    while time.time() < end:
        try:
            code, body = http_get(endpoint, timeout=8.0)
            if 200 <= code < 400:
                snippet = body[:120].replace("\n", " ")
                return True, f"endpoint={code} body='{snippet}'"
            last = f"http={code}"
        except urllib.error.HTTPError as exc:
            last = f"http={exc.code}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)

        time.sleep(interval_seconds)

    return False, f"endpoint wait timeout: {last}"


def update_smoke_record(path: Path, ok: bool, details: str, dry_run: bool) -> None:
    record = read_yaml(path)
    tests = record.setdefault("tests", {})
    smoke = tests.setdefault("smoke", {})
    smoke["status"] = "pass" if ok else "fail"
    smoke["checkedAt"] = now_utc()
    smoke["details"] = details

    deploy = record.setdefault("deploy", {})
    if isinstance(deploy, dict):
        deploy["smokedAt"] = now_utc()

    if not dry_run:
        write_yaml(path, record)


def run_target(
    target: dict[str, Any], args: argparse.Namespace, queue_payload: dict[str, Any]
) -> TargetResult:
    service = str(target.get("service", "")).strip()
    environment = str(target.get("environment", "dev")).strip()
    queue_id = str(target.get("queue_id", "")).strip()
    app = str(target.get("argocd_app", "")).strip()
    endpoint = str(target.get("endpoint", "")).strip()

    if not service or not endpoint:
        return TargetResult(
            outcome="fail",
            message=f"invalid target: {target}",
            service=service or "<unknown>",
            source_env=environment or "dev",
            source_queue_id=queue_id,
        )

    resolved_queue_id = queue_id or latest_promoted_queue_id(
        queue_payload=queue_payload,
        service=service,
        env=environment,
    )
    record_path = find_record_path(
        evidence_dir=args.evidence_dir,
        service=service,
        environment=environment,
        queue_id=resolved_queue_id or None,
        prefer_pending=True,
    )
    if not record_path:
        record_path = find_record_path(
            evidence_dir=args.evidence_dir,
            service=service,
            environment=environment,
            queue_id=resolved_queue_id or None,
            prefer_pending=False,
        )
    if not record_path:
        return TargetResult(
            outcome="skip",
            message=f"{service}: no promoted evidence record for {service}/{environment} (queue={resolved_queue_id or '-'})",
            service=service,
            source_env=environment,
            source_queue_id=resolved_queue_id,
        )

    ok_argocd, argocd_details = wait_for_argocd_health(
        server=args.argocd_server,
        token=args.argocd_token,
        app=app,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.interval_seconds,
    )
    if not ok_argocd:
        update_smoke_record(record_path, False, argocd_details, args.dry_run)
        return TargetResult(
            outcome="fail",
            message=f"{service}: {argocd_details}",
            service=service,
            source_env=environment,
            source_queue_id=resolved_queue_id,
        )

    ok_endpoint, endpoint_details = wait_for_endpoint(
        endpoint=endpoint,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.interval_seconds,
    )

    details = f"{argocd_details}; {endpoint_details}"
    update_smoke_record(record_path, ok_endpoint, details, args.dry_run)
    if ok_endpoint:
        return TargetResult(
            outcome="pass",
            message=f"{service}: {details}",
            service=service,
            source_env=environment,
            source_queue_id=resolved_queue_id,
        )
    return TargetResult(
        outcome="fail",
        message=f"{service}: {details}",
        service=service,
        source_env=environment,
        source_queue_id=resolved_queue_id,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run smoke checks and write evidence results"
    )
    parser.add_argument(
        "--targets", type=Path, default=Path("scripts/smoke/targets.json")
    )
    parser.add_argument("--queue", type=Path, default=Path("release/queue.yaml"))
    parser.add_argument("--evidence-dir", type=Path, default=Path("evidence/records"))
    parser.add_argument("--argocd-server", default=os.getenv("ARGOCD_SERVER", ""))
    parser.add_argument("--argocd-token", default=os.getenv("ARGOCD_TOKEN", ""))
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--interval-seconds", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--auto-enqueue-prod",
        action="store_true",
        help="smoke 通过后自动入队目标生产环境",
    )
    parser.add_argument(
        "--prod-env",
        default=os.getenv("SMOKE_AUTO_PROD_ENV", "prod"),
        help="自动入队目标环境（默认: prod）",
    )
    parser.add_argument(
        "--service-map",
        type=Path,
        default=Path(
            os.getenv("SMOKE_SERVICE_MAP_PATH", "release/services.local-k3s.yaml")
        ),
        help="用于解析 harborImage 的 service map",
    )
    parser.add_argument(
        "--auto-tag-local-harbor",
        action="store_true",
        help="smoke 通过后自动给本地 Harbor artifact 打生产标签（prod-*）",
    )
    parser.add_argument(
        "--local-harbor-url",
        default=os.getenv("HARBOR_LOCAL_URL", os.getenv("HARBOR_URL", "")),
        help="本地 Harbor 地址（用于自动打标）",
    )
    parser.add_argument(
        "--local-harbor-user",
        default=os.getenv("HARBOR_LOCAL_USER", os.getenv("HARBOR_USER", "")),
        help="本地 Harbor 用户名（用于自动打标）",
    )
    parser.add_argument(
        "--local-harbor-pass",
        default=os.getenv("HARBOR_LOCAL_PASS", os.getenv("HARBOR_PASS", "")),
        help="本地 Harbor 密码（用于自动打标）",
    )
    parser.add_argument(
        "--local-harbor-prod-tag-prefix",
        default=os.getenv("LOCAL_HARBOR_PROD_TAG_PREFIX", "prod-"),
        help="本地 Harbor 生产标签前缀（默认: prod-）",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="return zero even when smoke failures exist (useful for CI structural checks)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = read_json(args.targets)
    targets = list(config.get("targets", []))
    queue_payload = ensure_queue_shape(read_queue(args.queue))

    passed = 0
    failed = 0
    skipped = 0
    results: list[TargetResult] = []
    for target in targets:
        result = run_target(target, args, queue_payload)
        results.append(result)
        print(result.message)
        if result.outcome == "pass":
            passed += 1
        elif result.outcome == "fail":
            failed += 1
        else:
            skipped += 1

    enqueue_candidates = results
    auto_tagged_local = 0
    auto_tag_failed = 0
    if args.auto_tag_local_harbor:
        try:
            service_map = load_service_map(args.service_map)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            auto_tag_failed = sum(
                1
                for item in results
                if item.outcome == "pass" and item.source_env != args.prod_env
            )
            enqueue_candidates = []
            print(f"[auto-prod-tag] 加载 service map 失败: {exc}")
            failed += auto_tag_failed
        else:
            (
                enqueue_candidates,
                auto_tagged_local,
                auto_tag_failed,
                tag_messages,
            ) = tag_local_harbor_from_smoke(
                queue_payload=queue_payload,
                results=results,
                service_map=service_map,
                target_env=args.prod_env,
                harbor_url=args.local_harbor_url,
                harbor_user=args.local_harbor_user,
                harbor_pass=args.local_harbor_pass,
                tag_prefix=args.local_harbor_prod_tag_prefix,
                dry_run=args.dry_run,
            )
            for line in tag_messages:
                print(line)
            failed += auto_tag_failed

    auto_enqueued = 0
    if args.auto_enqueue_prod:
        auto_enqueued, enqueue_messages = enqueue_prod_from_smoke(
            queue_payload=queue_payload,
            results=enqueue_candidates,
            target_env=args.prod_env,
        )
        for line in enqueue_messages:
            print(line)
        if auto_enqueued > 0 and not args.dry_run:
            write_yaml(args.queue, queue_payload)

    print(
        json.dumps(
            {
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "auto_tagged_local_harbor": auto_tagged_local,
                "auto_tag_local_harbor_failed": auto_tag_failed,
                "auto_enqueued_prod": auto_enqueued,
                "dry_run": args.dry_run,
                "allow_failures": args.allow_failures,
            }
        )
    )
    return 0 if failed == 0 or args.allow_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

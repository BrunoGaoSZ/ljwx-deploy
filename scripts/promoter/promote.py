#!/usr/bin/env python3
"""Method-1 release queue promoter (idempotent, per-service serialized)."""

from __future__ import annotations

import argparse
import copy
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # noqa: BLE001
    raise SystemExit(f"PyYAML is required. Install with: pip3 install pyyaml\n{exc}")


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    txt = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def yaml_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if data is None:
        return copy.deepcopy(default)
    return data


def yaml_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def ensure_queue_shape(queue: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "pending": list(queue.get("pending", [])),
        "promoted": list(queue.get("promoted", [])),
        "failed": list(queue.get("failed", [])),
        "superseded": list(queue.get("superseded", [])),
    }


def entry_id(entry: dict[str, Any]) -> str:
    return str(entry.get("id", "")).strip()


def by_id(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in entries:
        eid = entry_id(e)
        if eid:
            out[eid] = e
    return out


def upsert_entry(entries: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    eid = entry_id(entry)
    if not eid:
        entries.append(entry)
        return
    for idx, it in enumerate(entries):
        if entry_id(it) == eid:
            entries[idx] = entry
            return
    entries.append(entry)


def get_digest(entry: dict[str, Any]) -> str:
    source = entry.get("source", {}) if isinstance(entry.get("source"), dict) else {}
    digest = str(source.get("digest", "")).strip()
    if digest:
        return digest

    ghcr = str(source.get("ghcr", "")).strip()
    if "@" in ghcr:
        digest = ghcr.rsplit("@", 1)[1]
    return digest


def host_from_url(url: str) -> str:
    txt = url.strip()
    if "://" in txt:
        txt = txt.split("://", 1)[1]
    return txt.strip("/")


def image_without_digest(image_ref: str) -> str:
    image = image_ref.strip()
    if "@" in image:
        return image.split("@", 1)[0]
    return image


def image_registry_and_repo(image_ref: str) -> tuple[str, str]:
    image = image_without_digest(image_ref)
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


def harbor_repo_path(harbor_image: str, harbor_url: str) -> str:
    harbor_host = host_from_url(harbor_url)
    image_host, image_repo = image_registry_and_repo(harbor_image)
    if not image_repo:
        return ""

    if harbor_host and image_host and image_host != harbor_host:
        return ""

    return image_repo


def harbor_manifest_ready(
    harbor_image: str, digest: str, harbor_url: str, harbor_user: str, harbor_pass: str
) -> bool:
    if not harbor_url.strip():
        return False

    repo = harbor_repo_path(harbor_image, harbor_url)
    if not repo or not digest:
        return False

    endpoint = f"{harbor_url.rstrip('/')}/v2/{repo}/manifests/{digest}"
    accept = "application/vnd.oci.image.manifest.v1+json"
    base = ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}"]
    if harbor_user or harbor_pass:
        base += ["-u", f"{harbor_user}:{harbor_pass}"]

    head_cmd = base + ["-I", "-H", f"Accept: {accept}", endpoint]
    head = subprocess.run(head_cmd, text=True, capture_output=True)
    if head.returncode == 0 and head.stdout.strip() == "200":
        return True

    get_cmd = base + ["-X", "GET", "-H", f"Accept: {accept}", endpoint]
    get = subprocess.run(get_cmd, text=True, capture_output=True)
    return get.returncode == 0 and get.stdout.strip() == "200"


def ghcr_repo(ghcr_ref: str) -> str:
    return ghcr_ref.split("@", 1)[0] if "@" in ghcr_ref else ghcr_ref


def commit_from_tag(tag: str) -> str:
    return (
        tag[4:]
        if isinstance(tag, str) and tag.startswith("sha-") and len(tag) > 4
        else "unknown"
    )


def safe_tag(tag: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "-", tag or "unknown")


def build_evidence_id(entry: dict[str, Any], promoted_at: str) -> str:
    if entry.get("evidenceId"):
        return str(entry["evidenceId"])
    service = str(entry.get("service", "svc"))
    tag = str(entry.get("source", {}).get("tag", "unknown"))
    date = parse_ts(promoted_at).strftime("%Y%m%d")
    return f"{date}-{service}-{safe_tag(tag)}"


def load_service_map(path: Path) -> dict[str, Any]:
    data = yaml_load(path, default={"services": {}})
    if not isinstance(data, dict):
        raise ValueError(f"service map root must be mapping: {path}")
    services = data.get("services", {})
    if not isinstance(services, dict):
        raise ValueError("service map requires 'services' mapping")
    data["services"] = services
    return data


def resolve_target(
    service_map: dict[str, Any], service: str, env: str
) -> dict[str, Any]:
    services = service_map.get("services", {})
    svc = services.get(service, {}) if isinstance(services, dict) else {}
    if not isinstance(svc, dict):
        return {}

    envs = svc.get("envs", {})
    if isinstance(envs, dict):
        cfg = envs.get(env, {})
        if isinstance(cfg, dict):
            return cfg

    return {}


def normalize_pending(
    queue: dict[str, list[dict[str, Any]]], now: str
) -> tuple[dict[str, list[dict[str, Any]]], bool]:
    changed = False
    pending = queue["pending"]
    promoted_ids = set(by_id(queue["promoted"]).keys())
    failed_ids = set(by_id(queue["failed"]).keys())
    superseded_ids = set(by_id(queue["superseded"]).keys())

    filtered: list[dict[str, Any]] = []
    for entry in pending:
        eid = entry_id(entry)
        if eid and (eid in promoted_ids or eid in failed_ids or eid in superseded_ids):
            changed = True
            continue
        filtered.append(entry)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in filtered:
        key = (
            str(entry.get("service", "")).strip(),
            str(entry.get("env", "dev")).strip(),
        )
        grouped.setdefault(key, []).append(entry)

    new_pending: list[dict[str, Any]] = []
    for (_svc, _env), entries in grouped.items():
        entries.sort(key=lambda e: parse_ts(e.get("createdAt")))
        keeper = entries[-1]
        new_pending.append(keeper)

        for older in entries[:-1]:
            moved = copy.deepcopy(older)
            moved["status"] = "superseded"
            moved["supersededAt"] = now
            moved["reason"] = "replaced by newer pending release for same service+env"
            upsert_entry(queue["superseded"], moved)
            changed = True

    if len(new_pending) != len(queue["pending"]):
        changed = True
    queue["pending"] = new_pending
    return queue, changed


def update_overlay_kustomization(
    overlay_path: Path,
    image_name: str,
    harbor_image: str,
    digest: str,
) -> tuple[Path, bool, dict[str, Any]]:
    data = yaml_load(overlay_path, default={})
    if not isinstance(data, dict):
        raise ValueError(f"overlay root must be mapping: {overlay_path}")

    before = copy.deepcopy(data)
    images = data.get("images", [])
    if not isinstance(images, list):
        images = []

    idx: int | None = None
    for i, item in enumerate(images):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        new_name = str(item.get("newName", "")).strip()
        if image_name in {name, new_name} or harbor_image in {name, new_name}:
            idx = i
            break

    target = (
        copy.deepcopy(images[idx])
        if idx is not None and isinstance(images[idx], dict)
        else {}
    )
    target["name"] = image_name
    target["newName"] = harbor_image
    target["digest"] = digest
    if "newTag" in target:
        del target["newTag"]

    if idx is None:
        images.append(target)
    else:
        images[idx] = target

    data["images"] = images
    changed = before != data
    return overlay_path, changed, data


def process_pending(
    queue: dict[str, list[dict[str, Any]]],
    repo_dir: Path,
    service_map: dict[str, Any],
    retry_max: int,
    harbor_url: str,
    harbor_user: str,
    harbor_pass: str,
    skip_registry_check: bool,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[Path, dict[str, Any]],
    dict[Path, dict[str, Any]],
    list[dict[str, str]],
    bool,
]:
    now = now_rfc3339()
    queue, changed = normalize_pending(queue, now)

    overlay_changes: dict[Path, dict[str, Any]] = {}
    evidence_changes: dict[Path, dict[str, Any]] = {}
    promoted_meta: list[dict[str, str]] = []

    for entry in list(queue["pending"]):
        service = str(entry.get("service", "")).strip()
        env = str(entry.get("env", "dev")).strip() or "dev"
        source = (
            entry.get("source", {}) if isinstance(entry.get("source"), dict) else {}
        )
        ghcr_ref = str(source.get("ghcr", "")).strip()
        ghcr_image_repo = ghcr_repo(ghcr_ref) if ghcr_ref else ""
        tag = str(source.get("tag", "unknown"))
        digest = get_digest(entry)

        target = resolve_target(service_map, service, env)
        overlay_rel = (
            str(target.get("overlayPath", "")).strip()
            if isinstance(target, dict)
            else ""
        )
        image_name = (
            str(target.get("kustomizeImageName", "")).strip()
            if isinstance(target, dict)
            else ""
        )
        harbor_image = (
            str(target.get("harborImage", "")).strip()
            if isinstance(target, dict)
            else ""
        )
        deploy_image = (
            str(target.get("deployImage", "")).strip()
            if isinstance(target, dict)
            else ""
        )
        argocd_app = (
            str(target.get("argocdApp", "")).strip() if isinstance(target, dict) else ""
        )

        if not deploy_image and ghcr_image_repo:
            deploy_image = ghcr_image_repo
        if not deploy_image and harbor_image:
            deploy_image = harbor_image
        if not deploy_image:
            deploy_image = f"ghcr.io/unknown/{service}"

        if not service or not env or not digest or not overlay_rel or not image_name:
            attempts = int(entry.get("attempts", 0)) + 1
            entry["attempts"] = attempts
            entry["lastError"] = (
                "invalid entry or missing service mapping in release/services.yaml"
            )
            if attempts >= retry_max:
                entry["status"] = "failed"
                entry["failedAt"] = now_rfc3339()
                queue["pending"] = [
                    e for e in queue["pending"] if entry_id(e) != entry_id(entry)
                ]
                upsert_entry(queue["failed"], entry)
            changed = True
            continue

        should_check_registry = (not skip_registry_check) and bool(harbor_url.strip())
        if should_check_registry and not harbor_manifest_ready(
            deploy_image, digest, harbor_url, harbor_user, harbor_pass
        ):
            continue

        overlay_path = repo_dir / overlay_rel
        if not overlay_path.exists():
            attempts = int(entry.get("attempts", 0)) + 1
            entry["attempts"] = attempts
            entry["lastError"] = f"overlay file not found: {overlay_rel}"
            if attempts >= retry_max:
                entry["status"] = "failed"
                entry["failedAt"] = now_rfc3339()
                queue["pending"] = [
                    e for e in queue["pending"] if entry_id(e) != entry_id(entry)
                ]
                upsert_entry(queue["failed"], entry)
            changed = True
            continue

        promoted_at = now_rfc3339()
        o_path, o_changed, o_data = update_overlay_kustomization(
            overlay_path=overlay_path,
            image_name=image_name,
            harbor_image=deploy_image,
            digest=digest,
        )
        if o_changed:
            overlay_changes[o_path] = o_data
            changed = True

        evidence_id = build_evidence_id(entry, promoted_at)
        evidence_path = repo_dir / "evidence/records" / f"{evidence_id}.yaml"
        existing = yaml_load(evidence_path, default={})
        if not isinstance(existing, dict):
            existing = {}

        record = {
            "evidenceId": evidence_id,
            "service": service,
            "env": env,
            "source": {
                "repo": ghcr_image_repo
                if ghcr_image_repo
                else f"ghcr.io/unknown/{service}",
                "commit": commit_from_tag(tag),
                "workflowRun": str(source.get("workflowRun", ""))
                if source.get("workflowRun")
                else "",
            },
            "image": {
                "ghcr": ghcr_ref,
                # Keep legacy key for schema compatibility; value is the actual deployed image.
                "harbor": f"{deploy_image}@{digest}",
                "deployed": f"{deploy_image}@{digest}",
            },
            "deploy": {
                "deployRepoCommit": "__PENDING_COMMIT__",
                "queueId": entry_id(entry),
                "argocdApp": argocd_app
                or existing.get("deploy", {}).get("argocdApp", f"{service}-{env}")
                if isinstance(existing.get("deploy"), dict)
                else f"{service}-{env}",
                "overlayPath": overlay_rel,
                "syncedAt": promoted_at,
            },
            "tests": {
                "smoke": {
                    "status": "pending",
                    "checkedAt": "",
                }
            },
            "approvals": existing.get("approvals", {})
            if isinstance(existing.get("approvals"), dict)
            else {},
        }

        evidence_changes[evidence_path] = record
        changed = True

        entry["status"] = "promoted"
        entry["promotedAt"] = promoted_at
        entry["lastError"] = ""
        queue["pending"] = [
            e for e in queue["pending"] if entry_id(e) != entry_id(entry)
        ]
        upsert_entry(queue["promoted"], entry)

        promoted_meta.append(
            {
                "service": service,
                "tag": tag,
                "evidence_path": str(evidence_path),
                "overlay_path": overlay_rel,
            }
        )

    return queue, overlay_changes, evidence_changes, promoted_meta, changed


def run(
    cmd: list[str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def repo_workdir(args: argparse.Namespace) -> tuple[Path, Path | None]:
    if args.local_repo_dir:
        return Path(args.local_repo_dir).resolve(), None

    token = args.deploy_repo_token or os.getenv("DEPLOY_REPO_TOKEN", "")
    if not token:
        raise SystemExit("DEPLOY_REPO_TOKEN is required unless --local-repo-dir is set")

    url = args.deploy_repo_url
    if url.startswith("https://"):
        url = url.replace("https://", f"https://x-access-token:{token}@", 1)

    tmp = Path(tempfile.mkdtemp(prefix="promoter-"))
    repo_dir = tmp / "repo"
    run(["git", "clone", "--depth", "1", url, str(repo_dir)])
    return repo_dir, tmp


def validate_queue_shape(queue: dict[str, Any]) -> None:
    for key in ["pending", "promoted", "failed", "superseded"]:
        if key not in queue or not isinstance(queue[key], list):
            raise ValueError(f"queue missing list: {key}")


def commit_and_push(
    repo_dir: Path,
    promoted_meta: list[dict[str, str]],
    dry_run: bool,
) -> None:
    if dry_run:
        print("DRY_RUN=1, skip commit/push")
        return

    run(["python3", "scripts/evidence/validate.py"], cwd=repo_dir)

    run(["git", "config", "user.name", "deploy-promoter[bot]"], cwd=repo_dir)
    run(
        [
            "git",
            "config",
            "user.email",
            "deploy-promoter[bot]@users.noreply.github.com",
        ],
        cwd=repo_dir,
    )

    stage_paths = ["release/queue.yaml", "evidence/records"]
    stage_paths.extend(
        item["overlay_path"] for item in promoted_meta if item.get("overlay_path")
    )
    run(["git", "add", *sorted(set(stage_paths))], cwd=repo_dir)
    diff = run(
        ["git", "diff", "--cached", "--name-only"], cwd=repo_dir, check=False
    ).stdout.strip()
    if not diff:
        print("No changes to commit")
        return

    if promoted_meta:
        svc = promoted_meta[0]["service"]
        tag = promoted_meta[0]["tag"]
        message = f"promote(dev): {svc} {tag} [skip ci]"
    else:
        message = "promote(dev): queue normalize [skip ci]"

    run(["git", "commit", "-m", message], cwd=repo_dir)
    sha = run(["git", "rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()

    touched = []
    for item in promoted_meta:
        path = repo_dir / item["evidence_path"]
        record = yaml_load(path, default={})
        if not isinstance(record, dict):
            continue
        deploy = (
            record.get("deploy", {}) if isinstance(record.get("deploy"), dict) else {}
        )
        if deploy.get("deployRepoCommit") != sha:
            deploy["deployRepoCommit"] = sha
            record["deploy"] = deploy
            yaml_dump(path, record)
            touched.append(path)

    if touched:
        run(["python3", "scripts/evidence/validate.py"], cwd=repo_dir)
        run(
            ["git", "add", *[str(p.relative_to(repo_dir)) for p in touched]],
            cwd=repo_dir,
        )
        run(["git", "commit", "--amend", "--no-edit"], cwd=repo_dir)

    run(["git", "push", "origin", "HEAD:main"], cwd=repo_dir)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote ready release queue entries to Argo-consumed overlays"
    )
    parser.add_argument("--local-repo-dir", default=os.getenv("LOCAL_REPO_DIR", ""))
    parser.add_argument(
        "--deploy-repo-url",
        default=os.getenv(
            "DEPLOY_REPO_URL", "https://github.com/BrunoGaoSZ/ljwx-deploy.git"
        ),
    )
    parser.add_argument(
        "--deploy-repo-token", default=os.getenv("DEPLOY_REPO_TOKEN", "")
    )
    parser.add_argument(
        "--service-map", default=os.getenv("SERVICE_MAP_PATH", "release/services.yaml")
    )
    parser.add_argument(
        "--harbor-url",
        default=os.getenv("HARBOR_URL", ""),
    )
    parser.add_argument("--harbor-user", default=os.getenv("HARBOR_USER", ""))
    parser.add_argument("--harbor-pass", default=os.getenv("HARBOR_PASS", ""))
    parser.add_argument(
        "--retry-max", type=int, default=int(os.getenv("RETRY_MAX", "10"))
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="simulate without writing/committing"
    )
    parser.add_argument(
        "--skip-registry-check",
        action="store_true",
        help="skip registry manifest check (transparent-cache mode)",
    )
    args = parser.parse_args()

    dry_run = bool(args.dry_run) or os.getenv("DRY_RUN", "0") in {
        "1",
        "true",
        "True",
        "yes",
        "YES",
    }

    repo_dir, tmp_root = repo_workdir(args)
    try:
        queue_path = repo_dir / "release/queue.yaml"
        queue = yaml_load(queue_path, default={})
        if not isinstance(queue, dict):
            raise ValueError("release/queue.yaml root must be mapping")
        queue = ensure_queue_shape(queue)
        validate_queue_shape(queue)

        service_map = load_service_map(repo_dir / args.service_map)

        queue, overlay_changes, evidence_changes, promoted_meta, changed = (
            process_pending(
                queue=queue,
                repo_dir=repo_dir,
                service_map=service_map,
                retry_max=args.retry_max,
                harbor_url=args.harbor_url,
                harbor_user=args.harbor_user,
                harbor_pass=args.harbor_pass,
                skip_registry_check=args.skip_registry_check,
            )
        )

        if not changed:
            print("No changes made (nothing ready or no normalization needed)")
            return 0

        if dry_run:
            print("DRY_RUN summary:")
            print(f"- overlay changes: {len(overlay_changes)}")
            print(f"- evidence changes: {len(evidence_changes)}")
            print(f"- promoted entries: {len(promoted_meta)}")
            print(
                f"- pending: {len(queue['pending'])}, promoted: {len(queue['promoted'])}, "
                f"failed: {len(queue['failed'])}, superseded: {len(queue['superseded'])}"
            )
            return 0

        yaml_dump(queue_path, queue)
        for path, data in overlay_changes.items():
            yaml_dump(path, data)
        for path, data in evidence_changes.items():
            yaml_dump(path, data)

        commit_and_push(repo_dir, promoted_meta, dry_run=False)
        print("Promotion completed")
        return 0
    finally:
        if tmp_root is not None and tmp_root.exists():
            shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Batch onboarding tool for release/smoke/argocd integration."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "缺少 PyYAML，请使用 `uvx --with pyyaml python scripts/factory/onboard_services.py` 运行。"
    ) from exc


SERVICE_MAP_FILES: dict[str, Path] = {
    "default": Path("release/services.yaml"),
    "local-k3s": Path("release/services.local-k3s.yaml"),
    "orbstack-k3s-cn": Path("release/services.orbstack-k3s-cn.yaml"),
}

SMOKE_TARGET_FILES: dict[str, Path] = {
    "local-k3s": Path("scripts/smoke/targets.local-k3s.json"),
    "orbstack-k3s-cn": Path("scripts/smoke/targets.orbstack-k3s-cn.json"),
}


@dataclass(frozen=True)
class OnboardEntry:
    service: str
    environment: str
    overlay_path: str
    kustomize_image_name: str
    harbor_image: str
    argocd_app: str
    smoke_endpoint: str
    deploy_namespace: str
    profiles: tuple[str, ...]
    scaffold_app: bool
    generate_argocd_app: bool
    argocd_app_file: str


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_yaml_mapping(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = yaml.safe_load(read_text_file(path))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML 顶层必须是对象: {path}")
    return data


def dump_yaml(path: Path, payload: dict[str, object]) -> None:
    write_text_file(path, yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))


def load_json_object(path: Path) -> dict[str, object]:
    data = json.loads(read_text_file(path))
    if not isinstance(data, dict):
        raise ValueError(f"JSON 顶层必须是对象: {path}")
    return data


def dump_json(path: Path, payload: dict[str, object]) -> None:
    write_text_file(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def normalize_profiles(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        if value == "all":
            return ("local-k3s", "orbstack-k3s-cn")
        return (value,)
    if not isinstance(value, list):
        return ("local-k3s", "orbstack-k3s-cn")

    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
    if not out:
        return ("local-k3s", "orbstack-k3s-cn")
    return tuple(dict.fromkeys(out))


def normalize_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def get_required_str(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"字段 `{key}` 必填且必须为字符串")
    return value.strip()


def parse_entry(raw: dict[str, object]) -> OnboardEntry:
    service = get_required_str(raw, "service")
    environment = get_required_str(raw, "environment")
    overlay_path = get_required_str(raw, "overlay_path")
    kustomize_image_name = get_required_str(raw, "kustomize_image_name")
    harbor_image = get_required_str(raw, "harbor_image")
    argocd_app = get_required_str(raw, "argocd_app")
    smoke_endpoint = get_required_str(raw, "smoke_endpoint")
    deploy_namespace = get_required_str(raw, "deploy_namespace")

    profiles = normalize_profiles(raw.get("profiles", "all"))
    scaffold_app = normalize_bool(raw.get("scaffold_app"), False)
    generate_argocd_app = normalize_bool(raw.get("generate_argocd_app"), False)
    argocd_app_file = str(raw.get("argocd_app_file", "")).strip()
    if generate_argocd_app and not argocd_app_file:
        raise ValueError("启用 generate_argocd_app 时必须提供 argocd_app_file")

    return OnboardEntry(
        service=service,
        environment=environment,
        overlay_path=overlay_path,
        kustomize_image_name=kustomize_image_name,
        harbor_image=harbor_image,
        argocd_app=argocd_app,
        smoke_endpoint=smoke_endpoint,
        deploy_namespace=deploy_namespace,
        profiles=profiles,
        scaffold_app=scaffold_app,
        generate_argocd_app=generate_argocd_app,
        argocd_app_file=argocd_app_file,
    )


def load_catalog(path: Path) -> list[OnboardEntry]:
    root = load_yaml_mapping(path)
    services_obj = root.get("services")
    if not isinstance(services_obj, list):
        raise ValueError("catalog 需要包含 services 列表")

    entries: list[OnboardEntry] = []
    for item in services_obj:
        if not isinstance(item, dict):
            raise ValueError("services 列表项必须是对象")
        entries.append(parse_entry(item))
    return entries


def ensure_service_mapping(path: Path, entry: OnboardEntry, dry_run: bool) -> bool:
    payload = load_yaml_mapping(path)
    services_obj = payload.get("services")
    services = services_obj if isinstance(services_obj, dict) else {}
    payload["services"] = services

    svc_obj = services.get(entry.service)
    svc_map = svc_obj if isinstance(svc_obj, dict) else {}
    services[entry.service] = svc_map

    envs_obj = svc_map.get("envs")
    envs = envs_obj if isinstance(envs_obj, dict) else {}
    svc_map["envs"] = envs

    current = envs.get(entry.environment)
    current_map = current if isinstance(current, dict) else {}
    desired: dict[str, object] = {
        "overlayPath": entry.overlay_path,
        "kustomizeImageName": entry.kustomize_image_name,
        "harborImage": entry.harbor_image,
        "argocdApp": entry.argocd_app,
    }
    changed = current_map != desired
    if changed:
        envs[entry.environment] = desired
        if not dry_run:
            dump_yaml(path, payload)
    return changed


def ensure_smoke_target(path: Path, entry: OnboardEntry, dry_run: bool) -> bool:
    payload = load_json_object(path)
    targets_obj = payload.get("targets")
    targets = targets_obj if isinstance(targets_obj, list) else []
    payload["targets"] = targets

    desired = {
        "service": entry.service,
        "environment": entry.environment,
        "argocd_app": entry.argocd_app,
        "endpoint": entry.smoke_endpoint,
    }
    changed = False
    found = False
    for idx, target in enumerate(targets):
        if not isinstance(target, dict):
            continue
        service = str(target.get("service", ""))
        environment = str(target.get("environment", ""))
        if service == entry.service and environment == entry.environment:
            found = True
            if target != desired:
                targets[idx] = desired
                changed = True
            break
    if not found:
        targets.append(desired)
        changed = True

    if changed and not dry_run:
        dump_json(path, payload)
    return changed


def ensure_argocd_app_file(repo_root: Path, entry: OnboardEntry, dry_run: bool) -> bool:
    if not entry.generate_argocd_app:
        return False

    source_path = str(Path(entry.overlay_path).parent).replace("\\", "/")
    content = "\n".join(
        [
            "apiVersion: argoproj.io/v1alpha1",
            "kind: Application",
            "metadata:",
            f"  name: {entry.argocd_app}",
            "  namespace: argocd",
            "spec:",
            "  project: default",
            "  source:",
            "    repoURL: https://github.com/BrunoGaoSZ/ljwx-deploy.git",
            "    targetRevision: main",
            f"    path: {source_path}",
            "  destination:",
            "    server: https://kubernetes.default.svc",
            f"    namespace: {entry.deploy_namespace}",
            "  syncPolicy:",
            "    automated:",
            "      prune: true",
            "      selfHeal: true",
            "    syncOptions:",
            "      - CreateNamespace=true",
            "",
        ]
    )
    app_path = repo_root / entry.argocd_app_file
    current = app_path.read_text(encoding="utf-8") if app_path.exists() else ""
    if current == content:
        return False
    if not dry_run:
        write_text_file(app_path, content)
    return True


def scaffold_app_manifest(repo_root: Path, entry: OnboardEntry, dry_run: bool) -> int:
    if not entry.scaffold_app:
        return 0

    overlay_path = repo_root / entry.overlay_path
    overlay_dir = overlay_path.parent
    base_dir = overlay_dir.parent.parent / "base"
    if not str(overlay_dir).endswith("/overlays/" + entry.environment):
        raise ValueError(
            f"overlay_path 必须形如 apps/<svc>/overlays/<env>/kustomization.yaml: {entry.overlay_path}"
        )

    deployment_path = base_dir / "deployment.yaml"
    service_path = base_dir / "service.yaml"
    base_kustomization_path = base_dir / "kustomization.yaml"

    deployment_content = "\n".join(
        [
            "apiVersion: apps/v1",
            "kind: Deployment",
            "metadata:",
            f"  name: {entry.service}",
            "  labels:",
            f"    app: {entry.service}",
            "spec:",
            "  replicas: 1",
            "  selector:",
            "    matchLabels:",
            f"      app: {entry.service}",
            "  template:",
            "    metadata:",
            "      labels:",
            f"        app: {entry.service}",
            "    spec:",
            "      containers:",
            f"        - name: {entry.service}",
            f"          image: {entry.harbor_image}:latest",
            "          ports:",
            "            - name: http",
            "              containerPort: 80",
            "              protocol: TCP",
            "          livenessProbe:",
            "            httpGet:",
            "              path: /",
            "              port: http",
            "            initialDelaySeconds: 10",
            "            periodSeconds: 10",
            "          readinessProbe:",
            "            httpGet:",
            "              path: /",
            "              port: http",
            "            initialDelaySeconds: 5",
            "            periodSeconds: 5",
            "",
        ]
    )

    service_content = "\n".join(
        [
            "apiVersion: v1",
            "kind: Service",
            "metadata:",
            f"  name: {entry.service}",
            "  labels:",
            f"    app: {entry.service}",
            "spec:",
            "  type: ClusterIP",
            "  selector:",
            f"    app: {entry.service}",
            "  ports:",
            "    - name: http",
            "      port: 80",
            "      targetPort: http",
            "      protocol: TCP",
            "",
        ]
    )

    base_kustomization_content = "\n".join(
        [
            "apiVersion: kustomize.config.k8s.io/v1beta1",
            "kind: Kustomization",
            "resources:",
            "  - deployment.yaml",
            "  - service.yaml",
            "",
        ]
    )

    overlay_content = "\n".join(
        [
            "apiVersion: kustomize.config.k8s.io/v1beta1",
            "kind: Kustomization",
            f"namespace: {entry.deploy_namespace}",
            "resources:",
            "  - ../../base",
            "images:",
            f"  - name: {entry.kustomize_image_name}",
            f"    newName: {entry.harbor_image}",
            '    newTag: "latest"',
            "",
        ]
    )

    changes = 0
    files_to_write = {
        deployment_path: deployment_content,
        service_path: service_content,
        base_kustomization_path: base_kustomization_content,
        overlay_path: overlay_content,
    }
    for file_path, content in files_to_write.items():
        current = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        if current != content:
            changes += 1
            if not dry_run:
                write_text_file(file_path, content)
    return changes


def apply_onboarding(
    repo_root: Path, entries: list[OnboardEntry], dry_run: bool
) -> None:
    changed_files = 0
    for entry in entries:
        print(f"[onboard] 处理服务: {entry.service}/{entry.environment}")

        for map_key in ("default", *entry.profiles):
            path = repo_root / SERVICE_MAP_FILES[map_key]
            if ensure_service_mapping(path, entry, dry_run):
                changed_files += 1
                print(f"  - 已更新映射: {path}")

        for profile in entry.profiles:
            smoke_path = repo_root / SMOKE_TARGET_FILES[profile]
            if ensure_smoke_target(smoke_path, entry, dry_run):
                changed_files += 1
                print(f"  - 已更新 smoke 目标: {smoke_path}")

        scaffold_changes = scaffold_app_manifest(repo_root, entry, dry_run)
        if scaffold_changes > 0:
            changed_files += scaffold_changes
            print(f"  - 已生成清单文件: {scaffold_changes} 个")

        if ensure_argocd_app_file(repo_root, entry, dry_run):
            changed_files += 1
            print(f"  - 已生成 Argo Application: {entry.argocd_app_file}")

    if dry_run:
        print(f"[onboard] dry-run 完成，预计变更文件数: {changed_files}")
    else:
        print(f"[onboard] 执行完成，变更文件数: {changed_files}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量接入服务到 queue/promoter/smoke/evidence 闭环"
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("factory/onboarding/services.catalog.yaml"),
        help="服务接入清单 YAML",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不落盘")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    catalog_path = (repo_root / args.catalog).resolve()
    if not catalog_path.exists():
        print(f"未找到 catalog 文件: {catalog_path}")
        return 1

    entries = load_catalog(catalog_path)
    apply_onboarding(repo_root=repo_root, entries=entries, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

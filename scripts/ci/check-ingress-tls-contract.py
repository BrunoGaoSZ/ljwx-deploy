#!/usr/bin/env python3
"""Validate ingress TLS and ClusterIssuer references managed in Git."""

from __future__ import annotations

from pathlib import Path

import yaml


def iter_yaml_documents(root: Path) -> list[tuple[Path, dict[str, object]]]:
    docs: list[tuple[Path, dict[str, object]]] = []
    for path in root.rglob("*.yaml"):
        try:
            loaded = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError as exc:
            raise SystemExit(f"YAML 解析失败: {path}: {exc}") from exc
        for item in loaded:
            if isinstance(item, dict):
                docs.append((path, item))
    return docs


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    issuer_docs = iter_yaml_documents(repo_root / "apps" / "cert-manager-config")
    issuers = {
        str(doc.get("metadata", {}).get("name", "")).strip()
        for _, doc in issuer_docs
        if str(doc.get("kind", "")).strip() == "ClusterIssuer"
    }

    if not issuers:
        raise SystemExit("未找到任何 Git 管理的 ClusterIssuer")

    errors: list[str] = []
    for path, doc in iter_yaml_documents(repo_root / "apps"):
        if str(doc.get("kind", "")).strip() != "Ingress":
            continue
        metadata = doc.get("metadata", {})
        annotations_obj = metadata.get("annotations", {})
        annotations = annotations_obj if isinstance(annotations_obj, dict) else {}
        issuer_name = str(annotations.get("cert-manager.io/cluster-issuer", "")).strip()
        if not issuer_name:
            continue
        if issuer_name not in issuers:
            errors.append(f"{path}: 引用了不存在的 ClusterIssuer `{issuer_name}`")
        spec = doc.get("spec", {})
        tls_obj = spec.get("tls", [])
        tls_items = tls_obj if isinstance(tls_obj, list) else []
        if not tls_items:
            errors.append(f"{path}: 配置了 cert-manager issuer 但缺少 spec.tls")
            continue
        for tls_item in tls_items:
            if not isinstance(tls_item, dict):
                errors.append(f"{path}: spec.tls 列表项必须是对象")
                continue
            secret_name = str(tls_item.get("secretName", "")).strip()
            hosts_obj = tls_item.get("hosts", [])
            hosts = hosts_obj if isinstance(hosts_obj, list) else []
            if not secret_name:
                errors.append(f"{path}: spec.tls 缺少 secretName")
            if not hosts:
                errors.append(f"{path}: spec.tls 缺少 hosts")

    if errors:
        raise SystemExit("Ingress/TLS contract 校验失败:\n- " + "\n- ".join(errors))

    print(f"Ingress/TLS contract gate passed ({len(issuers)} ClusterIssuer).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

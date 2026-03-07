#!/usr/bin/env python3
"""Batch onboarding tool for release/smoke/argocd/capability integration."""

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

DEFAULT_NAMESPACE_PROFILES_PATH = Path("factory/onboarding/namespace-profiles.yaml")
DEFAULT_CAPABILITY_PROFILES_PATH = Path("factory/onboarding/capability-profiles.yaml")
DEFAULT_SERVICE_TEMPLATES_PATH = Path("factory/onboarding/service-templates.yaml")
DEFAULT_INGRESS_PROFILES_PATH = Path("factory/onboarding/ingress-profiles.yaml")
DEFAULT_CLUSTER_KUSTOMIZATION_PATH = Path("cluster/kustomization.yaml")
DEFAULT_PROD_CLUSTER_KUSTOMIZATION_PATH = Path("cluster-prod/kustomization.yaml")
DEFAULT_DEPLOY_REPO_URL = "https://github.com/BrunoGaoSZ/ljwx-deploy.git"
DEFAULT_DEPLOY_REF = "main"
ANNOTATION_PREFIX = "gitops.ljwx.io"


@dataclass(frozen=True)
class OnboardEntry:
    service: str
    environment: str
    overlay_path: str
    kustomize_image_name: str
    harbor_image: str
    deploy_image: str
    argocd_app: str
    smoke_endpoint: str
    deploy_namespace: str
    profiles: tuple[str, ...]
    scaffold_app: bool
    generate_argocd_app: bool
    argocd_app_file: str
    cluster_bootstrap: bool
    ingress_profile: str
    public_host: str
    generate_ingress: bool
    public_path: str
    public_path_type: str
    public_service_name: str
    public_service_port: int
    ingress_class_name: str
    tls_enabled: bool
    cluster_issuer: str
    tls_secret_name: str
    ingress_annotations: tuple[tuple[str, str], ...]
    namespace_profile: str
    registry_profile: str
    runtime_secret_profile: str
    capabilities: tuple[str, ...]
    components: tuple["ServiceComponent", ...]


@dataclass(frozen=True)
class ServiceTemplate:
    description: str
    overlay_name_template: str
    smoke_host_template: str
    smoke_path: str
    smoke_port: str
    ghcr_org: str
    harbor_registry: str
    harbor_project: str
    profiles: tuple[str, ...]
    namespace_profile: str
    registry_profile: str
    runtime_secret_profile: str
    capabilities: tuple[str, ...]
    scaffold_app: bool
    generate_argocd_app: bool
    cluster_bootstrap: bool
    ingress_profile: str
    public_host_template: str
    argocd_order: int


@dataclass(frozen=True)
class ServiceComponent:
    service_name: str
    kustomize_image_name: str
    harbor_image: str
    deploy_image: str
    smoke_endpoint: str


@dataclass(frozen=True)
class NamespaceProfile:
    description: str
    resource_quota: dict[str, str]
    limit_max: dict[str, str]
    limit_min: dict[str, str]
    limit_default: dict[str, str]
    limit_default_request: dict[str, str]


@dataclass(frozen=True)
class RegistryProfile:
    description: str
    image_pull_secrets: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeSecretProfile:
    description: str
    contract_secret_names: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityDefinition:
    scope: str
    description: str


@dataclass(frozen=True)
class IngressProfile:
    description: str
    ingress_class_name: str
    annotations: tuple[tuple[str, str], ...]
    tls_enabled: bool
    cluster_issuer: str
    path: str
    path_type: str
    service_port: int


@dataclass(frozen=True)
class PlatformProfiles:
    namespace_profiles: dict[str, NamespaceProfile]
    registry_profiles: dict[str, RegistryProfile]
    runtime_secret_profiles: dict[str, RuntimeSecretProfile]
    capabilities: dict[str, CapabilityDefinition]


@dataclass(frozen=True)
class ResolvedEntry:
    entry: OnboardEntry
    namespace_profile: NamespaceProfile
    registry_profile: RegistryProfile
    runtime_secret_profile: RuntimeSecretProfile
    capabilities: tuple[str, ...]


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def resolve_repo_path(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return repo_root / path


def load_yaml_mapping(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = yaml.safe_load(read_text_file(path))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML 顶层必须是对象: {path}")
    return data


def dump_yaml_text(payload: dict[str, object]) -> str:
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def dump_yaml_documents_text(payloads: list[dict[str, object]]) -> str:
    return yaml.safe_dump_all(payloads, sort_keys=False, allow_unicode=True)


def dump_yaml(path: Path, payload: dict[str, object]) -> None:
    write_text_file(path, dump_yaml_text(payload))


def load_json_object(path: Path) -> dict[str, object]:
    data = json.loads(read_text_file(path))
    if not isinstance(data, dict):
        raise ValueError(f"JSON 顶层必须是对象: {path}")
    return data


def dump_json(path: Path, payload: dict[str, object]) -> None:
    write_text_file(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def expect_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是对象")
    return value


def parse_string_mapping(value: object, label: str) -> dict[str, str]:
    mapping = expect_mapping(value, label)
    out: dict[str, str] = {}
    for raw_key, raw_value in mapping.items():
        if not isinstance(raw_key, str) or not str(raw_value).strip():
            raise ValueError(f"{label} 必须是字符串键值对")
        out[raw_key] = str(raw_value).strip()
    return out


def normalize_profiles(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        if value == "all":
            return ("local-k3s", "orbstack-k3s-cn")
        return (value,)
    if not isinstance(value, list):
        return ("local-k3s", "orbstack-k3s-cn")

    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    if not out:
        return ("local-k3s", "orbstack-k3s-cn")
    return tuple(dict.fromkeys(out))


def normalize_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def normalize_string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",") if item.strip()]
        return tuple(parts)
    if not isinstance(value, list):
        return ()

    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return tuple(dict.fromkeys(out))


def get_required_str(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"字段 `{key}` 必填且必须为字符串")
    return value.strip()


def get_optional_str(raw: dict[str, object], key: str, default: str) -> str:
    value = raw.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"字段 `{key}` 必须为字符串")
    stripped = value.strip()
    if stripped:
        return stripped
    return default


def get_optional_int(raw: dict[str, object], key: str, default: int) -> int:
    value = raw.get(key)
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError(f"字段 `{key}` 必须为整数")


def render_string_template(template: str, context: dict[str, str], label: str) -> str:
    try:
        rendered = template.format_map(context)
    except KeyError as exc:
        missing_key = str(exc.args[0])
        raise ValueError(f"{label} 缺少变量 `{missing_key}`") from exc
    stripped = rendered.strip()
    if not stripped:
        raise ValueError(f"{label} 渲染结果不能为空")
    return stripped


def default_namespace_profile(environment: str) -> str:
    if environment in {"prod", "production"}:
        return "prod-default"
    return "dev-default"


def default_argocd_app_file(service: str, environment: str, order: int) -> str:
    return f"argocd-apps/{order:02d}-{service}-{environment}.yaml"


def default_tls_secret_name(host: str) -> str:
    out = []
    for char in host.strip().lower():
        if char.isalnum():
            out.append(char)
        else:
            out.append("-")
    collapsed = "".join(out).strip("-")
    while "--" in collapsed:
        collapsed = collapsed.replace("--", "-")
    return f"{collapsed}-tls"


def build_default_smoke_endpoint(
    smoke_host: str,
    deploy_namespace: str,
    smoke_port: str,
    smoke_path: str,
) -> str:
    port_segment = f":{smoke_port}" if smoke_port else ""
    return f"http://{smoke_host}.{deploy_namespace}.svc.cluster.local{port_segment}{smoke_path}"


def build_component(
    raw: dict[str, object],
    *,
    deploy_namespace: str,
    default_service_name: str,
    default_image_repo: str,
    default_ghcr_org: str,
    default_harbor_registry: str,
    default_harbor_project: str,
    default_deploy_image: str,
    default_smoke_path: str,
    default_smoke_port: str,
    default_smoke_endpoint: str,
) -> ServiceComponent:
    service_name = get_optional_str(raw, "service", default_service_name)
    image_repo = get_optional_str(raw, "image_repo", default_image_repo)
    ghcr_org = get_optional_str(raw, "ghcr_org", default_ghcr_org)
    harbor_registry = get_optional_str(raw, "harbor_registry", default_harbor_registry)
    harbor_project = get_optional_str(raw, "harbor_project", default_harbor_project)
    kustomize_image_name = get_optional_str(
        raw,
        "kustomize_image_name",
        f"ghcr.io/{ghcr_org}/{image_repo}",
    )
    harbor_image = get_optional_str(
        raw,
        "harbor_image",
        f"{harbor_registry}/{harbor_project}/{image_repo}",
    )
    deploy_image = get_optional_str(raw, "deploy_image", default_deploy_image)

    smoke_endpoint = get_optional_str(raw, "smoke_endpoint", "")
    smoke_host = get_optional_str(raw, "smoke_host", "")
    has_smoke_config = bool(
        smoke_endpoint or smoke_host or "smoke_path" in raw or "smoke_port" in raw
    )
    if not smoke_endpoint and has_smoke_config:
        smoke_path = get_optional_str(raw, "smoke_path", default_smoke_path)
        smoke_port = get_optional_str(raw, "smoke_port", default_smoke_port)
        if not smoke_host:
            smoke_host = service_name
        smoke_endpoint = build_default_smoke_endpoint(
            smoke_host=smoke_host,
            deploy_namespace=deploy_namespace,
            smoke_port=smoke_port,
            smoke_path=smoke_path,
        )
    if not smoke_endpoint and not has_smoke_config:
        smoke_endpoint = default_smoke_endpoint

    return ServiceComponent(
        service_name=service_name,
        kustomize_image_name=kustomize_image_name,
        harbor_image=harbor_image,
        deploy_image=deploy_image,
        smoke_endpoint=smoke_endpoint,
    )


def parse_entry(
    raw: dict[str, object],
    service_templates: dict[str, ServiceTemplate],
    ingress_profiles: dict[str, IngressProfile],
) -> OnboardEntry:
    service = get_required_str(raw, "service")
    environment = get_required_str(raw, "environment")
    template_name = get_optional_str(raw, "template", "service-default")
    try:
        service_template = service_templates[template_name]
    except KeyError as exc:
        raise ValueError(f"未定义 service template `{template_name}`") from exc

    image_repo = get_optional_str(raw, "image_repo", service)
    ghcr_org = get_optional_str(raw, "ghcr_org", service_template.ghcr_org)
    harbor_registry = get_optional_str(
        raw,
        "harbor_registry",
        service_template.harbor_registry,
    )
    harbor_project = get_optional_str(
        raw, "harbor_project", service_template.harbor_project
    )

    render_context = {
        "service": service,
        "environment": environment,
        "image_repo": image_repo,
        "ghcr_org": ghcr_org,
        "harbor_registry": harbor_registry,
        "harbor_project": harbor_project,
    }

    overlay_name = get_optional_str(raw, "overlay_name", "")
    if not overlay_name:
        overlay_name = render_string_template(
            service_template.overlay_name_template,
            render_context,
            f"service template `{template_name}`.overlay_name_template",
        )

    deploy_namespace = get_optional_str(
        raw, "deploy_namespace", f"{service}-{environment}"
    )
    argocd_app = get_optional_str(raw, "argocd_app", f"{service}-{environment}")
    argocd_order = get_optional_int(raw, "argocd_order", service_template.argocd_order)
    overlay_path = get_optional_str(
        raw,
        "overlay_path",
        f"apps/{service}/overlays/{overlay_name}/kustomization.yaml",
    )
    has_explicit_kustomize_image_name = "kustomize_image_name" in raw
    kustomize_image_name = get_optional_str(
        raw,
        "kustomize_image_name",
        f"ghcr.io/{ghcr_org}/{image_repo}",
    )
    has_explicit_harbor_image = "harbor_image" in raw
    harbor_image = get_optional_str(
        raw,
        "harbor_image",
        f"{harbor_registry}/{harbor_project}/{image_repo}",
    )
    has_explicit_deploy_image = "deploy_image" in raw
    deploy_image = get_optional_str(raw, "deploy_image", "")
    has_explicit_smoke_config = any(
        key in raw
        for key in ("smoke_endpoint", "smoke_host", "smoke_path", "smoke_port")
    )
    smoke_endpoint = get_optional_str(raw, "smoke_endpoint", "")
    if not smoke_endpoint:
        smoke_host = get_optional_str(raw, "smoke_host", "")
        if not smoke_host:
            smoke_host = render_string_template(
                service_template.smoke_host_template,
                {
                    "service": service,
                    "environment": environment,
                    "deploy_namespace": deploy_namespace,
                },
                f"service template `{template_name}`.smoke_host_template",
            )
        smoke_path = get_optional_str(raw, "smoke_path", service_template.smoke_path)
        smoke_port = get_optional_str(raw, "smoke_port", service_template.smoke_port)
        smoke_endpoint = build_default_smoke_endpoint(
            smoke_host=smoke_host,
            deploy_namespace=deploy_namespace,
            smoke_port=smoke_port,
            smoke_path=smoke_path,
        )

    profiles = normalize_profiles(raw.get("profiles", list(service_template.profiles)))
    scaffold_app = normalize_bool(
        raw.get("scaffold_app"), service_template.scaffold_app
    )
    generate_argocd_app = normalize_bool(
        raw.get("generate_argocd_app"),
        service_template.generate_argocd_app,
    )
    entry_cluster_bootstrap = normalize_bool(
        raw.get("cluster_bootstrap"),
        service_template.cluster_bootstrap,
    )
    argocd_app_file = get_optional_str(raw, "argocd_app_file", "")
    if not argocd_app_file and generate_argocd_app:
        argocd_app_file = default_argocd_app_file(service, environment, argocd_order)
    if generate_argocd_app and not argocd_app_file:
        raise ValueError("启用 generate_argocd_app 时必须提供 argocd_app_file")

    ingress_profile_name = get_optional_str(
        raw,
        "ingress_profile",
        service_template.ingress_profile,
    )
    public_host = get_optional_str(raw, "public_host", "")
    if not public_host and service_template.public_host_template:
        public_host = render_string_template(
            service_template.public_host_template,
            {
                "service": service,
                "environment": environment,
                "deploy_namespace": deploy_namespace,
            },
            f"service template `{template_name}`.public_host_template",
        )
    if public_host and ingress_profile_name in {"", "none"}:
        ingress_profile_name = "traefik-letsencrypt-public"
    if not ingress_profile_name:
        ingress_profile_name = "none"
    try:
        ingress_profile = ingress_profiles[ingress_profile_name]
    except KeyError as exc:
        raise ValueError(f"未定义 ingress_profile `{ingress_profile_name}`") from exc
    if ingress_profile_name != "none" and not public_host:
        raise ValueError(
            f"{service}/{environment} 启用了 ingress_profile=`{ingress_profile_name}` 但缺少 public_host"
        )
    public_path = get_optional_str(raw, "public_path", ingress_profile.path)
    public_path_type = get_optional_str(
        raw, "public_path_type", ingress_profile.path_type
    )
    public_service_name = get_optional_str(raw, "public_service_name", service)
    public_service_port = get_optional_int(
        raw, "public_service_port", ingress_profile.service_port
    )
    ingress_class_name = get_optional_str(
        raw,
        "ingress_class_name",
        ingress_profile.ingress_class_name,
    )
    tls_enabled = normalize_bool(raw.get("tls_enabled"), ingress_profile.tls_enabled)
    cluster_issuer = get_optional_str(
        raw, "cluster_issuer", ingress_profile.cluster_issuer
    )
    tls_secret_name = get_optional_str(raw, "tls_secret_name", "")
    if public_host and tls_enabled and not tls_secret_name:
        tls_secret_name = default_tls_secret_name(public_host)
    ingress_annotations = dict(ingress_profile.annotations)
    raw_ingress_annotations = raw.get("ingress_annotations")
    if raw_ingress_annotations is not None:
        ingress_annotations.update(
            parse_string_mapping(
                raw_ingress_annotations,
                f"{service}/{environment}.ingress_annotations",
            )
        )
    if cluster_issuer:
        ingress_annotations.setdefault("cert-manager.io/cluster-issuer", cluster_issuer)
    if public_host and not ingress_class_name:
        raise ValueError(
            f"{service}/{environment} 配置 public_host 时必须提供 ingressClass"
        )
    generate_ingress = normalize_bool(raw.get("generate_ingress"), True)

    namespace_profile_default = (
        service_template.namespace_profile or default_namespace_profile(environment)
    )
    namespace_profile = get_optional_str(
        raw,
        "namespace_profile",
        namespace_profile_default,
    )
    registry_profile = get_optional_str(
        raw,
        "registry_profile",
        service_template.registry_profile,
    )
    runtime_secret_profile = get_optional_str(
        raw,
        "runtime_secret_profile",
        service_template.runtime_secret_profile,
    )
    template_capabilities = normalize_string_tuple(list(service_template.capabilities))
    explicit_capabilities = normalize_string_tuple(raw.get("capabilities", []))
    if explicit_capabilities:
        capabilities = tuple(
            dict.fromkeys((*template_capabilities, *explicit_capabilities))
        )
    else:
        capabilities = template_capabilities

    components_obj = raw.get("components")
    components: tuple[ServiceComponent, ...]
    if components_obj is not None:
        if not isinstance(components_obj, list):
            raise ValueError("字段 `components` 必须是列表")
        if not components_obj:
            raise ValueError("字段 `components` 不能为空列表")
        parsed_components: list[ServiceComponent] = []
        seen_component_services: set[str] = set()
        for item in components_obj:
            if not isinstance(item, dict):
                raise ValueError("字段 `components` 列表项必须是对象")
            component = build_component(
                item,
                deploy_namespace=deploy_namespace,
                default_service_name=service,
                default_image_repo=image_repo,
                default_ghcr_org=ghcr_org,
                default_harbor_registry=harbor_registry,
                default_harbor_project=harbor_project,
                default_deploy_image=deploy_image,
                default_smoke_path=service_template.smoke_path,
                default_smoke_port=service_template.smoke_port,
                default_smoke_endpoint="",
            )
            if component.service_name in seen_component_services:
                raise ValueError(
                    f"`components` 中存在重复 service `{component.service_name}` for {service}/{environment}"
                )
            seen_component_services.add(component.service_name)
            parsed_components.append(component)
        components = tuple(parsed_components)
        if not has_explicit_kustomize_image_name and components:
            kustomize_image_name = components[0].kustomize_image_name
        if not has_explicit_harbor_image and components:
            harbor_image = components[0].harbor_image
        if not has_explicit_deploy_image and components:
            deploy_image = components[0].deploy_image
        if not has_explicit_smoke_config and components:
            smoke_endpoint = components[0].smoke_endpoint
    else:
        single_component_raw: dict[str, object] = {
            "service": service,
            "kustomize_image_name": kustomize_image_name,
            "harbor_image": harbor_image,
            "deploy_image": deploy_image,
            "smoke_endpoint": smoke_endpoint,
        }
        components = (
            build_component(
                single_component_raw,
                deploy_namespace=deploy_namespace,
                default_service_name=service,
                default_image_repo=image_repo,
                default_ghcr_org=ghcr_org,
                default_harbor_registry=harbor_registry,
                default_harbor_project=harbor_project,
                default_deploy_image=deploy_image,
                default_smoke_path=service_template.smoke_path,
                default_smoke_port=service_template.smoke_port,
                default_smoke_endpoint=smoke_endpoint,
            ),
        )
    if scaffold_app and len(components) > 1:
        raise ValueError(
            f"{service}/{environment} 使用多组件模式时不支持 scaffold_app=true，请改为复用现有 overlay"
        )

    return OnboardEntry(
        service=service,
        environment=environment,
        overlay_path=overlay_path,
        kustomize_image_name=kustomize_image_name,
        harbor_image=harbor_image,
        deploy_image=deploy_image,
        argocd_app=argocd_app,
        smoke_endpoint=smoke_endpoint,
        deploy_namespace=deploy_namespace,
        profiles=profiles,
        scaffold_app=scaffold_app,
        generate_argocd_app=generate_argocd_app,
        argocd_app_file=argocd_app_file,
        cluster_bootstrap=entry_cluster_bootstrap,
        ingress_profile=ingress_profile_name,
        public_host=public_host,
        generate_ingress=generate_ingress,
        public_path=public_path,
        public_path_type=public_path_type,
        public_service_name=public_service_name,
        public_service_port=public_service_port,
        ingress_class_name=ingress_class_name,
        tls_enabled=tls_enabled,
        cluster_issuer=cluster_issuer,
        tls_secret_name=tls_secret_name,
        ingress_annotations=tuple(ingress_annotations.items()),
        namespace_profile=namespace_profile,
        registry_profile=registry_profile,
        runtime_secret_profile=runtime_secret_profile,
        capabilities=capabilities,
        components=components,
    )


def load_catalog(
    path: Path,
    service_templates: dict[str, ServiceTemplate],
    ingress_profiles: dict[str, IngressProfile],
) -> list[OnboardEntry]:
    root = load_yaml_mapping(path)
    services_obj = root.get("services")
    if not isinstance(services_obj, list):
        raise ValueError("catalog 需要包含 services 列表")

    entries: list[OnboardEntry] = []
    for item in services_obj:
        if not isinstance(item, dict):
            raise ValueError("services 列表项必须是对象")
        entries.append(parse_entry(item, service_templates, ingress_profiles))
    return entries


def load_service_templates(repo_root: Path, path: Path) -> dict[str, ServiceTemplate]:
    resolved_path = resolve_repo_path(repo_root, path)
    root = load_yaml_mapping(resolved_path)
    templates_obj = expect_mapping(root.get("templates"), "service templates")
    templates: dict[str, ServiceTemplate] = {}
    for raw_name, raw_template in templates_obj.items():
        if not isinstance(raw_name, str):
            raise ValueError("service template 名称必须是字符串")
        template_map = expect_mapping(raw_template, f"service template `{raw_name}`")
        templates[raw_name] = ServiceTemplate(
            description=get_optional_str(template_map, "description", ""),
            overlay_name_template=get_optional_str(
                template_map,
                "overlay_name_template",
                "{service}-{environment}",
            ),
            smoke_host_template=get_optional_str(
                template_map,
                "smoke_host_template",
                "{service}",
            ),
            smoke_path=get_optional_str(template_map, "smoke_path", "/health"),
            smoke_port=get_optional_str(template_map, "smoke_port", ""),
            ghcr_org=get_optional_str(template_map, "ghcr_org", "brunogao"),
            harbor_registry=get_optional_str(
                template_map,
                "harbor_registry",
                "harbor.eu.lingjingwanxiang.cn",
            ),
            harbor_project=get_optional_str(template_map, "harbor_project", "ljwx"),
            profiles=normalize_profiles(template_map.get("profiles", "all")),
            namespace_profile=get_optional_str(template_map, "namespace_profile", ""),
            registry_profile=get_optional_str(
                template_map,
                "registry_profile",
                "ghcr-and-harbor",
            ),
            runtime_secret_profile=get_optional_str(
                template_map,
                "runtime_secret_profile",
                "app-runtime",
            ),
            capabilities=normalize_string_tuple(template_map.get("capabilities", [])),
            scaffold_app=normalize_bool(template_map.get("scaffold_app"), False),
            generate_argocd_app=normalize_bool(
                template_map.get("generate_argocd_app"),
                True,
            ),
            cluster_bootstrap=normalize_bool(
                template_map.get("cluster_bootstrap"),
                True,
            ),
            ingress_profile=get_optional_str(template_map, "ingress_profile", "none"),
            public_host_template=get_optional_str(
                template_map, "public_host_template", ""
            ),
            argocd_order=get_optional_int(template_map, "argocd_order", 90),
        )
    if "service-default" not in templates:
        raise ValueError("service templates 必须定义 `service-default`")
    return templates


def load_ingress_profiles(repo_root: Path, path: Path) -> dict[str, IngressProfile]:
    resolved_path = resolve_repo_path(repo_root, path)
    root = load_yaml_mapping(resolved_path)
    profiles_obj = expect_mapping(root.get("profiles"), "ingress profiles")
    profiles: dict[str, IngressProfile] = {}
    for raw_name, raw_profile in profiles_obj.items():
        if not isinstance(raw_name, str):
            raise ValueError("ingress profile 名称必须是字符串")
        profile_map = expect_mapping(raw_profile, f"ingress profile `{raw_name}`")
        annotations_map = (
            parse_string_mapping(
                profile_map.get("annotations"),
                f"ingress profile `{raw_name}`.annotations",
            )
            if profile_map.get("annotations") is not None
            else {}
        )
        profiles[raw_name] = IngressProfile(
            description=get_optional_str(profile_map, "description", ""),
            ingress_class_name=get_optional_str(profile_map, "ingress_class_name", ""),
            annotations=tuple(annotations_map.items()),
            tls_enabled=normalize_bool(profile_map.get("tls_enabled"), False),
            cluster_issuer=get_optional_str(profile_map, "cluster_issuer", ""),
            path=get_optional_str(profile_map, "path", "/"),
            path_type=get_optional_str(profile_map, "path_type", "Prefix"),
            service_port=get_optional_int(profile_map, "service_port", 80),
        )
    if "none" not in profiles:
        profiles["none"] = IngressProfile(
            description="No ingress is generated.",
            ingress_class_name="",
            annotations=(),
            tls_enabled=False,
            cluster_issuer="",
            path="/",
            path_type="Prefix",
            service_port=80,
        )
    return profiles


def load_namespace_profiles(repo_root: Path, path: Path) -> dict[str, NamespaceProfile]:
    resolved_path = resolve_repo_path(repo_root, path)
    root = load_yaml_mapping(resolved_path)
    profiles_obj = expect_mapping(root.get("profiles"), "namespace profiles")
    profiles: dict[str, NamespaceProfile] = {}
    for raw_name, raw_profile in profiles_obj.items():
        if not isinstance(raw_name, str):
            raise ValueError("namespace profile 名称必须是字符串")
        profile_map = expect_mapping(raw_profile, f"namespace profile `{raw_name}`")
        limit_range = expect_mapping(
            profile_map.get("limit_range"),
            f"namespace profile `{raw_name}`.limit_range",
        )
        profiles[raw_name] = NamespaceProfile(
            description=str(profile_map.get("description", "")).strip(),
            resource_quota=parse_string_mapping(
                profile_map.get("resource_quota"),
                f"namespace profile `{raw_name}`.resource_quota",
            ),
            limit_max=parse_string_mapping(
                limit_range.get("max"),
                f"namespace profile `{raw_name}`.limit_range.max",
            ),
            limit_min=parse_string_mapping(
                limit_range.get("min"),
                f"namespace profile `{raw_name}`.limit_range.min",
            ),
            limit_default=parse_string_mapping(
                limit_range.get("default"),
                f"namespace profile `{raw_name}`.limit_range.default",
            ),
            limit_default_request=parse_string_mapping(
                limit_range.get("default_request"),
                f"namespace profile `{raw_name}`.limit_range.default_request",
            ),
        )
    return profiles


def load_capability_profiles(
    repo_root: Path,
    path: Path,
) -> tuple[
    dict[str, RegistryProfile],
    dict[str, RuntimeSecretProfile],
    dict[str, CapabilityDefinition],
]:
    resolved_path = resolve_repo_path(repo_root, path)
    root = load_yaml_mapping(resolved_path)

    registry_profiles_obj = expect_mapping(
        root.get("registry_profiles"), "registry profiles"
    )
    registry_profiles: dict[str, RegistryProfile] = {}
    for raw_name, raw_profile in registry_profiles_obj.items():
        if not isinstance(raw_name, str):
            raise ValueError("registry profile 名称必须是字符串")
        profile_map = expect_mapping(raw_profile, f"registry profile `{raw_name}`")
        registry_profiles[raw_name] = RegistryProfile(
            description=str(profile_map.get("description", "")).strip(),
            image_pull_secrets=normalize_string_tuple(
                profile_map.get("image_pull_secrets", [])
            ),
        )

    runtime_secret_profiles_obj = expect_mapping(
        root.get("runtime_secret_profiles"),
        "runtime secret profiles",
    )
    runtime_secret_profiles: dict[str, RuntimeSecretProfile] = {}
    for raw_name, raw_profile in runtime_secret_profiles_obj.items():
        if not isinstance(raw_name, str):
            raise ValueError("runtime secret profile 名称必须是字符串")
        profile_map = expect_mapping(
            raw_profile, f"runtime secret profile `{raw_name}`"
        )
        runtime_secret_profiles[raw_name] = RuntimeSecretProfile(
            description=str(profile_map.get("description", "")).strip(),
            contract_secret_names=normalize_string_tuple(
                profile_map.get("contract_secret_names", []),
            ),
        )

    capabilities_obj = expect_mapping(root.get("capabilities"), "capabilities")
    capabilities: dict[str, CapabilityDefinition] = {}
    for raw_name, raw_capability in capabilities_obj.items():
        if not isinstance(raw_name, str):
            raise ValueError("capability 名称必须是字符串")
        capability_map = expect_mapping(raw_capability, f"capability `{raw_name}`")
        capabilities[raw_name] = CapabilityDefinition(
            scope=get_optional_str(capability_map, "scope", "application"),
            description=get_optional_str(capability_map, "description", ""),
        )

    return registry_profiles, runtime_secret_profiles, capabilities


def load_platform_profiles(
    repo_root: Path,
    namespace_profiles_path: Path,
    capability_profiles_path: Path,
) -> PlatformProfiles:
    registry_profiles, runtime_secret_profiles, capabilities = load_capability_profiles(
        repo_root,
        capability_profiles_path,
    )
    return PlatformProfiles(
        namespace_profiles=load_namespace_profiles(repo_root, namespace_profiles_path),
        registry_profiles=registry_profiles,
        runtime_secret_profiles=runtime_secret_profiles,
        capabilities=capabilities,
    )


def resolve_entry_capabilities(
    entry: OnboardEntry,
    registry_profile: RegistryProfile,
    runtime_secret_profile: RuntimeSecretProfile,
) -> tuple[str, ...]:
    out: list[str] = list(entry.capabilities)
    image_pull_secret_names = set(registry_profile.image_pull_secrets)
    contract_secret_names = set(runtime_secret_profile.contract_secret_names)

    if "ghcr-pull" in image_pull_secret_names:
        out.append("ghcr_pull")
    if "regcred" in image_pull_secret_names:
        out.append("harbor_pull")
    if "runtime-app" in contract_secret_names:
        out.append("runtime_app_secret")
    if "runtime-infra" in contract_secret_names:
        out.append("runtime_infra_secret")
    if "runtime-llm" in contract_secret_names:
        out.append("runtime_llm_secret")
    return tuple(dict.fromkeys(out))


def resolve_entry(entry: OnboardEntry, profiles: PlatformProfiles) -> ResolvedEntry:
    try:
        namespace_profile = profiles.namespace_profiles[entry.namespace_profile]
    except KeyError as exc:
        raise ValueError(
            f"未定义 namespace_profile `{entry.namespace_profile}` for {entry.service}/{entry.environment}"
        ) from exc

    try:
        registry_profile = profiles.registry_profiles[entry.registry_profile]
    except KeyError as exc:
        raise ValueError(
            f"未定义 registry_profile `{entry.registry_profile}` for {entry.service}/{entry.environment}"
        ) from exc

    try:
        runtime_secret_profile = profiles.runtime_secret_profiles[
            entry.runtime_secret_profile
        ]
    except KeyError as exc:
        raise ValueError(
            f"未定义 runtime_secret_profile `{entry.runtime_secret_profile}` for {entry.service}/{entry.environment}"
        ) from exc

    capabilities = resolve_entry_capabilities(
        entry, registry_profile, runtime_secret_profile
    )
    for capability in capabilities:
        if capability not in profiles.capabilities:
            raise ValueError(
                f"未定义 capability `{capability}` for {entry.service}/{entry.environment}"
            )

    return ResolvedEntry(
        entry=entry,
        namespace_profile=namespace_profile,
        registry_profile=registry_profile,
        runtime_secret_profile=runtime_secret_profile,
        capabilities=capabilities,
    )


def ensure_service_mapping(path: Path, entry: OnboardEntry, dry_run: bool) -> bool:
    payload = load_yaml_mapping(path)
    services_obj = payload.get("services")
    services = services_obj if isinstance(services_obj, dict) else {}
    payload["services"] = services

    changed = False
    for component in entry.components:
        svc_obj = services.get(component.service_name)
        svc_map = svc_obj if isinstance(svc_obj, dict) else {}
        services[component.service_name] = svc_map

        envs_obj = svc_map.get("envs")
        envs = envs_obj if isinstance(envs_obj, dict) else {}
        svc_map["envs"] = envs

        current = envs.get(entry.environment)
        current_map = current if isinstance(current, dict) else {}
        desired: dict[str, object] = {
            "overlayPath": entry.overlay_path,
            "kustomizeImageName": component.kustomize_image_name,
            "harborImage": component.harbor_image,
            "argocdApp": entry.argocd_app,
        }
        if component.deploy_image:
            desired["deployImage"] = component.deploy_image
        if current_map != desired:
            envs[entry.environment] = desired
            changed = True

    if changed and not dry_run:
        dump_yaml(path, payload)
    return changed


def ensure_smoke_target(path: Path, entry: OnboardEntry, dry_run: bool) -> bool:
    payload = load_json_object(path)
    targets_obj = payload.get("targets")
    targets = targets_obj if isinstance(targets_obj, list) else []
    payload["targets"] = targets

    changed = False
    for component in entry.components:
        if not component.smoke_endpoint:
            continue

        desired = {
            "service": component.service_name,
            "environment": entry.environment,
            "argocd_app": entry.argocd_app,
            "endpoint": component.smoke_endpoint,
        }
        found = False
        for idx, target in enumerate(targets):
            if not isinstance(target, dict):
                continue
            service = str(target.get("service", ""))
            environment = str(target.get("environment", ""))
            if service == component.service_name and environment == entry.environment:
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


def ensure_argocd_app_file(
    repo_root: Path,
    entry: OnboardEntry,
    deploy_repo_url: str,
    deploy_ref: str,
    dry_run: bool,
) -> bool:
    if not entry.generate_argocd_app:
        return False

    source_path = str(Path(entry.overlay_path).parent).replace("\\", "/")
    payload: dict[str, object] = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {
            "name": entry.argocd_app,
            "namespace": "argocd",
        },
        "spec": {
            "project": "default",
            "source": {
                "repoURL": deploy_repo_url,
                "targetRevision": deploy_ref,
                "path": source_path,
            },
            "destination": {
                "server": "https://kubernetes.default.svc",
                "namespace": entry.deploy_namespace,
            },
            "syncPolicy": {
                "automated": {
                    "prune": True,
                    "selfHeal": True,
                },
                "syncOptions": ["CreateNamespace=true"],
            },
        },
    }
    content = dump_yaml_text(payload)
    app_path = repo_root / entry.argocd_app_file
    current = app_path.read_text(encoding="utf-8") if app_path.exists() else ""
    if current == content:
        return False
    if not dry_run:
        write_text_file(app_path, content)
    return True


def build_deployment_doc(
    resolved_entry: ResolvedEntry,
) -> dict[str, object]:
    entry = resolved_entry.entry
    annotations = {
        f"{ANNOTATION_PREFIX}/namespace-profile": entry.namespace_profile,
        f"{ANNOTATION_PREFIX}/registry-profile": entry.registry_profile,
        f"{ANNOTATION_PREFIX}/runtime-secret-profile": entry.runtime_secret_profile,
        f"{ANNOTATION_PREFIX}/capabilities": ",".join(resolved_entry.capabilities),
    }
    container: dict[str, object] = {
        "name": entry.service,
        "image": f"{entry.harbor_image}:latest",
        "ports": [
            {
                "name": "http",
                "containerPort": 80,
                "protocol": "TCP",
            }
        ],
        "livenessProbe": {
            "httpGet": {
                "path": "/",
                "port": "http",
            },
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
        },
        "readinessProbe": {
            "httpGet": {
                "path": "/",
                "port": "http",
            },
            "initialDelaySeconds": 5,
            "periodSeconds": 5,
        },
    }
    if resolved_entry.runtime_secret_profile.contract_secret_names:
        env_from: list[dict[str, object]] = []
        for secret_name in resolved_entry.runtime_secret_profile.contract_secret_names:
            env_from.append(
                {
                    "secretRef": {
                        "name": secret_name,
                        "optional": True,
                    }
                }
            )
        container["envFrom"] = env_from

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": entry.service,
            "labels": {
                "app": entry.service,
            },
            "annotations": annotations,
        },
        "spec": {
            "replicas": 1,
            "selector": {
                "matchLabels": {
                    "app": entry.service,
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": entry.service,
                    },
                    "annotations": annotations,
                },
                "spec": {
                    "containers": [container],
                },
            },
        },
    }


def ensure_kustomization_resource(
    kustomization_path: Path,
    resource_name: str,
    dry_run: bool,
) -> bool:
    root = load_yaml_mapping(kustomization_path)
    resources_obj = root.get("resources")
    resources = resources_obj if isinstance(resources_obj, list) else []
    root["resources"] = resources
    if resource_name in resources:
        return False
    resources.append(resource_name)
    if not dry_run:
        dump_yaml(kustomization_path, root)
    return True


def build_ingress_doc(entry: OnboardEntry) -> dict[str, object]:
    metadata: dict[str, object] = {
        "name": f"{entry.service}-ingress",
    }
    annotations = dict(entry.ingress_annotations)
    if annotations:
        metadata["annotations"] = annotations

    rule: dict[str, object] = {
        "host": entry.public_host,
        "http": {
            "paths": [
                {
                    "path": entry.public_path,
                    "pathType": entry.public_path_type,
                    "backend": {
                        "service": {
                            "name": entry.public_service_name,
                            "port": {
                                "number": entry.public_service_port,
                            },
                        }
                    },
                }
            ]
        },
    }
    spec: dict[str, object] = {
        "ingressClassName": entry.ingress_class_name,
        "rules": [rule],
    }
    if entry.tls_enabled:
        spec["tls"] = [
            {
                "hosts": [entry.public_host],
                "secretName": entry.tls_secret_name,
            }
        ]

    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": metadata,
        "spec": spec,
    }


def ensure_generated_ingress_artifacts(
    repo_root: Path,
    entry: OnboardEntry,
    dry_run: bool,
) -> int:
    if not entry.public_host or not entry.generate_ingress:
        return 0

    overlay_path = repo_root / entry.overlay_path
    if not overlay_path.exists():
        raise ValueError(
            f"overlay kustomization 不存在，无法生成 ingress: {overlay_path}"
        )

    ingress_path = overlay_path.parent / "ingress.yaml"
    ingress_content = dump_yaml_text(build_ingress_doc(entry))
    changes = 0

    current = ingress_path.read_text(encoding="utf-8") if ingress_path.exists() else ""
    if current != ingress_content:
        changes += 1
        if not dry_run:
            write_text_file(ingress_path, ingress_content)

    if ensure_kustomization_resource(overlay_path, "ingress.yaml", dry_run):
        changes += 1

    return changes


def scaffold_app_manifest(
    repo_root: Path,
    resolved_entry: ResolvedEntry,
    dry_run: bool,
) -> int:
    entry = resolved_entry.entry
    if not entry.scaffold_app:
        return 0

    overlay_path = repo_root / entry.overlay_path
    overlay_dir = overlay_path.parent
    base_dir = overlay_dir.parent.parent / "base"

    deployment_path = base_dir / "deployment.yaml"
    service_path = base_dir / "service.yaml"
    base_kustomization_path = base_dir / "kustomization.yaml"

    deployment_content = dump_yaml_text(build_deployment_doc(resolved_entry))
    service_content = dump_yaml_text(
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": entry.service,
                "labels": {
                    "app": entry.service,
                },
            },
            "spec": {
                "type": "ClusterIP",
                "selector": {
                    "app": entry.service,
                },
                "ports": [
                    {
                        "name": "http",
                        "port": 80,
                        "targetPort": "http",
                        "protocol": "TCP",
                    }
                ],
            },
        }
    )
    base_kustomization_content = dump_yaml_text(
        {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "resources": [
                "deployment.yaml",
                "service.yaml",
            ],
        }
    )
    overlay_resources = [
        "../../base",
    ]
    if entry.public_host and entry.generate_ingress:
        overlay_resources.append("ingress.yaml")
    overlay_content = dump_yaml_text(
        {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "namespace": entry.deploy_namespace,
            "resources": overlay_resources,
            "images": [
                {
                    "name": entry.kustomize_image_name,
                    "newName": entry.harbor_image,
                    "newTag": "latest",
                }
            ],
        }
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


def build_namespace_baseline_documents(
    resolved_entry: ResolvedEntry,
) -> list[dict[str, object]]:
    entry = resolved_entry.entry
    annotations = {
        f"{ANNOTATION_PREFIX}/namespace-profile": entry.namespace_profile,
        f"{ANNOTATION_PREFIX}/registry-profile": entry.registry_profile,
        f"{ANNOTATION_PREFIX}/runtime-secret-profile": entry.runtime_secret_profile,
        f"{ANNOTATION_PREFIX}/capabilities": ",".join(resolved_entry.capabilities),
    }
    namespace_doc: dict[str, object] = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": entry.deploy_namespace,
            "labels": {
                "name": entry.deploy_namespace,
                "environment": entry.environment,
                "app": entry.service,
            },
            "annotations": annotations,
        },
    }
    service_account_doc: dict[str, object] = {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {
            "name": "default",
            "namespace": entry.deploy_namespace,
            "annotations": annotations,
        },
    }
    if resolved_entry.registry_profile.image_pull_secrets:
        service_account_doc["imagePullSecrets"] = [
            {"name": secret_name}
            for secret_name in resolved_entry.registry_profile.image_pull_secrets
        ]

    resource_quota_doc: dict[str, object] = {
        "apiVersion": "v1",
        "kind": "ResourceQuota",
        "metadata": {
            "name": f"{entry.deploy_namespace}-quota",
            "namespace": entry.deploy_namespace,
        },
        "spec": {
            "hard": resolved_entry.namespace_profile.resource_quota,
        },
    }
    limit_range_doc: dict[str, object] = {
        "apiVersion": "v1",
        "kind": "LimitRange",
        "metadata": {
            "name": f"{entry.deploy_namespace}-limits",
            "namespace": entry.deploy_namespace,
        },
        "spec": {
            "limits": [
                {
                    "max": resolved_entry.namespace_profile.limit_max,
                    "min": resolved_entry.namespace_profile.limit_min,
                    "default": resolved_entry.namespace_profile.limit_default,
                    "defaultRequest": resolved_entry.namespace_profile.limit_default_request,
                    "type": "Container",
                }
            ]
        },
    }
    return [
        namespace_doc,
        service_account_doc,
        resource_quota_doc,
        limit_range_doc,
    ]


def ensure_namespace_baseline_file(
    repo_root: Path,
    resolved_entry: ResolvedEntry,
    cluster_root: Path,
    dry_run: bool,
) -> bool:
    path = (
        repo_root
        / cluster_root
        / f"namespace-{resolved_entry.entry.deploy_namespace}.yaml"
    )
    content = dump_yaml_documents_text(
        build_namespace_baseline_documents(resolved_entry)
    )
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if current == content:
        return False
    if not dry_run:
        write_text_file(path, content)
    return True


def ensure_cluster_application_file(
    repo_root: Path,
    entry: OnboardEntry,
    deploy_repo_url: str,
    deploy_ref: str,
    cluster_root: Path,
    dry_run: bool,
) -> bool:
    application_path = (
        repo_root
        / cluster_root
        / f"{entry.service}-{entry.environment}-application.yaml"
    )
    source_path = str(Path(entry.overlay_path).parent).replace("\\", "/")
    payload: dict[str, object] = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {
            "name": entry.argocd_app,
            "namespace": "argocd",
        },
        "spec": {
            "project": "default",
            "source": {
                "repoURL": deploy_repo_url,
                "targetRevision": deploy_ref,
                "path": source_path,
            },
            "destination": {
                "server": "https://kubernetes.default.svc",
                "namespace": entry.deploy_namespace,
            },
            "syncPolicy": {
                "automated": {
                    "prune": True,
                    "selfHeal": True,
                },
                "syncOptions": ["CreateNamespace=true"],
            },
        },
    }
    content = dump_yaml_text(payload)
    current = (
        application_path.read_text(encoding="utf-8")
        if application_path.exists()
        else ""
    )
    if current == content:
        return False
    if not dry_run:
        write_text_file(application_path, content)
    return True


def ensure_cluster_kustomization_resources(
    repo_root: Path,
    cluster_kustomization_path: Path,
    entry: OnboardEntry,
    dry_run: bool,
) -> int:
    resolved_path = resolve_repo_path(repo_root, cluster_kustomization_path)
    if not resolved_path.exists():
        raise ValueError(f"cluster kustomization 不存在: {resolved_path}")

    root = load_yaml_mapping(resolved_path)
    resources_obj = root.get("resources")
    resources = resources_obj if isinstance(resources_obj, list) else []
    root["resources"] = resources

    changed = 0
    for item in (
        f"namespace-{entry.deploy_namespace}.yaml",
        f"{entry.service}-{entry.environment}-application.yaml",
    ):
        if item not in resources:
            resources.append(item)
            changed += 1
    if changed > 0 and not dry_run:
        dump_yaml(resolved_path, root)
    return changed


def is_production_environment(environment: str) -> bool:
    return environment.strip().lower() in {"prod", "production"}


def default_cluster_kustomization_for_entry(
    entry: OnboardEntry,
    configured_path: Path,
) -> Path:
    if configured_path != DEFAULT_CLUSTER_KUSTOMIZATION_PATH:
        return configured_path
    if is_production_environment(entry.environment):
        return DEFAULT_PROD_CLUSTER_KUSTOMIZATION_PATH
    return configured_path


def capability_description(
    capability_name: str,
    definitions: dict[str, CapabilityDefinition],
) -> str:
    definition = definitions[capability_name]
    return f"{capability_name} ({definition.scope}): {definition.description}"


def secret_example_payload(secret_name: str, namespace: str) -> dict[str, object]:
    if secret_name == "runtime-infra":
        string_data: dict[str, str] = {
            "DB_HOST": "mysql-infra.infra.svc.cluster.local",
            "DB_PORT": "3306",
            "DB_NAME": "<replace-with-db-name>",
            "DB_USER": "root",
            "DB_PASSWORD": "<set-via-secret-manager>",
            "REDIS_HOST": "redis-infra-master.infra.svc.cluster.local",
            "REDIS_PORT": "6379",
            "REDIS_PASSWORD": "<set-via-secret-manager>",
        }
    elif secret_name == "runtime-llm":
        string_data = {
            "AI_LOCAL_ENABLED": "false",
            "AI_CLOUD_ENABLED": "true",
            "AI_CLOUD_PROVIDER": "openai",
            "AI_CLOUD_API_KEY": "<set-via-secret-manager>",
            "AI_CLOUD_BASE_URL": "<replace-with-proxy-url>",
            "AI_CLOUD_MODEL": "claude-sonnet-4-6",
            "AI_LLM_TYPE": "openai",
            "AI_LLM_API_KEY": "<set-via-secret-manager>",
            "AI_LLM_BASE_URL": "<replace-with-proxy-url>",
            "AI_LLM_MODEL": "claude-sonnet-4-6",
            "ANTHROPIC_AUTH_TOKEN": "<set-via-secret-manager>",
            "ANTHROPIC_BASE_URL": "<replace-with-proxy-url>",
        }
    else:
        string_data = {
            "EXAMPLE_KEY": "<replace-with-app-secret>",
        }
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": secret_name,
            "namespace": namespace,
            "annotations": {
                f"{ANNOTATION_PREFIX}/generated-example": "true",
            },
        },
        "type": "Opaque",
        "stringData": string_data,
    }


def extract_custom_readme_notes(
    existing_readme: str,
    standard_notes: tuple[str, ...],
) -> tuple[str, ...]:
    notes_marker = "## Notes"
    start_index = existing_readme.find(notes_marker)
    if start_index == -1:
        return ()

    notes_section = existing_readme[start_index + len(notes_marker) :]
    next_heading_index = notes_section.find("\n## ")
    if next_heading_index != -1:
        notes_section = notes_section[:next_heading_index]

    standard_set = set(standard_notes)
    custom_notes: list[str] = []
    for raw_line in notes_section.splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("- "):
            continue
        if line.startswith("- Namespace baseline is generated into `cluster"):
            continue
        if line in standard_set or line in custom_notes:
            continue
        custom_notes.append(line)
    return tuple(custom_notes)


def render_runtime_contract_readme(
    resolved_entry: ResolvedEntry,
    capability_definitions: dict[str, CapabilityDefinition],
    cluster_root: Path,
    existing_readme: str,
) -> str:
    entry = resolved_entry.entry
    image_pull_secrets = (
        ", ".join(resolved_entry.registry_profile.image_pull_secrets) or "none"
    )
    contract_secret_names = (
        ", ".join(
            resolved_entry.runtime_secret_profile.contract_secret_names,
        )
        or "none"
    )
    capability_lines = "\n".join(
        f"- {capability_description(name, capability_definitions)}"
        for name in resolved_entry.capabilities
    )
    bootstrap_commands: list[str] = []
    if resolved_entry.registry_profile.image_pull_secrets:
        bootstrap_commands.append(
            "bash scripts/ops/sync-registry-pull-secrets.sh "
            f"--target-namespace {entry.deploy_namespace} "
            f"--registry-profile {entry.registry_profile}"
        )
    if "runtime-infra" in resolved_entry.runtime_secret_profile.contract_secret_names:
        bootstrap_commands.append(
            "bash scripts/create-app-secret.sh "
            f"--app {entry.service} "
            f"--namespace {entry.deploy_namespace} "
            "--profile shared-infra "
            "--secret-name runtime-infra "
            "--db-name <replace-with-db-name> "
            "--skip-llm"
        )
    if "runtime-llm" in resolved_entry.runtime_secret_profile.contract_secret_names:
        bootstrap_commands.append(
            "bash scripts/sync-llm-secret.sh "
            f"--app {entry.service} "
            f"--namespace {entry.deploy_namespace} "
            "--secret-name runtime-llm "
            "/root/codes/.env"
        )
    if "runtime-app" in resolved_entry.runtime_secret_profile.contract_secret_names:
        bootstrap_commands.append(
            "kubectl create secret generic runtime-app "
            f"-n {entry.deploy_namespace} "
            "--from-literal=EXAMPLE_KEY='replace-me'"
        )
    commands_block = (
        "\n".join(bootstrap_commands)
        if bootstrap_commands
        else "# No bootstrap command required."
    )
    if entry.public_host:
        ingress_generation_mode = (
            "enabled"
            if entry.generate_ingress
            else "disabled (managed by existing manifests)"
        )
        public_endpoint_block = (
            "## Public endpoint\n\n"
            f"- ingress profile: `{entry.ingress_profile}`\n"
            f"- host: `https://{entry.public_host}`\n"
            f"- ingress class: `{entry.ingress_class_name}`\n"
            f"- cluster issuer: `{entry.cluster_issuer or 'none'}`\n"
            f"- tls secret: `{entry.tls_secret_name or 'none'}`\n"
            f"- ingress artifact generation: `{ingress_generation_mode}`\n\n"
        )
    else:
        public_endpoint_block = ""
    if entry.cluster_bootstrap:
        cluster_note = (
            f"- Namespace baseline is generated into `{cluster_root.as_posix()}/namespace-<namespace>.yaml` "
            "and should remain the source of truth."
        )
    else:
        cluster_note = (
            "- `cluster_bootstrap` is disabled for this entry; keep the existing cluster "
            "namespace/application manifests as the current source of truth."
        )
    standard_notes = (
        "- `runtime-contract/*.secret.example.yaml` are placeholders only and must not contain real credentials.",
        cluster_note,
        "- For legacy workloads, migrate deployment manifests gradually to `runtime-infra`, `runtime-llm`, and `runtime-app` instead of app-specific secret names.",
    )
    custom_notes = extract_custom_readme_notes(existing_readme, standard_notes)
    notes_block = "\n".join((*standard_notes, *custom_notes))
    return (
        f"# {entry.service} capability contract ({entry.environment})\n\n"
        "## Namespace baseline\n\n"
        f"- namespace: `{entry.deploy_namespace}`\n"
        f"- namespace profile: `{entry.namespace_profile}`\n"
        f"- registry profile: `{entry.registry_profile}`\n"
        f"- runtime secret profile: `{entry.runtime_secret_profile}`\n"
        f"- image pull secrets: `{image_pull_secrets}`\n"
        f"- runtime contract secrets: `{contract_secret_names}`\n\n"
        "## Capabilities\n\n"
        f"{capability_lines or '- none'}\n\n"
        f"{public_endpoint_block}"
        "## Bootstrap commands\n\n"
        "```bash\n"
        f"{commands_block}\n"
        "```\n\n"
        "## Notes\n\n"
        f"{notes_block}\n"
    )


def ensure_runtime_contract_artifacts(
    repo_root: Path,
    resolved_entry: ResolvedEntry,
    capability_definitions: dict[str, CapabilityDefinition],
    cluster_root: Path,
    dry_run: bool,
) -> int:
    entry = resolved_entry.entry
    overlay_dir = (repo_root / entry.overlay_path).parent
    contract_dir = overlay_dir / "runtime-contract"
    contract_doc_path = contract_dir / "contract.yaml"
    readme_path = contract_dir / "README.md"

    contract_payload: dict[str, object] = {
        "service": entry.service,
        "environment": entry.environment,
        "namespace": entry.deploy_namespace,
        "cluster_bootstrap": entry.cluster_bootstrap,
        "ingress_profile": entry.ingress_profile,
        "public_host": entry.public_host,
        "generate_ingress": entry.generate_ingress,
        "ingress_class_name": entry.ingress_class_name,
        "cluster_issuer": entry.cluster_issuer,
        "tls_secret_name": entry.tls_secret_name,
        "namespace_profile": entry.namespace_profile,
        "registry_profile": entry.registry_profile,
        "runtime_secret_profile": entry.runtime_secret_profile,
        "capabilities": list(resolved_entry.capabilities),
        "image_pull_secrets": list(resolved_entry.registry_profile.image_pull_secrets),
        "contract_secret_names": list(
            resolved_entry.runtime_secret_profile.contract_secret_names,
        ),
    }
    existing_readme = read_text_file(readme_path) if readme_path.exists() else ""

    files_to_write: dict[Path, str] = {
        contract_doc_path: dump_yaml_text(contract_payload),
        readme_path: render_runtime_contract_readme(
            resolved_entry,
            capability_definitions,
            cluster_root,
            existing_readme,
        ),
    }

    for secret_name in resolved_entry.runtime_secret_profile.contract_secret_names:
        files_to_write[contract_dir / f"{secret_name}.secret.example.yaml"] = (
            dump_yaml_text(
                secret_example_payload(secret_name, entry.deploy_namespace),
            )
        )

    changes = 0
    for file_path, content in files_to_write.items():
        current = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        if current != content:
            changes += 1
            if not dry_run:
                write_text_file(file_path, content)
    return changes


def apply_onboarding(
    repo_root: Path,
    entries: list[OnboardEntry],
    profiles: PlatformProfiles,
    dry_run: bool,
    cluster_bootstrap: bool,
    cluster_kustomization_path: Path,
    deploy_repo_url: str,
    deploy_ref: str,
) -> int:
    changed_files = 0
    for entry in entries:
        resolved_entry = resolve_entry(entry, profiles)
        entry_cluster_kustomization_path = default_cluster_kustomization_for_entry(
            entry,
            cluster_kustomization_path,
        )
        entry_cluster_root = entry_cluster_kustomization_path.parent
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

        scaffold_changes = scaffold_app_manifest(repo_root, resolved_entry, dry_run)
        if scaffold_changes > 0:
            changed_files += scaffold_changes
            print(f"  - 已生成应用骨架: {scaffold_changes} 个文件")

        ingress_changes = ensure_generated_ingress_artifacts(repo_root, entry, dry_run)
        if ingress_changes > 0:
            changed_files += ingress_changes
            print(f"  - 已生成公网入口: {ingress_changes} 个文件")

        if ensure_argocd_app_file(
            repo_root,
            entry,
            deploy_repo_url,
            deploy_ref,
            dry_run,
        ):
            changed_files += 1
            print(f"  - 已生成 Argo Application: {entry.argocd_app_file}")

        runtime_contract_changes = ensure_runtime_contract_artifacts(
            repo_root,
            resolved_entry,
            profiles.capabilities,
            entry_cluster_root,
            dry_run,
        )
        if runtime_contract_changes > 0:
            changed_files += runtime_contract_changes
            print(f"  - 已生成 runtime contract: {runtime_contract_changes} 个文件")

        if cluster_bootstrap and entry.cluster_bootstrap:
            if ensure_namespace_baseline_file(
                repo_root,
                resolved_entry,
                entry_cluster_root,
                dry_run,
            ):
                changed_files += 1
                print(
                    "  - 已生成 namespace baseline: "
                    f"{entry_cluster_root.as_posix()}/namespace-{entry.deploy_namespace}.yaml"
                )
            if ensure_cluster_application_file(
                repo_root,
                entry,
                deploy_repo_url,
                deploy_ref,
                entry_cluster_root,
                dry_run,
            ):
                changed_files += 1
                print(
                    "  - 已生成 cluster application: "
                    f"{entry_cluster_root.as_posix()}/{entry.service}-{entry.environment}-application.yaml"
                )

            cluster_kustomization_changes = ensure_cluster_kustomization_resources(
                repo_root,
                entry_cluster_kustomization_path,
                entry,
                dry_run,
            )
            if cluster_kustomization_changes > 0:
                changed_files += cluster_kustomization_changes
                print(
                    "  - 已更新 cluster kustomization: "
                    f"{cluster_kustomization_changes} 条资源引用"
                )

    if dry_run:
        print(f"[onboard] dry-run 完成，预计变更文件数: {changed_files}")
    else:
        print(f"[onboard] 执行完成，变更文件数: {changed_files}")
    return changed_files


def parse_bool_arg(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError("只支持 true/false")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量接入服务到 queue/promoter/smoke/evidence/capability 闭环"
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("factory/onboarding/services.catalog.yaml"),
        help="服务接入清单 YAML",
    )
    parser.add_argument(
        "--namespace-profiles",
        type=Path,
        default=DEFAULT_NAMESPACE_PROFILES_PATH,
        help="namespace profile 配置文件",
    )
    parser.add_argument(
        "--capability-profiles",
        type=Path,
        default=DEFAULT_CAPABILITY_PROFILES_PATH,
        help="capability profile 配置文件",
    )
    parser.add_argument(
        "--service-templates",
        type=Path,
        default=DEFAULT_SERVICE_TEMPLATES_PATH,
        help="service template 配置文件",
    )
    parser.add_argument(
        "--ingress-profiles",
        type=Path,
        default=DEFAULT_INGRESS_PROFILES_PATH,
        help="ingress profile 配置文件",
    )
    parser.add_argument(
        "--cluster-bootstrap",
        type=parse_bool_arg,
        default=True,
        help="是否生成 cluster namespace baseline 与 application (true/false)",
    )
    parser.add_argument(
        "--cluster-kustomization",
        type=Path,
        default=DEFAULT_CLUSTER_KUSTOMIZATION_PATH,
        help="cluster kustomization 路径（默认 dev/demos 用 cluster/，prod 自动切到 cluster-prod/）",
    )
    parser.add_argument(
        "--deploy-repo-url",
        default=DEFAULT_DEPLOY_REPO_URL,
        help="deploy repo URL，用于生成 Argo Application",
    )
    parser.add_argument(
        "--deploy-ref",
        default=DEFAULT_DEPLOY_REF,
        help="deploy repo revision，用于生成 Argo Application",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不落盘")
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="dry-run 发现漂移时返回非零退出码",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    catalog_path = resolve_repo_path(repo_root, args.catalog).resolve()
    if not catalog_path.exists():
        print(f"未找到 catalog 文件: {catalog_path}")
        return 1

    service_templates = load_service_templates(repo_root, args.service_templates)
    ingress_profiles = load_ingress_profiles(repo_root, args.ingress_profiles)
    entries = load_catalog(catalog_path, service_templates, ingress_profiles)
    profiles = load_platform_profiles(
        repo_root,
        args.namespace_profiles,
        args.capability_profiles,
    )
    changed_files = apply_onboarding(
        repo_root=repo_root,
        entries=entries,
        profiles=profiles,
        dry_run=args.dry_run,
        cluster_bootstrap=args.cluster_bootstrap,
        cluster_kustomization_path=args.cluster_kustomization,
        deploy_repo_url=args.deploy_repo_url,
        deploy_ref=args.deploy_ref,
    )
    if args.dry_run and args.fail_on_drift and changed_files > 0:
        print(f"[onboard] dry-run 检测到漂移，失败退出: {changed_files} 个文件")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

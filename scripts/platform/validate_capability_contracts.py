#!/usr/bin/env python3
"""Validate capability ownership and gateway contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError as exc:
    raise SystemExit(
        f"缺少依赖 jsonschema，请使用 uvx --with jsonschema --with pyyaml python <script>\n{exc}"
    ) from exc

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        f"缺少依赖 PyYAML，请使用 uvx --with pyyaml --with jsonschema python <script>\n{exc}"
    ) from exc


CAPABILITY_REGISTRY_FILE = Path("platform/assembly/capabilities.yaml")
SERVICE_MAP_FILE = Path("platform/contracts/service-capability-map.yaml")
RELEASE_VERSION_FILE = Path("release/platform-version.yaml")
GATEWAY_REQUEST_SCHEMA_FILE = Path("platform/contracts/capability-gateway-request.schema.json")
AUDIT_EVENT_SCHEMA_FILE = Path("platform/contracts/audit-event.schema.json")
KNOWN_PLATFORM_SERVICES = {"openclaw", "knowledge-processor", "n8n"}


class ValidationError(Exception):
    """Raised when a platform contract is invalid."""


def load_yaml_mapping(path: Path) -> dict[str, object]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError(f"{path} 根节点必须是 mapping")
    return {str(key): value for key, value in raw.items()}


def load_json_mapping(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValidationError(f"{path} 根节点必须是 object")
    return {str(key): value for key, value in raw.items()}


def require_mapping(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValidationError(f"{path} 必须是 mapping")
    return {str(key): item for key, item in value.items()}


def require_list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise ValidationError(f"{path} 必须是列表")
    return value


def require_non_empty_str(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{path} 必须是非空字符串")
    return value.strip()


def optional_non_empty_str(value: object, path: str) -> str | None:
    if value in ("", None):
        return None
    return require_non_empty_str(value, path)


def load_validator(path: Path) -> jsonschema.Draft202012Validator:
    schema = load_json_mapping(path)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def validate_examples() -> list[str]:
    errors: list[str] = []
    gateway_validator = load_validator(GATEWAY_REQUEST_SCHEMA_FILE)
    audit_validator = load_validator(AUDIT_EVENT_SCHEMA_FILE)

    gateway_example: dict[str, object] = {
        "trace_id": "trace-core-api-001",
        "caller_service": "openclaw",
        "capability": "customer.lookup",
        "profile_name": "default",
        "route_id": "knowledge_qa",
        "actor_id": "user-001",
        "payload": {"customer_id": "acme"},
        "meta": {"channel": "web"},
    }
    audit_example: dict[str, object] = {
        "audit_event_id": "audit-20260307-001",
        "timestamp": "2026-03-07T12:00:00+00:00",
        "component": "ljwx-core-api",
        "event_type": "capability_execution",
        "trace_id": "trace-core-api-001",
        "route_id": "knowledge_qa",
        "capability": "customer.lookup",
        "success": True,
        "caller_service": "openclaw",
        "details": {
            "duration_ms": 12,
            "profile_name": "default",
        },
    }

    for name, validator, payload in (
        ("capability-gateway-request", gateway_validator, gateway_example),
        ("audit-event", audit_validator, audit_example),
    ):
        try:
            validator.validate(payload)
        except jsonschema.ValidationError as exc:
            errors.append(f"{name} 示例不符合 schema: {exc.message}")

    return errors


def validate_version_references(
    capability_registry: dict[str, object],
    service_map: dict[str, object],
    release_version: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    capability_version = require_non_empty_str(
        capability_registry.get("version"),
        "platform/assembly/capabilities.yaml.version",
    )
    service_map_version = require_non_empty_str(
        service_map.get("version"),
        "platform/contracts/service-capability-map.yaml.version",
    )
    config_versions = require_mapping(
        release_version.get("config_versions"),
        "release/platform-version.yaml.config_versions",
    )

    expected_capability_ref = f"{CAPABILITY_REGISTRY_FILE.as_posix()}@{capability_version}"
    if config_versions.get("capability_registry") != expected_capability_ref:
        errors.append(
            "release/platform-version.yaml.config_versions.capability_registry "
            f"必须等于 {expected_capability_ref}"
        )

    expected_service_map_ref = f"{SERVICE_MAP_FILE.as_posix()}@{service_map_version}"
    if config_versions.get("service_capability_map") != expected_service_map_ref:
        errors.append(
            "release/platform-version.yaml.config_versions.service_capability_map "
            f"必须等于 {expected_service_map_ref}"
        )

    return errors


def validate_registry_and_service_map(
    capability_registry: dict[str, object],
    service_map: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    raw_capabilities = require_mapping(
        capability_registry.get("capabilities"),
        "platform/assembly/capabilities.yaml.capabilities",
    )
    capabilities: dict[str, dict[str, object]] = {}
    for capability_name, raw_capability in raw_capabilities.items():
        capability = require_mapping(
            raw_capability,
            f"platform/assembly/capabilities.yaml.capabilities.{capability_name}",
        )
        capabilities[capability_name] = capability
        try:
            require_non_empty_str(
                capability.get("executor"),
                f"platform/assembly/capabilities.yaml.capabilities.{capability_name}.executor",
            )
            require_non_empty_str(
                capability.get("owner_service"),
                f"platform/assembly/capabilities.yaml.capabilities.{capability_name}.owner_service",
            )
            require_non_empty_str(
                capability.get("auth"),
                f"platform/assembly/capabilities.yaml.capabilities.{capability_name}.auth",
            )
            require_non_empty_str(
                capability.get("audit"),
                f"platform/assembly/capabilities.yaml.capabilities.{capability_name}.audit",
            )
            timeout_ms = capability.get("timeout_ms")
            if not isinstance(timeout_ms, int) or timeout_ms <= 0:
                errors.append(
                    "platform/assembly/capabilities.yaml.capabilities."
                    f"{capability_name}.timeout_ms 必须是正整数"
                )
        except ValidationError as exc:
            errors.append(str(exc))

    services = require_mapping(
        service_map.get("services"),
        "platform/contracts/service-capability-map.yaml.services",
    )
    providers: dict[str, str] = {}

    for service_name, raw_service in services.items():
        service = require_mapping(
            raw_service,
            f"platform/contracts/service-capability-map.yaml.services.{service_name}",
        )
        for relation_name in ("provides", "consumes"):
            entries = require_list(
                service.get(relation_name),
                f"platform/contracts/service-capability-map.yaml.services.{service_name}.{relation_name}",
            )
            for index, raw_entry in enumerate(entries):
                entry = require_mapping(
                    raw_entry,
                    "platform/contracts/service-capability-map.yaml.services."
                    f"{service_name}.{relation_name}[{index}]",
                )
                try:
                    capability_name = require_non_empty_str(
                        entry.get("capability"),
                        "platform/contracts/service-capability-map.yaml.services."
                        f"{service_name}.{relation_name}[{index}].capability",
                    )
                except ValidationError as exc:
                    errors.append(str(exc))
                    continue

                if capability_name not in capabilities:
                    errors.append(
                        f"{service_name}.{relation_name}[{index}] 引用了未注册 capability: "
                        f"{capability_name}"
                    )
                    continue

                runtime_facing = entry.get("runtime_facing")
                if not isinstance(runtime_facing, bool):
                    errors.append(
                        f"{service_name}.{relation_name}[{index}].runtime_facing 必须是 boolean"
                    )

                dispatch_via = optional_non_empty_str(
                    entry.get("dispatch_via"),
                    f"{service_name}.{relation_name}[{index}].dispatch_via",
                )
                if dispatch_via and dispatch_via not in services and dispatch_via not in KNOWN_PLATFORM_SERVICES:
                    errors.append(
                        f"{service_name}.{relation_name}[{index}].dispatch_via 未知: {dispatch_via}"
                    )

                owner_service = require_non_empty_str(
                    capabilities[capability_name].get("owner_service"),
                    f"platform/assembly/capabilities.yaml.capabilities.{capability_name}.owner_service",
                )

                if relation_name == "provides":
                    if owner_service != service_name:
                        errors.append(
                            f"{service_name}.provides 声明了 {capability_name}，但 owner_service 是 "
                            f"{owner_service}"
                        )
                    previous_provider = providers.get(capability_name)
                    if previous_provider and previous_provider != service_name:
                        errors.append(
                            f"capability {capability_name} 被多个服务提供: "
                            f"{previous_provider}, {service_name}"
                        )
                    providers[capability_name] = service_name
                    continue

                if runtime_facing and dispatch_via is None:
                    errors.append(
                        f"{service_name}.consumes[{index}] 为 runtime_facing=true 时必须声明 dispatch_via"
                    )
                if dispatch_via and dispatch_via != owner_service:
                    errors.append(
                        f"{service_name}.consumes[{index}].dispatch_via={dispatch_via} "
                        f"必须与 owner_service={owner_service} 一致"
                    )

    for capability_name in capabilities:
        if capability_name not in providers:
            errors.append(f"capability {capability_name} 未在 service-capability-map 中声明 provider")

    return errors


def main() -> int:
    try:
        capability_registry = load_yaml_mapping(CAPABILITY_REGISTRY_FILE)
        service_map = load_yaml_mapping(SERVICE_MAP_FILE)
        release_version = load_yaml_mapping(RELEASE_VERSION_FILE)
    except ValidationError as exc:
        print(f"[capability-contracts] {exc}", file=sys.stderr)
        return 1

    errors = []
    try:
        errors.extend(
            validate_version_references(capability_registry, service_map, release_version)
        )
        errors.extend(validate_registry_and_service_map(capability_registry, service_map))
        errors.extend(validate_examples())
    except ValidationError as exc:
        errors.append(str(exc))

    if errors:
        for error in errors:
            print(f"[capability-contracts] {error}", file=sys.stderr)
        return 1

    capability_count = len(
        require_mapping(
            capability_registry.get("capabilities"),
            "platform/assembly/capabilities.yaml.capabilities",
        )
    )
    service_count = len(
        require_mapping(
            service_map.get("services"),
            "platform/contracts/service-capability-map.yaml.services",
        )
    )
    print(
        "[capability-contracts] valid "
        f"capabilities={capability_count} services={service_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

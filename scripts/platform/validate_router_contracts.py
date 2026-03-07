#!/usr/bin/env python3
"""Validate router contracts and routing configuration consistency."""

from __future__ import annotations

import argparse
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


SCHEMA_DIR = Path("platform/contracts")
ROUTING_DIR = Path("platform/routing")
RELEASE_VERSION_FILE = Path("release/platform-version.yaml")
ROUTING_FILES = (
    ROUTING_DIR / "routes.dev.yaml",
    ROUTING_DIR / "routes.prod.yaml",
)
ALLOWED_TOOL_POLICIES = {"none", "retrieval_only", "capability_registry"}
ALLOWED_TRANSPORTS = {"openclaw-gateway", "runtime"}


class ValidationError(Exception):
    """Raised when a contract file violates the expected shape."""


def load_json_mapping(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValidationError(f"{path} 根节点必须是 object")
    if not all(isinstance(key, str) for key in raw):
        raise ValidationError(f"{path} 根节点键必须都是字符串")
    return raw


def load_yaml_mapping(path: Path) -> dict[str, object]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError(f"{path} 根节点必须是 mapping")
    if not all(isinstance(key, str) for key in raw):
        raise ValidationError(f"{path} 根节点键必须都是字符串")
    return raw


def require_mapping(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValidationError(f"{path} 必须是 mapping")
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValidationError(f"{path} 的键必须是字符串")
        normalized[key] = item
    return normalized


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


def require_str_list(value: object, path: str) -> list[str]:
    items = require_list(value, path)
    result: list[str] = []
    for index, item in enumerate(items):
        result.append(require_non_empty_str(item, f"{path}[{index}]"))
    return result


def load_validator(
    path: Path,
) -> tuple[dict[str, object], jsonschema.Draft202012Validator]:
    schema = load_json_mapping(path)
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema, jsonschema.Draft202012Validator(schema)


def task_types_from_request_schema(request_schema: dict[str, object]) -> set[str]:
    properties = require_mapping(
        request_schema.get("properties"), "router-request.properties"
    )
    task_type = require_mapping(
        properties.get("task_type"), "router-request.properties.task_type"
    )
    enum_values = require_list(
        task_type.get("enum"), "router-request.properties.task_type.enum"
    )
    task_types: set[str] = set()
    for index, item in enumerate(enum_values):
        task_types.add(
            require_non_empty_str(
                item, f"router-request.properties.task_type.enum[{index}]"
            )
        )
    return task_types


def model_provider_map(model_catalog: dict[str, object]) -> dict[str, str]:
    providers = require_mapping(
        model_catalog.get("providers"), "model-catalog.providers"
    )
    models = require_mapping(model_catalog.get("models"), "model-catalog.models")

    provider_names = set(providers)
    if not provider_names:
        raise ValidationError("model-catalog.providers 不能为空")

    mapping: dict[str, str] = {}
    for model_name, raw_model in models.items():
        model = require_mapping(raw_model, f"model-catalog.models.{model_name}")
        provider_name = require_non_empty_str(
            model.get("provider"),
            f"model-catalog.models.{model_name}.provider",
        )
        if provider_name not in provider_names:
            raise ValidationError(
                f"model-catalog.models.{model_name}.provider 引用了未知 provider: {provider_name}"
            )
        mapping[model_name] = provider_name

    return mapping


def validate_contract_examples(
    request_validator: jsonschema.Draft202012Validator,
    decision_validator: jsonschema.Draft202012Validator,
    tool_result_validator: jsonschema.Draft202012Validator,
) -> list[str]:
    errors: list[str] = []
    request_example: dict[str, object] = {
        "trace_id": "trace-router-001",
        "entrypoint": "ljwx_chat",
        "channel": "web",
        "task_type": "knowledge_qa",
        "requires_tools": True,
        "requires_retrieval": True,
        "latency_budget_ms": 8000,
        "messages": [
            {"role": "user", "content": "请给我总结产品上线风险，并引用知识库条目。"},
        ],
        "context_meta": {"tenant": "default"},
    }
    decision_example: dict[str, object] = {
        "trace_id": "trace-router-001",
        "route_id": "knowledge_qa",
        "entrypoint": "ljwx_chat",
        "selected_provider": "anthropic",
        "selected_model": "claude-sonnet-4.6",
        "fallback_reason": "provider_error_or_timeout",
        "tool_plan": ["kb.search"],
        "dataset_scopes": ["public", "internal"],
        "fallback": {
            "provider": "anthropic",
            "model": "claude-sonnet-4.6",
            "condition": "provider_error_or_timeout",
        },
        "citations": [
            {
                "kind": "chunk",
                "document_id": "kb-2026-03-routing",
                "chunk_id": "chunk-0007",
                "uri": "kb://routing/2026-03#chunk-0007",
            }
        ],
        "decision_basis": {
            "matched_rules": ["knowledge_qa"],
            "reasons": ["requires_retrieval=true", "knowledge route selected"],
            "skipped_tools": [],
        },
    }
    tool_result_example: dict[str, object] = {
        "trace_id": "trace-router-001",
        "route_id": "knowledge_qa",
        "tool_name": "kb.search",
        "success": True,
        "data": {"hits": 3},
        "error": None,
        "meta": {
            "audit_event_id": "audit-20260307-001",
            "mock": False,
        },
    }

    for name, validator, payload in (
        ("router-request", request_validator, request_example),
        ("router-decision", decision_validator, decision_example),
        ("tool-result", tool_result_validator, tool_result_example),
    ):
        try:
            validator.validate(payload)
        except jsonschema.ValidationError as exc:
            errors.append(f"{name} 示例不符合 schema: {exc.message}")

    return errors


def validate_route_entrypoints(route: dict[str, object], path: str) -> list[str]:
    errors: list[str] = []
    raw_entrypoints = route.get("entrypoints")
    if raw_entrypoints is None:
        return errors

    try:
        entrypoints = require_mapping(raw_entrypoints, f"{path}.entrypoints")
    except ValidationError as exc:
        return [str(exc)]

    for entrypoint_name, raw_entrypoint in entrypoints.items():
        try:
            require_non_empty_str(entrypoint_name, f"{path}.entrypoints key")
            entrypoint = require_mapping(
                raw_entrypoint,
                f"{path}.entrypoints.{entrypoint_name}",
            )
            transport = require_non_empty_str(
                entrypoint.get("transport"),
                f"{path}.entrypoints.{entrypoint_name}.transport",
            )
            if transport not in ALLOWED_TRANSPORTS:
                errors.append(
                    f"{path}.entrypoints.{entrypoint_name}.transport 非法: {transport}"
                )
            visible_models = require_str_list(
                entrypoint.get("visible_models"),
                f"{path}.entrypoints.{entrypoint_name}.visible_models",
            )
            if not visible_models:
                errors.append(
                    f"{path}.entrypoints.{entrypoint_name}.visible_models 不能为空"
                )
        except ValidationError as exc:
            errors.append(str(exc))

    return errors


def validate_routing_file(
    path: Path,
    expected_task_types: set[str],
    models: dict[str, str],
) -> tuple[str | None, list[str]]:
    errors: list[str] = []

    try:
        payload = load_yaml_mapping(path)
        version = require_non_empty_str(payload.get("version"), f"{path}.version")
        default_route = require_non_empty_str(
            payload.get("default_route"),
            f"{path}.default_route",
        )
        routes = require_list(payload.get("routes"), f"{path}.routes")
    except ValidationError as exc:
        return None, [str(exc)]

    route_ids: set[str] = set()
    seen_task_types: set[str] = set()
    for index, raw_route in enumerate(routes):
        route_path = f"{path}.routes[{index}]"
        try:
            route = require_mapping(raw_route, route_path)
            route_id = require_non_empty_str(route.get("id"), f"{route_path}.id")
            if route_id in route_ids:
                errors.append(f"{route_path}.id 重复: {route_id}")
            else:
                route_ids.add(route_id)

            match = require_mapping(route.get("match"), f"{route_path}.match")
            task_type = require_non_empty_str(
                match.get("task_type"),
                f"{route_path}.match.task_type",
            )
            if task_type not in expected_task_types:
                errors.append(
                    f"{route_path}.match.task_type 不在 request schema 中: {task_type}"
                )
            elif task_type in seen_task_types:
                errors.append(f"{route_path}.match.task_type 重复: {task_type}")
            else:
                seen_task_types.add(task_type)

            for section_name in ("primary", "fallback"):
                section = require_mapping(
                    route.get(section_name), f"{route_path}.{section_name}"
                )
                provider = require_non_empty_str(
                    section.get("provider"),
                    f"{route_path}.{section_name}.provider",
                )
                model = require_non_empty_str(
                    section.get("model"),
                    f"{route_path}.{section_name}.model",
                )
                expected_provider = models.get(model)
                if expected_provider is None:
                    errors.append(
                        f"{route_path}.{section_name}.model 未在 model-catalog 中定义: {model}"
                    )
                elif expected_provider != provider:
                    errors.append(
                        f"{route_path}.{section_name} provider/model 不匹配: {provider} != {expected_provider}"
                    )

            fallback = require_mapping(route.get("fallback"), f"{route_path}.fallback")
            require_non_empty_str(
                fallback.get("condition"),
                f"{route_path}.fallback.condition",
            )

            tool_policy = require_non_empty_str(
                route.get("tool_policy"),
                f"{route_path}.tool_policy",
            )
            if tool_policy not in ALLOWED_TOOL_POLICIES:
                errors.append(f"{route_path}.tool_policy 非法: {tool_policy}")

            dataset_scopes = route.get("dataset_scopes")
            if dataset_scopes is not None:
                scope_list = require_str_list(
                    dataset_scopes, f"{route_path}.dataset_scopes"
                )
                if not scope_list:
                    errors.append(f"{route_path}.dataset_scopes 不能为空")

            approval_gate = optional_non_empty_str(
                route.get("approval_gate"),
                f"{route_path}.approval_gate",
            )
            if approval_gate is not None and tool_policy != "capability_registry":
                errors.append(
                    f"{route_path}.approval_gate 只能用于 capability_registry 路由"
                )

            errors.extend(validate_route_entrypoints(route, route_path))
        except ValidationError as exc:
            errors.append(str(exc))

    if default_route not in route_ids:
        errors.append(f"{path}.default_route 未在 routes.id 中定义: {default_route}")

    missing_task_types = sorted(expected_task_types - seen_task_types)
    if missing_task_types:
        errors.append(
            f"{path} 缺少 task_type 路由覆盖: {', '.join(missing_task_types)}"
        )

    return version, errors


def validate_release_version_reference(
    path: Path,
    route_versions: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    try:
        payload = load_yaml_mapping(path)
        config_versions = require_mapping(
            payload.get("config_versions"),
            f"{path}.config_versions",
        )
        routing_rules = require_non_empty_str(
            config_versions.get("routing_rules"),
            f"{path}.config_versions.routing_rules",
        )
    except ValidationError as exc:
        return [str(exc)]

    if "@" not in routing_rules:
        return [f"{path}.config_versions.routing_rules 必须使用 path@version 格式"]

    referenced_path, referenced_version = routing_rules.split("@", 1)
    if referenced_path not in route_versions:
        errors.append(
            f"{path}.config_versions.routing_rules 引用了未知路由文件: {referenced_path}"
        )
        return errors

    actual_version = route_versions[referenced_path]
    if referenced_version != actual_version:
        errors.append(
            f"{path}.config_versions.routing_rules 版本不匹配: {referenced_version} != {actual_version}"
        )

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate router contracts and routing YAML consistency"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.root.resolve()

    request_schema, request_validator = load_validator(
        repo_root / SCHEMA_DIR / "router-request.schema.json"
    )
    _, decision_validator = load_validator(
        repo_root / SCHEMA_DIR / "router-decision.schema.json"
    )
    _, tool_result_validator = load_validator(
        repo_root / SCHEMA_DIR / "tool-result.schema.json"
    )

    all_errors = validate_contract_examples(
        request_validator=request_validator,
        decision_validator=decision_validator,
        tool_result_validator=tool_result_validator,
    )

    task_types = task_types_from_request_schema(request_schema)
    model_catalog = load_yaml_mapping(repo_root / ROUTING_DIR / "model-catalog.yaml")
    models = model_provider_map(model_catalog)

    route_versions: dict[str, str] = {}
    for relative_path in ROUTING_FILES:
        version, errors = validate_routing_file(
            repo_root / relative_path,
            expected_task_types=task_types,
            models=models,
        )
        if version is not None:
            route_versions[relative_path.as_posix()] = version
        all_errors.extend(errors)

    all_errors.extend(
        validate_release_version_reference(
            repo_root / RELEASE_VERSION_FILE,
            route_versions=route_versions,
        )
    )

    if all_errors:
        print("router contract 校验失败:")
        for message in all_errors:
            print(f"- {message}")
        return 1

    print("router contract 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

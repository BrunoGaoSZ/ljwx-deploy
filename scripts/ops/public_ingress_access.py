#!/usr/bin/env python3
"""Probe live public ingress endpoints and manage local hosts mappings."""

from __future__ import annotations

import argparse
import ipaddress
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BEGIN_MARKER = "# BEGIN ljwx-public-ingress-hosts"
END_MARKER = "# END ljwx-public-ingress-hosts"


@dataclass(frozen=True, slots=True)
class HostRoute:
    """Live ingress route for one host."""

    host: str
    sources: tuple[str, ...]
    addresses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Probe outcome for one host."""

    host: str
    sources: tuple[str, ...]
    selected_address: str
    attempted_addresses: tuple[str, ...]
    http_status: int | None
    reachable: bool
    success: bool
    used_local_address: bool
    detail: str


def ensure_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f"缺少必需命令: {name}")
    return path


def unique_preserve(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return tuple(ordered)


def run_checked_command(command: list[str], timeout_seconds: int) -> str:
    try:
        proc = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        joined = " ".join(command)
        raise SystemExit(f"命令执行超时: {joined}") from exc
    except subprocess.CalledProcessError as exc:
        stderr_text = exc.stderr.strip()
        joined = " ".join(command)
        message = f"命令执行失败: {joined}"
        if stderr_text:
            message = f"{message}\n{stderr_text}"
        raise SystemExit(message) from exc
    except OSError as exc:
        joined = " ".join(command)
        raise SystemExit(f"无法执行命令: {joined}\n{exc}") from exc
    return proc.stdout


def parse_json_object(raw_text: str, command_name: str) -> dict[str, object]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{command_name} 输出不是合法 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{command_name} 输出不是对象")
    return payload


def mapping_of(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def list_of(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def text_of(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def is_ip_literal(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    if path.startswith("/"):
        return path
    return f"/{path}"


def join_sources(sources: tuple[str, ...]) -> str:
    return ",".join(sources)


def routes_from_payload(payload: dict[str, object]) -> list[HostRoute]:
    items = list_of(payload.get("items"))

    routes_by_host: dict[str, tuple[list[str], list[str]]] = {}
    for item_obj in items:
        item = mapping_of(item_obj)
        metadata = mapping_of(item.get("metadata"))
        namespace = text_of(metadata.get("namespace"))
        name = text_of(metadata.get("name"))
        if not namespace or not name:
            continue

        source = f"{namespace}/{name}"
        spec = mapping_of(item.get("spec"))
        rules = list_of(spec.get("rules"))
        hosts: list[str] = []
        for rule_obj in rules:
            rule = mapping_of(rule_obj)
            host = text_of(rule.get("host"))
            if host:
                hosts.append(host)

        status = mapping_of(item.get("status"))
        load_balancer = mapping_of(status.get("loadBalancer"))
        ingress_entries = list_of(load_balancer.get("ingress"))
        addresses: list[str] = []
        for ingress_obj in ingress_entries:
            ingress = mapping_of(ingress_obj)
            ip_text = text_of(ingress.get("ip"))
            hostname_text = text_of(ingress.get("hostname"))
            if ip_text:
                addresses.append(ip_text)
            elif hostname_text:
                addresses.append(hostname_text)

        for host in hosts:
            source_list, address_list = routes_by_host.setdefault(host, ([], []))
            source_list.append(source)
            address_list.extend(addresses)

    routes: list[HostRoute] = []
    for host in sorted(routes_by_host):
        source_list, address_list = routes_by_host[host]
        routes.append(
            HostRoute(
                host=host,
                sources=unique_preserve(source_list),
                addresses=unique_preserve(address_list),
            )
        )

    return routes


def load_live_routes(timeout_seconds: int) -> list[HostRoute]:
    ensure_binary("kubectl")
    raw_json = run_checked_command(
        ["kubectl", "get", "ingress", "-A", "-o", "json"], timeout_seconds
    )
    payload = parse_json_object(raw_json, "kubectl get ingress")
    return routes_from_payload(payload)


def load_routes_from_file(path: Path) -> list[HostRoute]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"ingress JSON 文件不存在: {path}") from exc
    except OSError as exc:
        raise SystemExit(f"读取 ingress JSON 文件失败: {path}\n{exc}") from exc

    payload = parse_json_object(raw_text, str(path))
    return routes_from_payload(payload)


def collect_local_ip_addresses(
    timeout_seconds: int,
    extra_local_ips: tuple[str, ...],
) -> set[str]:
    local_ips = {item for item in extra_local_ips if item}
    local_ips.add("127.0.0.1")
    local_ips.add("::1")

    ensure_binary("hostname")
    try:
        raw_text = run_checked_command(["hostname", "-I"], timeout_seconds)
    except SystemExit:
        if not extra_local_ips:
            print(
                "警告: 无法自动探测本机 IP；如需避开公网回环，请显式传入 --local-ip",
                file=sys.stderr,
            )
        return local_ips

    local_ips.update(item for item in raw_text.split() if item)
    return local_ips


def resolve_address_candidates(address: str, timeout_seconds: int) -> tuple[str, ...]:
    if is_ip_literal(address):
        return (address,)

    ensure_binary("getent")
    raw_text = run_checked_command(["getent", "ahostsv4", address], timeout_seconds)
    resolved: list[str] = []
    for line in raw_text.splitlines():
        parts = line.split()
        if not parts:
            continue
        ip_text = parts[0].strip()
        if is_ip_literal(ip_text):
            resolved.append(ip_text)
    return unique_preserve(resolved)


def expand_route_addresses(route: HostRoute, timeout_seconds: int) -> tuple[str, ...]:
    expanded: list[str] = []
    for address in route.addresses:
        expanded.extend(resolve_address_candidates(address, timeout_seconds))
    return unique_preserve(expanded)


def rank_addresses(
    addresses: tuple[str, ...],
    local_ips: set[str],
    prefer_address: str,
    allow_local_address: bool,
) -> tuple[str, ...]:
    ranked: list[str] = []
    if prefer_address and prefer_address in addresses:
        ranked.append(prefer_address)

    remaining = [address for address in addresses if address not in ranked]
    non_local = [address for address in remaining if address not in local_ips]
    local = [address for address in remaining if address in local_ips]

    ranked.extend(non_local)
    if allow_local_address or not ranked:
        ranked.extend(local)

    return unique_preserve(ranked)


def probe_https_endpoint(
    host: str,
    address: str,
    path: str,
    timeout_seconds: int,
) -> tuple[int | None, bool, bool, str]:
    ensure_binary("curl")
    url = f"https://{host}{path}"
    command = [
        "curl",
        "-sS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "--connect-timeout",
        str(timeout_seconds),
        "--max-time",
        str(timeout_seconds),
        "--resolve",
        f"{host}:443:{address}",
        url,
    ]

    try:
        proc = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds + 2,
        )
    except subprocess.TimeoutExpired:
        return None, False, False, "curl 探测超时"
    except OSError as exc:
        return None, False, False, f"无法执行 curl: {exc}"

    status_text = proc.stdout.strip()
    http_status = int(status_text) if status_text.isdigit() else None
    reachable = http_status is not None and 100 <= http_status <= 599
    success = http_status is not None and 200 <= http_status < 500

    if reachable:
        return http_status, True, success, f"HTTP {http_status}"

    stderr_text = proc.stderr.strip()
    if stderr_text:
        return None, False, False, stderr_text
    return None, False, False, f"curl 返回退出码 {proc.returncode}"


def select_targets(
    routes: list[HostRoute],
    requested_hosts: tuple[str, ...],
    include_local_hosts: bool,
) -> list[HostRoute]:
    if requested_hosts:
        route_map = {route.host: route for route in routes}
        selected: list[HostRoute] = []
        missing: list[str] = []
        for host in requested_hosts:
            route = route_map.get(host)
            if route is None:
                missing.append(host)
                continue
            selected.append(route)
        if missing:
            raise SystemExit(f"集群中未找到这些 Ingress host: {', '.join(missing)}")
        return selected

    selected_routes: list[HostRoute] = []
    for route in routes:
        if route.host.endswith(".local") and not include_local_hosts:
            continue
        selected_routes.append(route)

    if not selected_routes:
        raise SystemExit("未找到可用的公网 Ingress host")

    return selected_routes


def probe_route(
    route: HostRoute,
    local_ips: set[str],
    prefer_address: str,
    allow_local_address: bool,
    timeout_seconds: int,
    path: str,
) -> ProbeResult:
    expanded_addresses = expand_route_addresses(route, timeout_seconds)
    ranked_addresses = rank_addresses(
        expanded_addresses,
        local_ips,
        prefer_address,
        allow_local_address,
    )

    if not ranked_addresses:
        return ProbeResult(
            host=route.host,
            sources=route.sources,
            selected_address="",
            attempted_addresses=(),
            http_status=None,
            reachable=False,
            success=False,
            used_local_address=False,
            detail="未找到可用的 Ingress 地址",
        )

    attempted: list[str] = []
    last_detail = ""
    for address in ranked_addresses:
        attempted.append(address)
        http_status, reachable, success, detail = probe_https_endpoint(
            route.host,
            address,
            path,
            timeout_seconds,
        )
        last_detail = detail
        if reachable:
            return ProbeResult(
                host=route.host,
                sources=route.sources,
                selected_address=address,
                attempted_addresses=tuple(attempted),
                http_status=http_status,
                reachable=reachable,
                success=success,
                used_local_address=address in local_ips,
                detail=detail,
            )

    fallback_address = ranked_addresses[0]
    return ProbeResult(
        host=route.host,
        sources=route.sources,
        selected_address=fallback_address,
        attempted_addresses=tuple(attempted),
        http_status=None,
        reachable=False,
        success=False,
        used_local_address=fallback_address in local_ips,
        detail=f"所有候选地址探测失败: {last_detail or '未知错误'}",
    )


def format_probe_line(result: ProbeResult) -> str:
    prefix = "OK" if result.success else "FAIL"
    source_text = join_sources(result.sources)
    suffix_parts = [
        f"{result.host} -> {result.selected_address or 'N/A'}",
        result.detail,
        f"source={source_text}",
    ]
    if result.attempted_addresses:
        suffix_parts.append("attempted=" + ",".join(result.attempted_addresses))
    if result.used_local_address:
        suffix_parts.append("used_local_address=true")
    return f"{prefix}  " + " | ".join(suffix_parts)


def render_hosts_block(results: list[ProbeResult]) -> str:
    grouped: dict[str, list[str]] = {}
    for result in results:
        if not result.selected_address:
            continue
        grouped.setdefault(result.selected_address, []).append(result.host)

    lines = [
        BEGIN_MARKER,
        "# Managed by scripts/ops/public_ingress_access.py",
    ]
    for address in sorted(grouped):
        hosts = sorted(set(grouped[address]))
        lines.append(f"{address} {' '.join(hosts)}")
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def replace_managed_block(existing_text: str, managed_block: str) -> str:
    start_index = existing_text.find(BEGIN_MARKER)
    end_index = existing_text.find(END_MARKER)

    if (start_index == -1) != (end_index == -1):
        raise SystemExit("hosts 文件中的受管标记不完整，请先手工修复")

    if start_index != -1 and end_index != -1:
        end_line_index = existing_text.find("\n", end_index)
        if end_line_index == -1:
            end_line_index = len(existing_text)
        else:
            end_line_index += 1

        before = existing_text[:start_index].rstrip("\n")
        after = existing_text[end_line_index:].lstrip("\n")
        parts = [part for part in (before, managed_block.rstrip("\n"), after) if part]
        return "\n\n".join(parts) + "\n"

    stripped = existing_text.rstrip("\n")
    if not stripped:
        return managed_block
    return stripped + "\n\n" + managed_block


def write_text_file(path: Path, content: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except PermissionError as exc:
        raise SystemExit(f"没有权限写入文件: {path}") from exc
    except OSError as exc:
        raise SystemExit(f"写入文件失败: {path}\n{exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 live Ingress 选择稳定地址，探测本机公网域名访问并生成 hosts 映射"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe_parser = subparsers.add_parser("probe", help="探测一个或多个公网 host")
    probe_parser.add_argument("--host", action="append", default=[])
    probe_parser.add_argument("--include-local-hosts", action="store_true")
    probe_parser.add_argument("--prefer-address", default="")
    probe_parser.add_argument("--allow-local-address", action="store_true")
    probe_parser.add_argument("--local-ip", action="append", default=[])
    probe_parser.add_argument("--path", default="/")
    probe_parser.add_argument("--timeout", type=int, default=5)
    probe_parser.add_argument("--ingress-json", type=Path)

    hosts_parser = subparsers.add_parser(
        "hosts",
        help="生成或写入推荐的 hosts 映射",
    )
    hosts_parser.add_argument("--host", action="append", default=[])
    hosts_parser.add_argument("--include-local-hosts", action="store_true")
    hosts_parser.add_argument("--prefer-address", default="")
    hosts_parser.add_argument("--allow-local-address", action="store_true")
    hosts_parser.add_argument("--local-ip", action="append", default=[])
    hosts_parser.add_argument("--path", default="/")
    hosts_parser.add_argument("--timeout", type=int, default=5)
    hosts_parser.add_argument("--ingress-json", type=Path)
    hosts_parser.add_argument("--out", type=Path)
    hosts_parser.add_argument("--apply", action="store_true")
    hosts_parser.add_argument("--hosts-file", type=Path, default=Path("/etc/hosts"))

    return parser


def validate_timeout(timeout_seconds: int) -> int:
    if timeout_seconds < 1:
        raise SystemExit("timeout 必须是正整数")
    return timeout_seconds


def collect_probe_results(args: argparse.Namespace) -> list[ProbeResult]:
    timeout_seconds = validate_timeout(int(args.timeout))
    prefer_address = str(args.prefer_address).strip()
    path = normalize_path(str(args.path).strip())
    requested_hosts = unique_preserve([str(host).strip() for host in args.host if host])
    extra_local_ips = unique_preserve(
        [str(ip_text).strip() for ip_text in args.local_ip if ip_text]
    )

    routes = (
        load_routes_from_file(Path(args.ingress_json))
        if args.ingress_json
        else load_live_routes(timeout_seconds)
    )
    selected_routes = select_targets(
        routes,
        requested_hosts,
        bool(args.include_local_hosts),
    )
    local_ips = collect_local_ip_addresses(timeout_seconds, extra_local_ips)

    return [
        probe_route(
            route=route,
            local_ips=local_ips,
            prefer_address=prefer_address,
            allow_local_address=bool(args.allow_local_address),
            timeout_seconds=timeout_seconds,
            path=path,
        )
        for route in selected_routes
    ]


def handle_probe(args: argparse.Namespace) -> int:
    results = collect_probe_results(args)
    print("探测结果:")
    for result in results:
        print(format_probe_line(result))

    failed_hosts = [result.host for result in results if not result.success]
    if failed_hosts:
        print(f"探测失败 host: {', '.join(failed_hosts)}")
        return 1
    return 0


def handle_hosts(args: argparse.Namespace) -> int:
    results = collect_probe_results(args)
    usable_results = [result for result in results if result.selected_address]
    if not usable_results:
        raise SystemExit("没有可写入 hosts 的地址")

    warning_hosts = [result.host for result in usable_results if not result.reachable]
    if warning_hosts:
        print(
            "警告: 以下 host 尚未探测成功，已按推荐地址生成映射: "
            + ", ".join(warning_hosts)
        )

    managed_block = render_hosts_block(usable_results)
    if args.out:
        write_text_file(Path(args.out), managed_block)
        print(f"已写入 hosts 片段: {args.out}")

    if args.apply:
        hosts_path = Path(args.hosts_file)
        try:
            existing_text = hosts_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            existing_text = ""
        updated_text = replace_managed_block(existing_text, managed_block)
        write_text_file(hosts_path, updated_text)
        print(f"已更新 hosts 文件: {hosts_path}")

    if not args.out and not args.apply:
        print(managed_block, end="")

    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "probe":
        return handle_probe(args)
    if args.command == "hosts":
        return handle_hosts(args)

    raise SystemExit("不支持的命令")


if __name__ == "__main__":
    raise SystemExit(main())

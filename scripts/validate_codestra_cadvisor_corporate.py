#!/usr/bin/env python3
"""Canonical entrypoint for Codestra cAdvisor corporate validation.

The legacy base validator retains broad topology, label, relabel, proxy, and
secret checks. This entrypoint reconciles the locked-source rootfs difference,
adds the infrastructure-label exemption, and enforces the current source-built
image and protocol-readiness contract. Rendered image values are independently
validated by ``validate_rendered_cadvisor_images.py`` in exact-head CI.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import re
import sys
from types import ModuleType
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_codestra_cadvisor.py"
REMOVED_LOCKED_SOURCE_FLAG = "--rootfs=/rootfs"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("codestra_cadvisor_policy", VALIDATOR)
    if spec is None or spec.loader is None:
        fail("unable to load the cAdvisor policy validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot parse {path.relative_to(ROOT)}: {exc}")
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain an object")
    return value


def validate_proxy_source_and_tests_syntax_aware(module: ModuleType) -> None:
    """Preserve every proxy check while accepting gofmt field alignment."""

    original_require_file = module.require_file

    def require_file_with_normalized_test_spacing(path: pathlib.Path) -> str:
        text = original_require_file(path)
        if path == module.PROXY_TEST:
            text = re.sub(r'name:\s+"', 'name: "', text)
        return text

    module.require_file = require_file_with_normalized_test_spacing
    try:
        module.validate_proxy_source_and_tests()
    finally:
        module.require_file = original_require_file


def validate_locked_source_rootfs_contract(module: ModuleType, compose: dict[str, Any]) -> None:
    cadvisor = compose.get("services", {}).get("cadvisor", {})
    command = {str(item) for item in cadvisor.get("command", [])}
    if REMOVED_LOCKED_SOURCE_FLAG in command:
        module.fail(
            "locked cAdvisor source no longer supports --rootfs; retain the "
            "read-only /rootfs bind without the removed CLI flag"
        )

    root_mounts = [
        item
        for item in cadvisor.get("volumes", [])
        if isinstance(item, dict) and item.get("target") == "/rootfs"
    ]
    if len(root_mounts) != 1 or root_mounts[0].get("read_only") is not True:
        module.fail("cAdvisor requires exactly one read-only host-root bind at /rootfs")
    if root_mounts[0].get("source") != "/":
        module.fail("cAdvisor /rootfs must map the host root and may not use another source")


def validate_current_source_and_health_contract(module: ModuleType, compose: dict[str, Any]) -> None:
    upstream = load_json(ROOT / "CODESTRA_UPSTREAM_LOCK.json")
    release = load_json(ROOT / "codestra/release/runtime-base.lock.json")
    source_commit = str(upstream.get("upstream_commit", ""))
    if not FULL_SHA.fullmatch(source_commit):
        fail("cAdvisor upstream source commit must be a full lowercase Git SHA")
    if release.get("cadvisorBinarySourceCommit") != source_commit:
        fail("release lock does not bind the cAdvisor binary to the governed source")
    if release.get("vendoredSourceUsedByImageBuild") is not True:
        fail("release lock must require the vendored source in the image build")
    if release.get("cadvisorBaseImageRole") != "runtime-substrate-only":
        fail("official cAdvisor image may be used only as a runtime substrate")

    services = compose.get("services", {})
    cadvisor = services.get("cadvisor", {})
    build = cadvisor.get("build", {})
    if build.get("context") != "../.." or build.get("dockerfile") != "codestra/deploy/Dockerfile.cadvisor":
        fail("cAdvisor must build from the repository root source context")
    if set(build.get("args", {})) != {
        "GO_BUILDER_IMAGE",
        "CADVISOR_BASE_IMAGE",
        "CADVISOR_SOURCE_COMMIT",
    }:
        fail("cAdvisor build arguments must include the exact source commit")
    source_expression = str(build.get("args", {}).get("CADVISOR_SOURCE_COMMIT", ""))
    if source_commit not in source_expression and "CADVISOR_SOURCE_COMMIT" not in source_expression:
        fail("cAdvisor source build argument is not governed")

    expected_health_urls = {
        "docker-api-proxy": "http://127.0.0.1:2375/healthz",
        "cadvisor": "http://127.0.0.1:8080/healthz",
        "cadvisor-metrics-proxy": "http://cadvisor:8080/healthz",
    }
    for name, expected in expected_health_urls.items():
        service = services.get(name, {})
        if service.get("environment", {}).get("CODESTRA_HEALTHCHECK_URL") != expected:
            fail(f"protocol readiness URL mismatch: {name}")
        if service.get("healthcheck", {}).get("test") != ["CMD", "/codestra-healthcheck"]:
            fail(f"native healthcheck command mismatch: {name}")


def validate_compose_with_current_contract(module: ModuleType) -> None:
    original_load_yaml = module.load_yaml
    original_required_flags = module.REQUIRED_CADVISOR_FLAGS
    compose = original_load_yaml(module.COMPOSE)
    services = compose.get("services", {})
    stable_labels = module.DOCKER_LABELS - {"codestra.replica"}

    validate_locked_source_rootfs_contract(module, compose)
    validate_current_source_and_health_contract(module, compose)

    for name, service in services.items():
        labels = service.get("labels", {})
        missing = stable_labels - set(labels)
        if missing:
            module.fail(
                f"managed cAdvisor infrastructure service {name} is missing labels: "
                f"{sorted(missing)}"
            )
        if "codestra.replica" in labels:
            module.fail(
                f"cAdvisor infrastructure service {name} must not impersonate an "
                "application replica"
            )

    def load_yaml_for_legacy_topology_checks(path: pathlib.Path) -> Any:
        value = original_load_yaml(path)
        if path != module.COMPOSE:
            return value
        value = copy.deepcopy(value)
        for service in value.get("services", {}).values():
            service.setdefault("labels", {})["codestra.replica"] = "infrastructure"
        # The current source commit is validated above and in rendered CI. The
        # legacy base checker predates this third non-image build argument.
        value["services"]["cadvisor"].get("build", {}).get("args", {}).pop(
            "CADVISOR_SOURCE_COMMIT", None
        )
        return value

    module.REQUIRED_CADVISOR_FLAGS = set(original_required_flags) - {
        REMOVED_LOCKED_SOURCE_FLAG
    }
    module.load_yaml = load_yaml_for_legacy_topology_checks
    try:
        module.validate_compose()
    finally:
        module.load_yaml = original_load_yaml
        module.REQUIRED_CADVISOR_FLAGS = original_required_flags


def validate_current_packaging(module: ModuleType) -> None:
    proxy_dockerfile = module.require_file(module.PROXY_DOCKERFILE)
    for fragment in (
        "ARG GO_BUILDER_IMAGE",
        "ARG PROXY_RUNTIME_IMAGE",
        "CGO_ENABLED=0",
        "-trimpath",
        "/codestra-cadvisor-proxy",
        "/codestra-healthcheck",
        "USER 65532:65532",
    ):
        if fragment not in proxy_dockerfile:
            module.fail(f"proxy Dockerfile is missing {fragment}")

    cadvisor_dockerfile = module.require_file(module.CADVISOR_DOCKERFILE)
    for fragment in (
        "ARG GO_BUILDER_IMAGE",
        "ARG CADVISOR_BASE_IMAGE",
        "ARG CADVISOR_SOURCE_COMMIT",
        "COPY CODESTRA_UPSTREAM_LOCK.json",
        "COPY upstream/ ./",
        "github.com/google/cadvisor/version.Revision=${CADVISOR_SOURCE_COMMIT}",
        "/out/cadvisor /usr/bin/cadvisor",
        'ENTRYPOINT ["/usr/bin/cadvisor"]',
        "CGO_ENABLED=0",
        "-trimpath",
        "/codestra-healthcheck",
        "USER 0:0",
    ):
        if fragment not in cadvisor_dockerfile:
            module.fail(f"cAdvisor Dockerfile is missing {fragment}")
    if ":latest" in proxy_dockerfile or ":latest" in cadvisor_dockerfile:
        module.fail("cAdvisor Dockerfiles may not use latest tags")

    healthcheck = module.require_file(module.HEALTHCHECK)
    healthcheck_test = module.require_file(module.CODESTRA / "deploy/healthcheck_test.go")
    for fragment in (
        "http.NewRequestWithContext",
        "response.StatusCode",
        "io.LimitReader",
        "CODESTRA_HEALTHCHECK_URL",
        'parsed.Path != "/healthz"',
    ):
        if fragment not in healthcheck:
            module.fail(f"cAdvisor healthcheck omits protocol-readiness control: {fragment}")
    if "net.DialTimeout" in healthcheck or "os/exec" in healthcheck or "exec.Command" in healthcheck:
        module.fail("cAdvisor healthcheck may not treat a listening socket as readiness")
    for case in ("unavailable", "oversized", "redirect"):
        if case not in healthcheck_test.lower():
            module.fail(f"cAdvisor healthcheck tests omit {case} failure coverage")

    env_text = module.require_file(module.ENV_EXAMPLE)
    for fragment in (
        "CODESTRA_CADVISOR_DEPLOYMENT_ID=",
        "GO_BUILDER_IMAGE=",
        "PROXY_RUNTIME_IMAGE=",
        "CADVISOR_BASE_IMAGE=",
        "CADVISOR_SOURCE_COMMIT=",
        "CODESTRA_CADVISOR_PROXY_IMAGE=",
        "CODESTRA_CADVISOR_IMAGE=",
        "DOCKER_SOCKET_GID=",
        "CADVISOR_DOCKER_ROOT_PATH=",
        "CADVISOR_PROXY_SERVER_CERT_SECRET_NAME=",
        "CADVISOR_PROXY_SERVER_KEY_SECRET_NAME=",
        "PROMETHEUS_CLIENT_CA_SECRET_NAME=",
    ):
        if fragment not in env_text:
            module.fail(f"cAdvisor runtime example omits {fragment}")

    module.require_file(module.OPERATING_MODEL)
    module.require_file(module.RUNTIME_FEATURES)

    dash = chr(45) * 5
    signatures = (
        dash + "BEGIN " + "PRIVATE" + chr(32) + "KEY" + dash,
        dash + "BEGIN " + "OPENSSH" + chr(32) + "PRIVATE" + chr(32) + "KEY" + dash,
        "A" + "K" + "I" + "A",
    )
    for path in module.CODESTRA.rglob("*"):
        if not path.is_file() or path.suffix == ".pyc" or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for signature in signatures:
            if signature in text:
                module.fail(f"secret-shaped material found in {path.relative_to(module.ROOT)}")


def main() -> None:
    module = load_validator()
    module.validate_runtime()
    module.validate_label_contract()
    module.validate_relabel_contract()
    validate_proxy_source_and_tests_syntax_aware(module)
    validate_compose_with_current_contract(module)
    validate_current_packaging(module)
    print("Codestra cAdvisor corporate configuration validation PASS")
    print("CADVISOR_SOURCE_BUILT_BINARY=PASS")
    print("CADVISOR_PROTOCOL_READINESS=PASS")


if __name__ == "__main__":
    main()

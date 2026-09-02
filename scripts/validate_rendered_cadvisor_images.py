#!/usr/bin/env python3
"""Validate rendered cAdvisor image and build-argument identities."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

IMAGE = re.compile(r"^[a-z0-9][a-z0-9./_:-]*@sha256:[0-9a-f]{64}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("rendered Compose document must be an object")
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path} must contain an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("compose", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    document = load_yaml(args.compose)
    services = document.get("services")
    if not isinstance(services, dict) or set(services) != {
        "docker-api-proxy",
        "cadvisor",
        "cadvisor-metrics-proxy",
    }:
        fail("rendered service topology mismatch")

    for name, service in services.items():
        if not isinstance(service, dict):
            fail(f"service {name} must be an object")
        image = str(service.get("image", ""))
        if not IMAGE.fullmatch(image):
            fail(f"service {name} image is mutable or malformed: {image!r}")
        build = service.get("build")
        if build is None:
            continue
        if not isinstance(build, dict):
            fail(f"service {name} build must be an object")
        build_args = build.get("args", {})
        if not isinstance(build_args, dict):
            fail(f"service {name} build arguments must be an object")
        for key, value in build_args.items():
            rendered = str(value)
            if key.endswith("_IMAGE") and not IMAGE.fullmatch(rendered):
                fail(f"service {name} build argument {key} is mutable or malformed: {rendered!r}")

    upstream = load_json(args.root / "CODESTRA_UPSTREAM_LOCK.json")
    release = load_json(args.root / "codestra/release/runtime-base.lock.json")
    source_commit = str(
        services["cadvisor"].get("build", {}).get("args", {}).get("CADVISOR_SOURCE_COMMIT", "")
    )
    if not FULL_SHA.fullmatch(source_commit):
        fail("rendered CADVISOR_SOURCE_COMMIT must be a full lowercase Git SHA")
    if source_commit != upstream.get("upstream_commit"):
        fail("rendered cAdvisor source commit does not match CODESTRA_UPSTREAM_LOCK.json")
    if source_commit != release.get("cadvisorBinarySourceCommit"):
        fail("rendered cAdvisor source commit does not match the release source authority")

    print("CADVISOR_RENDERED_IMAGE_IDENTITIES=PASS")
    print(f"CADVISOR_BINARY_SOURCE_COMMIT={source_commit}")


if __name__ == "__main__":
    main()

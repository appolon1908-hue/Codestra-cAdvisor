#!/usr/bin/env python3
"""Canonical entrypoint for Codestra cAdvisor corporate validation.

Managed application containers require a deployment-owned replica label before their
metrics survive Prometheus relabeling. The three exporter/security containers are
not required to become their own monitored application replicas, so Compose checks
require the six stable platform labels while the full external container contract
continues to require `codestra.replica`.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from types import ModuleType

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_codestra_cadvisor.py"


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


def main() -> None:
    module = load_validator()
    module.validate_runtime()
    module.validate_label_contract()
    module.validate_relabel_contract()
    module.validate_proxy_source_and_tests()

    full_contract = module.DOCKER_LABELS
    module.DOCKER_LABELS = full_contract - {"codestra.replica"}
    try:
        module.validate_compose()
    finally:
        module.DOCKER_LABELS = full_contract

    module.validate_packaging_docs_and_secrets()
    print("Codestra cAdvisor corporate configuration validation PASS")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Validate repository-only cAdvisor image release readiness."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE = re.compile(r"^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
AUTHORITY = "appolon1908-hue/Codestra-Telemetry/.github/workflows/reusable-release-image.yml@9a6aebb849bbc068105c10d9d1dfd39ebf6f78bd"
REQUIRED = (
    ".dockerignore",
    ".gitattributes",
    "REPOSITORY_PROFILE.md",
    "SECURITY.md",
    ".github/CODEOWNERS",
    "docs/BACKUP_RESTORE_ROLLBACK.md",
    "docs/UPGRADE.md",
    "codestra/.dockerignore",
    "codestra/deploy/compose.candidate.yaml",
    "codestra/deploy/healthcheck_test.go",
    "codestra/release/runtime-base.lock.json",
    "codestra/release/cadvisor-image-build.v1.json",
    "codestra/release/proxy-image-build.v1.json",
    ".github/workflows/release-images.yml",
    ".github/workflows/upstream-source-sync.yml",
    "requirements-validation.txt",
)
LEGACY = (
    "deploy/compose.yaml",
    "codestra/runtime-v1/compose.yaml",
    "codestra/runtime-v1/compose-codestra.yaml",
    ".github/workflows/validate.yml",
)


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def load(path: str) -> dict:
    value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path} must contain an object")
    return value


def validate() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        fail(f"missing readiness files: {missing}")
    if (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()[-1] != "upstream/** -whitespace":
        fail("vendored upstream whitespace boundary is missing")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    if any(line.strip() in {"upstream", "upstream/", "CODESTRA_UPSTREAM_LOCK.json", "codestra"} for line in dockerignore):
        fail("root Docker context must retain locked source, source lock, and healthcheck input")
    present_legacy = [path for path in LEGACY if (ROOT / path).exists()]
    if present_legacy:
        fail(f"unsafe superseded deployment authority remains: {present_legacy}")

    lock = load("codestra/release/runtime-base.lock.json")
    if lock.get("schemaVersion") != "1.1.0":
        fail("cAdvisor release lock schema must be 1.1.0")
    if lock.get("artifactModel") != "repository-built-signed-images":
        fail("cAdvisor must use Model A")
    for field in ("buildFrontendImage", "builderImage", "cadvisorBaseImage", "proxyRuntimeImage"):
        if not IMAGE.fullmatch(str(lock.get(field, ""))):
            fail(f"mutable build identity: {field}")
    if lock.get("cadvisorBaseImageRole") != "runtime-substrate-only":
        fail("official cAdvisor base image must be runtime substrate only")

    upstream = load("CODESTRA_UPSTREAM_LOCK.json")
    if upstream.get("schema_version") != "1.1":
        fail("upstream lock schema must be 1.1")
    source_commit = str(upstream.get("upstream_commit", ""))
    source_tree = str(upstream.get("imported_tree_sha", ""))
    if not FULL_SHA.fullmatch(source_commit) or not FULL_SHA.fullmatch(source_tree):
        fail("upstream source commit and imported tree must be full Git object IDs")
    imported_tree = subprocess.run(
        ["git", "rev-parse", "HEAD:upstream"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if source_tree != imported_tree:
        fail("vendored source tree identity mismatch")
    expected_source_fields = {
        "vendoredSourceSnapshotCommit": source_commit,
        "vendoredSourceTreeSha": source_tree,
        "cadvisorBinarySourceCommit": source_commit,
        "cadvisorBinaryRevisionReadback": source_commit,
        "vendoredSourceUsedByImageBuild": True,
        "productionActivation": False,
    }
    for field, expected in expected_source_fields.items():
        if lock.get(field) != expected:
            fail(f"runtime source authority mismatch for {field}")

    sync = (ROOT / ".github/workflows/upstream-source-sync.yml").read_text(encoding="utf-8")
    sync_requirements = (
        "git add -A upstream",
        'IMPORTED_TREE_SHA="$(git rev-parse :upstream)"',
        "'schema_version':'1.1'",
        "'imported_tree_sha':os.environ['IMPORTED_TREE_SHA']",
        'test "$(git rev-parse :upstream)" = "$(python3 -c',
    )
    for requirement in sync_requirements:
        if requirement not in sync:
            fail(f"upstream sync omits tree-lock control: {requirement}")
    if "'schema_version':'1.0'" in sync:
        fail("upstream sync would regress the generated lock schema")

    manifests = {
        "cadvisor": load("codestra/release/cadvisor-image-build.v1.json"),
        "cadvisor-proxy": load("codestra/release/proxy-image-build.v1.json"),
    }
    expected_args = {
        "cadvisor": {
            "CADVISOR_BASE_IMAGE": lock["cadvisorBaseImage"],
            "CADVISOR_SOURCE_COMMIT": source_commit,
            "GO_BUILDER_IMAGE": lock["builderImage"],
        },
        "cadvisor-proxy": {
            "GO_BUILDER_IMAGE": lock["builderImage"],
            "PROXY_RUNTIME_IMAGE": lock["proxyRuntimeImage"],
        },
    }
    expected_context = {"cadvisor": ".", "cadvisor-proxy": "codestra"}
    for image_id, manifest in manifests.items():
        if manifest.get("schemaVersion") != "1.0.0" or manifest.get("imageId") != image_id:
            fail(f"image manifest identity mismatch: {image_id}")
        if manifest.get("context") != expected_context[image_id] or manifest.get("buildArgs") != expected_args[image_id]:
            fail(f"image manifest context/build arguments mismatch: {image_id}")
        if manifest.get("productionActivation") is not False:
            fail(f"image manifest activates production: {image_id}")
        dockerfile = (ROOT / manifest["dockerfile"]).read_text(encoding="utf-8")
        if dockerfile.splitlines()[0] != f"# syntax={lock['buildFrontendImage']}":
            fail(f"frontend mismatch: {image_id}")
        declared = set(re.findall(r"(?m)^ARG\s+([A-Z][A-Z0-9_]*)$", dockerfile))
        if declared != set(manifest["buildArgs"]):
            fail(f"Dockerfile arguments mismatch: {image_id}: {sorted(declared)}")

    cadvisor_dockerfile = (ROOT / "codestra/deploy/Dockerfile.cadvisor").read_text(encoding="utf-8")
    for required in (
        "COPY upstream/go.mod upstream/go.sum ./",
        "COPY upstream/ ./",
        "COPY CODESTRA_UPSTREAM_LOCK.json",
        "github.com/google/cadvisor/version.Revision=${CADVISOR_SOURCE_COMMIT}",
        "/out/cadvisor /usr/bin/cadvisor",
        'ENTRYPOINT ["/usr/bin/cadvisor"]',
    ):
        if required not in cadvisor_dockerfile:
            fail(f"cAdvisor image does not prove source-built binary packaging: {required}")

    compose = yaml.safe_load((ROOT / "codestra/deploy/compose.candidate.yaml").read_text(encoding="utf-8"))
    services = compose.get("services", {})
    if set(services) != {"docker-api-proxy", "cadvisor", "cadvisor-metrics-proxy"}:
        fail("topology mismatch")
    for name, service in services.items():
        if service.get("privileged") is True or service.get("network_mode") == "host" or service.get("pid") == "host" or service.get("ports"):
            fail(f"unsafe runtime boundary: {name}")
    if services["docker-api-proxy"].get("build", {}).get("context") != "..":
        fail("proxy build context mismatch")
    cadvisor_build = services["cadvisor"].get("build", {})
    if cadvisor_build.get("context") != "../.." or cadvisor_build.get("dockerfile") != "codestra/deploy/Dockerfile.cadvisor":
        fail("cAdvisor build must use the repository root source context")
    if set(cadvisor_build.get("args", {})) != {"GO_BUILDER_IMAGE", "CADVISOR_BASE_IMAGE", "CADVISOR_SOURCE_COMMIT"}:
        fail("cAdvisor Compose build arguments must include the exact source commit")
    expected_health_urls = {
        "docker-api-proxy": "http://127.0.0.1:2375/healthz",
        "cadvisor": "http://127.0.0.1:8080/healthz",
        "cadvisor-metrics-proxy": "http://cadvisor:8080/healthz",
    }
    for service, expected in expected_health_urls.items():
        if services[service].get("environment", {}).get("CODESTRA_HEALTHCHECK_URL") != expected:
            fail(f"protocol readiness URL mismatch: {service}")
        if services[service].get("healthcheck", {}).get("test") != ["CMD", "/codestra-healthcheck"]:
            fail(f"native healthcheck command mismatch: {service}")

    release = yaml.safe_load((ROOT / ".github/workflows/release-images.yml").read_text(encoding="utf-8"))
    jobs = release.get("jobs", {})
    expected_jobs = {"release-cadvisor": "cadvisor", "release-proxy": "cadvisor-proxy"}
    for job_name, image_id in expected_jobs.items():
        job = jobs.get(job_name, {})
        if job.get("uses") != AUTHORITY or job.get("with", {}).get("image_id") != image_id:
            fail(f"release authority mismatch: {job_name}")
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
        for ref in re.findall(r"(?m)^\s*(?:-\s*)?uses:\s*([^\s#]+)", workflow.read_text(encoding="utf-8")):
            if not ref.startswith("./") and not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", ref):
                fail(f"mutable action reference: {workflow.name}: {ref}")


def main() -> None:
    validate()
    print("CADVISOR_REPOSITORY_READINESS_SOURCE=PASS")
    print("CADVISOR_BINARY_SOURCE_BOUND=PASS")
    print("SIGNED_IMAGES=2")
    print("PRODUCTION_ACTIVATION=NO")


if __name__ == "__main__":
    main()

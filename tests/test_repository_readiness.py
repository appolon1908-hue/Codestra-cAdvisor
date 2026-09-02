from __future__ import annotations
import json, subprocess, unittest
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[1]
class ReadinessTests(unittest.TestCase):
    def test_validator(self) -> None:
        subprocess.run(["python3", "scripts/validate_repository_readiness.py"], cwd=ROOT, check=True)
    def test_two_release_jobs_are_structurally_pinned(self) -> None:
        workflow = yaml.safe_load((ROOT / ".github/workflows/release-images.yml").read_text())
        jobs = workflow["jobs"]
        self.assertEqual(jobs["release-cadvisor"]["with"]["image_id"], "cadvisor")
        self.assertEqual(jobs["release-proxy"]["with"]["image_id"], "cadvisor-proxy")
        for name in ("release-cadvisor", "release-proxy"):
            self.assertTrue(jobs[name]["uses"].endswith("@9a6aebb849bbc068105c10d9d1dfd39ebf6f78bd"))
    def test_base_lock_and_manifests_agree(self) -> None:
        lock = json.loads((ROOT / "codestra/release/runtime-base.lock.json").read_text())
        cadvisor = json.loads((ROOT / "codestra/release/cadvisor-image-build.v1.json").read_text())
        proxy = json.loads((ROOT / "codestra/release/proxy-image-build.v1.json").read_text())
        self.assertEqual(cadvisor["buildArgs"]["CADVISOR_BASE_IMAGE"], lock["cadvisorBaseImage"])
        self.assertEqual(proxy["buildArgs"]["PROXY_RUNTIME_IMAGE"], lock["proxyRuntimeImage"])
        self.assertEqual(lock["cadvisorBinaryRevisionReadback"], lock["cadvisorUpstreamTagCommit"][:7])
    def test_legacy_unsafe_manifests_are_absent(self) -> None:
        for relative in ("deploy/compose.yaml", "codestra/runtime-v1/compose.yaml", "codestra/runtime-v1/compose-codestra.yaml"):
            self.assertFalse((ROOT / relative).exists())
    def test_vendored_upstream_is_byte_preserved(self) -> None:
        self.assertEqual((ROOT / ".gitattributes").read_text().splitlines()[-1], "upstream/** -whitespace")
if __name__ == "__main__": unittest.main()

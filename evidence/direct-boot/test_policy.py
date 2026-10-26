from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import apt_guard
import guest_bootstrap
import host_controller
import policy


class DirectBootPolicyTests(unittest.TestCase):
    def boot_document(self):
        return {
            "schema": "dm-direct-boot-config-v1",
            "nonce": "a" * 32,
            "base_sha256": "b" * 64,
            "guest_source_sha256": "c" * 64,
            "seed_sha256": "d" * 64,
            "overlay_initial_sha256": "e" * 64,
            "argv_template": ["qemu", "-fw_cfg", "string=<CONFIG_BINDING>"],
            "machine": "pc,accel=tcg",
            "memory_mib": 2048,
            "cpus": 2,
        }

    def guest_result(self):
        release = "6.8.0-test"
        paths = [
            "/usr/bin/python3", "/usr/bin/cloud-init", "/usr/bin/dpkg-query", "/usr/bin/systemctl", "/usr/bin/sha256sum",
            "/boot/vmlinuz-" + release, "/boot/config-" + release,
        ]
        tools = [
            {"requested": path, "resolved": path, "sha256": "2" * 64, "bytes": 123, "mode": 0o755, "owner": {"package": "example", "version": "1"}}
            for path in paths
        ]
        return {
            "schema": "dm-direct-boot-result-v1",
            "result": "measured",
            "scope": "offline-bootstrap-only-no-product-no-g0",
            "nonce": "a" * 32,
            "binding": "f" * 64,
            "source_sha256": "c" * 64,
            "uname": ["Linux", "guest", release, "build", "x86_64"],
            "uid": 0,
            "gid": 0,
            "python": "3.12",
            "cmdline_sha256": "1" * 64,
            "tools": tools,
        }

    def frame(self, result=None):
        payload = policy.canonical(result or self.guest_result())
        return b"boot noise\nDMFRAME3 " + str(len(payload)).encode() + b" " + policy.sha_bytes(payload).encode() + b" " + payload + b"\n"

    def test_binding_changes_with_seed_and_has_one_placeholder(self):
        first = self.boot_document()
        second = dict(first, seed_sha256="9" * 64)
        self.assertNotEqual(policy.boot_binding(first), policy.boot_binding(second))
        with self.assertRaises(ValueError):
            policy.boot_binding(dict(first, argv_template=["qemu"]))

    def test_guest_frame_requires_one_exact_config_bound_result(self):
        parsed = policy.parse_frame(self.frame(), nonce="a" * 32, binding="f" * 64, guest_source_sha256="c" * 64)
        self.assertEqual(parsed["result"], "measured")
        with self.assertRaises(ValueError):
            policy.parse_frame(self.frame() * 2, nonce="a" * 32, binding="f" * 64, guest_source_sha256="c" * 64)
        damaged = bytearray(self.frame()); damaged[-3] ^= 1
        with self.assertRaises(ValueError):
            policy.parse_frame(bytes(damaged), nonce="a" * 32, binding="f" * 64, guest_source_sha256="c" * 64)
        empty = self.guest_result(); empty["tools"] = []
        with self.assertRaises(ValueError):
            policy.parse_frame(self.frame(empty), nonce="a" * 32, binding="f" * 64, guest_source_sha256="c" * 64)

    def test_qcow_policy_rejects_backing_data_encryption_snapshots_and_oversize(self):
        base = Path("/private/base.qcow2")
        valid = {
            "virtual-size": 3 * policy.GIB,
            "filename": str(base),
            "format": "qcow2",
            "actual-size": 700 * policy.MIB,
            "format-specific": {"type": "qcow2", "data": {"compat": "1.1", "compression-type": "zlib", "lazy-refcounts": False, "refcount-bits": 16, "corrupt": False, "extended-l2": False}},
        }
        self.assertEqual(policy.validate_qemu_img_info(valid, base_path=base, physical_size=700 * policy.MIB)["format"], "qcow2")
        for key in ("backing-filename", "data-file", "encrypt"):
            bad = json.loads(json.dumps(valid)); bad["format-specific"]["data"][key] = "x"
            with self.assertRaises(ValueError, msg=key):
                policy.validate_qemu_img_info(bad, base_path=base, physical_size=700 * policy.MIB)
        with self.assertRaises(ValueError):
            policy.validate_qemu_img_info(dict(valid, snapshots=[{}]), base_path=base, physical_size=700 * policy.MIB)
        nested_corrupt = json.loads(json.dumps(valid)); nested_corrupt["format-specific"]["data"]["corrupt"] = True
        with self.assertRaises(ValueError):
            policy.validate_qemu_img_info(nested_corrupt, base_path=base, physical_size=700 * policy.MIB)
        for feature, bad_value in (("lazy-refcounts", True), ("extended-l2", True), ("refcount-bits", 32)):
            unsupported = json.loads(json.dumps(valid)); unsupported["format-specific"]["data"][feature] = bad_value
            with self.assertRaises(ValueError, msg=feature):
                policy.validate_qemu_img_info(unsupported, base_path=base, physical_size=700 * policy.MIB)
        with self.assertRaises(ValueError):
            policy.validate_qemu_img_info(dict(valid, **{"virtual-size": 9 * policy.GIB}), base_path=base, physical_size=700 * policy.MIB)

    def test_qemu_check_requires_zero_errors_leaks_and_consistent_counts(self):
        valid = {
            "filename": "/private/base.qcow2", "format": "qcow2",
            "check-errors": 0, "image-end-offset": 700 * policy.MIB, "total-clusters": 100,
            "allocated-clusters": 80, "fragmented-clusters": 3, "compressed-clusters": 4,
        }
        base = Path("/private/base.qcow2")
        self.assertEqual(policy.validate_qemu_img_check(valid, base_path=base)["check-errors"], 0)
        for field in ("check-errors", "corruptions", "leaks"):
            bad = dict(valid, **{field: 1})
            with self.assertRaises(ValueError, msg=field):
                policy.validate_qemu_img_check(bad, base_path=base)
        with self.assertRaises(ValueError):
            policy.validate_qemu_img_check(dict(valid, **{"allocated-clusters": 101}), base_path=base)

    def test_effective_cgroup_limits_are_exact_not_merely_bounded(self):
        values = {"memory.max": str(3 * policy.GIB), "memory.swap.max": "0", "pids.max": "64", "cpu.max": "200000 100000"}
        self.assertEqual(policy.verify_limits(values.__getitem__)["pids.max"], "64")
        for key, bad in (("memory.max", "max"), ("pids.max", "65"), ("cpu.max", "max 100000")):
            changed = dict(values); changed[key] = bad
            with self.assertRaises(ValueError, msg=key):
                policy.verify_limits(changed.__getitem__)

    def test_qmp_requires_one_guest_shutdown(self):
        event = {"event": "SHUTDOWN", "data": {"guest": True, "reason": "guest-shutdown"}}
        self.assertTrue(policy.qmp_shutdown_seen([event]))
        self.assertFalse(policy.qmp_shutdown_seen([]))
        self.assertFalse(policy.qmp_shutdown_seen([event, event]))
        self.assertFalse(policy.qmp_shutdown_seen([{"event": "SHUTDOWN", "data": {"guest": False}}]))
        total = policy.charge_stream(0, 600_000, policy.STREAM_MAX)
        with self.assertRaises(ValueError):
            policy.charge_stream(total, 600_000, policy.STREAM_MAX)

    def test_apt_plan_rejects_non_noble_origin_and_unlisted_dependency(self):
        valid = "Inst qemu-utils (1:8.2 Ubuntu:24.04/noble-updates [amd64])\nAfter this operation, 12.5 MB of additional disk space will be used.\n"
        self.assertEqual(apt_guard.parse_plan(valid, {"qemu-utils"})["estimated_new_bytes"], 12_500_000)
        pcsc = "Inst libpcsclite1 (2.0.3-1build1 Ubuntu:24.04/noble [amd64])\nAfter this operation, 95.0 kB of additional disk space will be used.\n"
        self.assertEqual(apt_guard.parse_plan(pcsc, {"libpcsclite1"})["packages"][0]["name"], "libpcsclite1")
        allowed_text = (Path(__file__).parent / "allowed-packages.txt").read_text().splitlines()
        self.assertEqual(allowed_text.count("libpcsclite1"), 1)
        with self.assertRaises(ValueError):
            apt_guard.parse_plan(valid.replace("Ubuntu:24.04/noble-updates", "Vendor:1/stable"), {"qemu-utils"})
        with self.assertRaises(ValueError):
            apt_guard.parse_plan(valid.replace("qemu-utils", "mystery-helper"), {"qemu-utils"})

    def test_artifact_directory_rejects_extra_file_and_aggregate_overflow(self):
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["apt-plan.log"], policy.STREAM_MAX)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipt.json").write_bytes(b"{}")
            total, observed = policy.ensure_evidence_allowlist(root, {"receipt.json": 16})
            self.assertEqual((total, list(observed)), (2, ["receipt.json"]))
            (root / "raw-serial.log").write_bytes(b"secret")
            with self.assertRaises(ValueError):
                policy.ensure_evidence_allowlist(root, {"receipt.json": 16})

    def test_candidate_has_offline_no_default_device_flags_and_no_product_import(self):
        source = (Path(__file__).parent / "host_controller.py").read_text()
        for token in ('"-nodefaults"', '"-no-user-config"', '"-nic", "none"', '"-display", "none"', '"-accel", "tcg,thread=single"'):
            self.assertIn(token, source)
        self.assertNotIn("DefiantMaple", source)
        self.assertNotIn("docker", source.lower())
        self.assertIn('QEMU_SYSTEM = Path("/usr/bin/qemu-system-x86_64")', source)
        self.assertIn('QEMU_IMG = Path("/usr/bin/qemu-img")', source)
        self.assertIn('CLOUD_LOCALDS = Path("/usr/bin/cloud-localds")', source)
        self.assertIn("os.dup2(null_fd, target_fd)", source)
        self.assertNotIn("shutil.which", source)

    def test_workflow_activation_is_push_bound_non_circular_and_cleanup_gated(self):
        workflow = (Path(__file__).parent / "workflow-candidate.yml").read_text()
        self.assertIn("push:", workflow)
        self.assertIn("branches:\n      - codex/enospc-host-inventory", workflow)
        self.assertIn("ROOT_GO_INPUT: ${{ github.event.head_commit.message }}", workflow)
        self.assertIn('test "$ROOT_GO_INPUT" = "$EXPECTED_ROOT_GO_COMMIT_MESSAGE"', workflow)
        self.assertIn('test "$(git -C "$GITHUB_WORKSPACE" rev-parse HEAD)" = "$GITHUB_SHA"', workflow)
        self.assertIn("payload-source-hashes.txt", workflow)
        self.assertIn("cleanup_wait.py", workflow)
        self.assertIn("BOOT_OUTCOME: ${{ steps.boot.outcome }}", workflow)
        self.assertIn("verify-export", workflow)
        self.assertIn("steps.finalize.outcome == 'success'", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertNotIn("EXPECTED_SOURCE_SHA", workflow)
        self.assertNotIn("${{ inputs.", workflow)

    def test_host_controller_loads_exact_sibling_policy_under_isolation(self):
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(Path(__file__).parent / "host_controller.py"), "--help"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_guest_tool_absence_is_not_used_for_type_or_size_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = guest_bootstrap.tool_fact(str(root / "missing"))
            self.assertIsNone(missing["resolved"])
            with self.assertRaises(RuntimeError):
                guest_bootstrap.tool_fact(str(root))
            oversized = root / "oversized"
            oversized.write_bytes(b"ab")
            original = guest_bootstrap.FILE_MAX
            try:
                guest_bootstrap.FILE_MAX = 1
                with self.assertRaises(RuntimeError):
                    guest_bootstrap.tool_fact(str(oversized))
            finally:
                guest_bootstrap.FILE_MAX = original


if __name__ == "__main__":
    unittest.main()

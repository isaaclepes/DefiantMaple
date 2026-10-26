from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import apt_guard
import apt_metadata
import guest_bootstrap
import host_controller
import policy


class DirectBootPolicyTests(unittest.TestCase):
    def apt_metadata(self, packages, size=1):
        return {
            "schema": "dm-apt-installed-size-v2",
            "apt_cache": {"path": "/usr/bin/apt-cache", "sha256": "a" * 64, "bytes": 1234, "uid": 0, "mode": 0o755},
            "source_list_sha256": "b" * 64,
            "lists_identity": [1, 2],
            "lists_manifest": {
                "regular_files": 6,
                "index_files": 6,
                "auxiliary_files": 0,
                "total_bytes": 123456,
                "sha256": "c" * 64,
                "administrative": [
                    {"name": "lock", "kind": "empty-lock", "uid": 0, "gid": 0, "mode": 0o600},
                    {"name": "partial", "kind": "opaque-directory", "uid": 42, "gid": 0, "mode": 0o700},
                    {"name": "auxfiles", "kind": "hashed-directory", "uid": 42, "gid": 0, "mode": 0o755},
                ],
            },
            "records": [
                {"name": package["name"].split(":", 1)[0], "version": package["version"], "architecture": package["architecture"],
                 "installed_size_kib": size, "metadata_sha256": f"{index + 1:064x}"}
                for index, package in enumerate(packages)
            ],
        }

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
        valid = "0 upgraded, 1 newly installed, 0 to remove and 98 not upgraded.\nInst qemu-utils (1:8.2 Ubuntu:24.04/noble-updates [amd64])\nConf qemu-utils (1:8.2 Ubuntu:24.04/noble-updates [amd64])\n"
        transaction = apt_guard.parse_transaction(valid, {"qemu-utils"})
        self.assertEqual(apt_guard.parse_plan(valid, {"qemu-utils"}, self.apt_metadata(transaction["packages"], 12))["estimated_new_bytes"], 12 * 1024)
        allowed_text = (Path(__file__).parent / "allowed-packages.txt").read_text().splitlines()
        self.assertEqual(allowed_text.count("libpcsclite1"), 1)
        self.assertEqual(allowed_text.count("libcacard0"), 1)
        with self.assertRaises(ValueError):
            apt_guard.parse_transaction(valid.replace("Ubuntu:24.04/noble-updates", "Vendor:1/stable"), {"qemu-utils"})
        with self.assertRaises(ValueError):
            apt_guard.parse_transaction(valid.replace("qemu-utils", "mystery-helper"), {"qemu-utils"})

    def test_complete_t3_plan_and_exact_version_metadata_are_fail_closed(self):
        fixture = (Path(__file__).parent / "fixtures" / "t3-apt-plan-sanitized.txt").read_text()
        allowed = {line for line in (Path(__file__).parent / "allowed-packages.txt").read_text().splitlines() if line and not line.startswith("#")}
        with self.assertRaisesRegex(ValueError, "outside reviewed allowlist: libcacard0"):
            apt_guard.parse_transaction(fixture, allowed - {"libcacard0"})
        transaction = apt_guard.parse_transaction(fixture, allowed)
        expected = [
            "genisoimage", "ipxe-qemu", "libbrlapi0.8", "libpcsclite1", "libcacard0", "libdaxctl1",
            "libndctl6", "libpmem1", "librdmacm1t64", "liburing2", "libusbredirparser1t64",
            "qemu-system-common", "qemu-system-data", "libfdt1", "seabios", "qemu-system-x86",
            "qemu-utils", "cloud-image-utils",
        ]
        self.assertEqual([item["name"] for item in transaction["packages"]], expected)
        self.assertEqual(transaction["transaction"], {"upgraded": 0, "newly_installed": 18, "removed": 0, "not_upgraded": 98})
        metadata = self.apt_metadata(transaction["packages"], 1024)
        parsed = apt_guard.parse_plan(fixture, allowed, metadata)
        self.assertEqual(parsed["estimated_new_bytes"], 18 * 1024 * 1024)
        mode_0640 = json.loads(json.dumps(metadata)); mode_0640["lists_manifest"]["administrative"][0]["mode"] = 0o640
        self.assertEqual(apt_guard.parse_plan(fixture, allowed, mode_0640)["estimated_new_bytes"], 18 * 1024 * 1024)
        missing = json.loads(json.dumps(metadata)); missing["records"].pop()
        with self.assertRaises(ValueError):
            apt_guard.parse_plan(fixture, allowed, missing)
        wrong_version = json.loads(json.dumps(metadata)); wrong_version["records"][4]["version"] += "-other"
        with self.assertRaises(ValueError):
            apt_guard.parse_plan(fixture, allowed, wrong_version)
        wrong_admin = json.loads(json.dumps(metadata)); wrong_admin["lists_manifest"]["administrative"][1]["mode"] = 0o755
        with self.assertRaisesRegex(ValueError, "partial manifest"):
            apt_guard.parse_plan(fixture, allowed, wrong_admin)
        added = fixture.replace(
            "0 upgraded, 18 newly installed, 0 to remove and 98 not upgraded.",
            "0 upgraded, 19 newly installed, 0 to remove and 98 not upgraded.\nInst mystery-helper (1.0 Ubuntu:24.04/noble [amd64])",
        ).replace(
            "Conf genisoimage (9:1.1.11-3.5 Ubuntu:24.04/noble [amd64])",
            "Conf mystery-helper (1.0 Ubuntu:24.04/noble [amd64])\nConf genisoimage (9:1.1.11-3.5 Ubuntu:24.04/noble [amd64])",
        )
        with self.assertRaisesRegex(ValueError, "outside reviewed allowlist"):
            apt_guard.parse_transaction(added, allowed)

    def test_apt_cache_stanza_requires_exact_version_architecture_and_size(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        stanza = b"Package: libcacard0\nVersion: 1:2.8.0-3build4\nArchitecture: amd64\nInstalled-Size: 108\nDescription: test fixture\n"
        self.assertEqual(apt_metadata.parse_stanza(stanza, package)["installed_size_kib"], 108)
        with self.assertRaises(ValueError):
            apt_metadata.parse_stanza(stanza.replace(b"Installed-Size: 108", b"Installed-Size: unknown"), package)
        with self.assertRaises(ValueError):
            apt_metadata.parse_stanza(stanza + b"\n" + stanza, package)

    def test_apt_cache_builds_only_in_memory_from_private_lists(self):
        argv = apt_metadata.cache_argv(Path("/private/sources.list"), Path("/private/lists"), "libcacard0", "1:2.8.0-3build4")
        self.assertNotIn("--no-generate", argv)
        self.assertIn("Dir::Cache::pkgcache=", argv)
        self.assertIn("Dir::Cache::srcpkgcache=", argv)
        self.assertIn("Dir::State::lists=/private/lists", argv)
        self.assertEqual(argv[-3:], ["--no-all-versions", "show", "libcacard0=1:2.8.0-3build4"])

    def test_apt_query_failure_diagnostic_preserves_exact_bounded_outcome(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        argv = ["/bin/sh", "-c", "printf package-output; printf query-warning >&2; exit 7"]
        raw, diagnostic = apt_metadata.bounded_query(argv, package)
        self.assertEqual(raw, b"package-output")
        self.assertEqual(diagnostic["argv"], argv)
        self.assertEqual((diagnostic["outcome"], diagnostic["returncode"]), ("exit", 7))
        self.assertEqual((diagnostic["stdout_bytes"], diagnostic["stderr_bytes"]), (14, 13))
        self.assertEqual(diagnostic["stdout_text"], "cGFja2FnZS1vdXRwdXQ=")
        self.assertEqual(diagnostic["stdout_text_encoding"], "base64")
        self.assertEqual(diagnostic["stderr_text"], "cXVlcnktd2FybmluZw==")
        self.assertEqual(diagnostic["stderr_text_encoding"], "base64")
        self.assertFalse(diagnostic["accepted"])
        self.assertEqual(diagnostic["parse_status"], "not-attempted")
        self.assertEqual(diagnostic["failure_reasons"], ["nonzero-returncode", "stderr-nonempty"])

    def test_apt_query_exec_error_is_bounded_and_recorded(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        raw, diagnostic = apt_metadata.bounded_query(["/definitely/not/a/real/apt-cache"], package)
        self.assertEqual(raw, b"")
        self.assertEqual((diagnostic["outcome"], diagnostic["returncode"]), ("exec-error", None))
        self.assertTrue(diagnostic["launch_error"].startswith("FileNotFoundError:"))
        self.assertEqual(diagnostic["failure_reasons"], ["launch-error", "stdout-empty"])
        self.assertFalse(diagnostic["accepted"])

    def test_apt_query_batch_measures_every_package_before_failing(self):
        packages = [
            {"name": name, "version": "1.0", "architecture": "amd64"}
            for name in ("first", "second", "third")
        ]
        seen = []

        def fake_query(argv, package, *, text_cap):
            seen.append(package["name"])
            self.assertEqual(text_cap, apt_metadata.diagnostic_text_cap(len(packages)))
            raw = ("Package: %s\nVersion: 1.0\nArchitecture: amd64\nInstalled-Size: 1\n" % package["name"]).encode()
            failed = package["name"] == "first"
            return raw, {
                "name": package["name"], "failure_reasons": ["stderr-nonempty"] if failed else [],
                "parse_status": "not-attempted", "parse_error": None, "accepted": not failed,
            }

        with mock.patch.object(apt_metadata, "bounded_query", side_effect=fake_query):
            records, diagnostics, failures, charged = apt_metadata.collect_queries(
                packages, Path("/private/sources.list"), Path("/private/lists")
            )
        self.assertEqual(seen, ["first", "second", "third"])
        self.assertEqual(failures, ["first"])
        self.assertEqual([record["name"] for record in records], ["second", "third"])
        self.assertEqual([item["parse_status"] for item in diagnostics], ["not-attempted", "ok", "ok"])
        self.assertGreater(charged, 0)

    def test_apt_query_diagnostic_budget_scales_to_package_ceiling(self):
        for count in (1, 18, 96):
            cap = apt_metadata.diagnostic_text_cap(count)
            self.assertLessEqual(cap, apt_metadata.DIAGNOSTIC_TEXT_MAX)
            self.assertLessEqual(2 * count * cap, apt_metadata.DIAGNOSTIC_RAW_TEXT_TOTAL_MAX)

    def test_apt_query_diagnostic_adaptively_preserves_all_failure_reasons(self):
        excerpt = apt_metadata.base64.b64encode(b"x" * apt_metadata.DIAGNOSTIC_TEXT_MAX).decode("ascii")
        queries = [
            {
                "name": "package-" + str(index), "failure_reasons": ["stderr-nonempty"],
                "stdout_text": excerpt, "stdout_text_bytes": apt_metadata.DIAGNOSTIC_TEXT_MAX,
                "stdout_text_truncated": False, "stderr_text": excerpt,
                "stderr_text_bytes": apt_metadata.DIAGNOSTIC_TEXT_MAX, "stderr_text_truncated": False,
            }
            for index in range(96)
        ]
        encoded = apt_metadata.failure_bytes({"schema": "test", "queries": queries})
        self.assertLessEqual(len(encoded), apt_metadata.TOTAL_MAX)
        decoded = json.loads(encoded)
        self.assertEqual(len(decoded["queries"]), 96)
        self.assertTrue(all(item["failure_reasons"] == ["stderr-nonempty"] for item in decoded["queries"]))
        self.assertGreater(decoded["excerpt_bytes_reduced_to_fit"], 0)

    def test_apt_lists_manifest_hashes_indexes_and_exact_administrative_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "lock").touch(mode=0o600)
            (root / "partial").mkdir(mode=0o700)
            (root / "auxfiles").mkdir(mode=0o755)
            (root / "partial" / "unreadable-scratch").write_bytes(b"not an index")
            (root / "partial" / "unreadable-scratch").chmod(0)
            index = root / "mirror_dists_noble_InRelease"
            index.write_bytes(b"signed-index-one")
            kwargs = {"root_uid": os.getuid(), "root_gid": os.getgid(), "sandbox_uid": os.getuid()}
            first = apt_metadata.lists_manifest(root, **kwargs)
            self.assertEqual(first, apt_metadata.lists_manifest(root, **kwargs))
            self.assertEqual((first["index_files"], first["auxiliary_files"], first["regular_files"]), (1, 0, 1))
            (root / "auxfiles" / "mirror.example").write_bytes(b"bounded auxiliary cache")
            second = apt_metadata.lists_manifest(root, **kwargs)
            self.assertEqual((second["index_files"], second["auxiliary_files"], second["regular_files"]), (1, 1, 2))
            self.assertNotEqual(first["sha256"], second["sha256"])
            index.write_bytes(b"signed-index-two")
            self.assertNotEqual(second["sha256"], apt_metadata.lists_manifest(root, **kwargs)["sha256"])

    def test_apt_lists_manifest_rejects_malformed_or_unreadable_entries(self):
        uid, gid = os.getuid(), os.getgid()
        exact_lock = SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0, st_gid=0, st_size=0, st_nlink=1)
        self.assertEqual(apt_metadata._administrative_record("lock", exact_lock, root_uid=0, root_gid=0, sandbox_uid=42)["kind"], "empty-lock")
        apt_metadata._administrative_record(
            "lock", SimpleNamespace(st_mode=stat.S_IFREG | 0o640, st_uid=0, st_gid=0, st_size=0, st_nlink=1),
            root_uid=0, root_gid=0, sandbox_uid=42,
        )
        for replacement in (
            {"st_size": 1}, {"st_mode": stat.S_IFREG | 0o644}, {"st_uid": 1},
            {"st_mode": stat.S_IFLNK | 0o777}, {"st_nlink": 2},
        ):
            values = vars(exact_lock).copy(); values.update(replacement)
            with self.assertRaises(RuntimeError):
                apt_metadata._administrative_record("lock", SimpleNamespace(**values), root_uid=0, root_gid=0, sandbox_uid=42)
        exact_partial = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=42, st_gid=0, st_size=4096, st_nlink=2)
        exact_aux = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=42, st_gid=0, st_size=4096, st_nlink=2)
        self.assertEqual(apt_metadata._administrative_record("partial", exact_partial, root_uid=0, root_gid=0, sandbox_uid=42)["kind"], "opaque-directory")
        self.assertEqual(apt_metadata._administrative_record("auxfiles", exact_aux, root_uid=0, root_gid=0, sandbox_uid=42)["kind"], "hashed-directory")
        for name, exact in (("partial", exact_partial), ("auxfiles", exact_aux)):
            for replacement in ({"st_uid": 0}, {"st_gid": 1}, {"st_mode": stat.S_IFDIR | 0o777}, {"st_mode": stat.S_IFLNK | 0o777}):
                values = vars(exact).copy(); values.update(replacement)
                with self.assertRaises(RuntimeError, msg=(name, replacement)):
                    apt_metadata._administrative_record(name, SimpleNamespace(**values), root_uid=0, root_gid=0, sandbox_uid=42)

        def candidate() -> tuple[tempfile.TemporaryDirectory, Path, dict]:
            temporary = tempfile.TemporaryDirectory()
            root = Path(temporary.name)
            (root / "lock").touch(mode=0o600)
            (root / "partial").mkdir(mode=0o700)
            (root / "auxfiles").mkdir(mode=0o755)
            (root / "index").write_bytes(b"index")
            return temporary, root, {"root_uid": uid, "root_gid": gid, "sandbox_uid": uid}

        for mutation in ("symlink-lock", "unknown-directory", "unreadable-index", "nested-aux", "symlink-aux", "unreadable-aux"):
            temporary, root, kwargs = candidate()
            try:
                if mutation == "symlink-lock":
                    (root / "lock").unlink(); (root / "lock").symlink_to("index")
                elif mutation == "unknown-directory":
                    (root / "unexpected").mkdir()
                elif mutation == "unreadable-index":
                    (root / "index").chmod(0)
                elif mutation == "nested-aux":
                    (root / "auxfiles" / "nested").mkdir()
                elif mutation == "symlink-aux":
                    (root / "auxfiles" / "link").symlink_to(root / "index")
                else:
                    (root / "auxfiles" / "unreadable").write_bytes(b"x"); (root / "auxfiles" / "unreadable").chmod(0)
                with self.assertRaises((RuntimeError, PermissionError), msg=mutation):
                    apt_metadata.lists_manifest(root, **kwargs)
            finally:
                temporary.cleanup()

    def test_artifact_directory_rejects_extra_file_and_aggregate_overflow(self):
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["apt-plan.log"], policy.STREAM_MAX)
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["apt-metadata.json"], policy.STREAM_MAX)
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["apt-metadata-failure.json"], policy.STREAM_MAX)
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

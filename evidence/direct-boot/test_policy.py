from __future__ import annotations

import json
import os
import select
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import apt_guard
import apt_metadata
import cgroup_admin
import cleanup_wait
import guest_bootstrap
import host_controller
import keyring_bootstrap
import policy
import qemu_watchdog


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
            "machine": "pc",
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

    def t12_qemu_info(self, base=Path("/private/base.qcow2")):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "t12-qemu-img-info-sanitized.txt").read_text())
        self.assertEqual(fixture["source"]["raw_bytes"], 1052)
        self.assertEqual(
            fixture["source"]["raw_sha256"],
            "c89d00bff8e80290aaf91ce1bd03542bad35f022c9fc81e28aed3bc055cc1626",
        )
        value = fixture["info"]
        self.assertEqual(value["filename"], "$RUN_ROOT/base.qcow2")
        self.assertEqual(value["children"][0]["info"]["filename"], "$RUN_ROOT/base.qcow2")
        value["filename"] = str(base)
        value["children"][0]["info"]["filename"] = str(base)
        return fixture, value

    def test_t13_fixture_records_unknown_startup_cause_without_boot_claim(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "t13-startup-failure.json").read_text())
        self.assertEqual(fixture["run"], 40370200242)
        self.assertEqual(fixture["commit"], "9b04d63494a6affe3294b74c1f3d78af5ecac82d")
        self.assertEqual(
            fixture["artifact_zip_sha256"],
            "588a2d74bc0f7a0e42d38c9e2b76d04de57317e8e445df2f13002ccb94941fbf",
        )
        self.assertFalse(fixture["failure"]["measurement_success"])
        self.assertIn("serial.sock", fixture["failure"]["error"])
        self.assertEqual(fixture["retained_facts"]["watchdog_events"], [])
        self.assertTrue(fixture["retained_facts"]["cgroup_empty"])
        self.assertIn("qemu_stderr", fixture["not_retained"])
        self.assertIn("direct_child_wait_status", fixture["not_retained"])
        self.assertIn("cause unknown", fixture["conclusion"])
        self.assertIn("G0", fixture["conclusion"])

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

    def test_t12_qcow_graph_fixture_accepts_only_exact_observed_file_child(self):
        base = Path("/private/base.qcow2")
        fixture, valid = self.t12_qemu_info(base)
        self.assertEqual(fixture["source"]["head"], "297999de9cfad5505d321a1d2909b228ace283f1")
        accepted = policy.validate_qemu_img_info(
            valid, base_path=base, physical_size=621284352, allocated_size=621289472,
        )
        self.assertEqual(accepted["child"], "file")
        self.assertEqual(accepted["allocated_size"], 621289472)

        mutations = []
        changed = json.loads(json.dumps(valid)); changed["children"].append(json.loads(json.dumps(changed["children"][0]))); mutations.append(("second child", changed))
        changed = json.loads(json.dumps(valid)); changed["children"][0]["name"] = "backing"; mutations.append(("child name", changed))
        changed = json.loads(json.dumps(valid)); changed["children"][0]["extra"] = 1; mutations.append(("child keys", changed))
        changed = json.loads(json.dumps(valid)); changed["children"][0]["info"]["backing-filename"] = "/external"; mutations.append(("nested key", changed))
        changed = json.loads(json.dumps(valid)); changed["children"][0]["info"]["children"] = [{"name": "nested", "info": {}}]; mutations.append(("descendant", changed))
        changed = json.loads(json.dumps(valid)); changed["children"][0]["info"]["filename"] = "/different"; mutations.append(("child path", changed))
        changed = json.loads(json.dumps(valid)); changed["children"][0]["info"]["format"] = "raw"; mutations.append(("child format", changed))
        changed = json.loads(json.dumps(valid)); changed["children"][0]["info"]["virtual-size"] = True; mutations.append(("child virtual type", changed))
        changed = json.loads(json.dumps(valid)); changed["children"][0]["info"]["actual-size"] += 512; mutations.append(("child actual", changed))
        changed = json.loads(json.dumps(valid)); changed["children"][0]["info"]["dirty-flag"] = True; mutations.append(("child dirty", changed))
        changed = json.loads(json.dumps(valid)); changed["children"][0]["info"]["format-specific"]["extra"] = 1; mutations.append(("child format-specific keys", changed))
        changed = json.loads(json.dumps(valid)); changed["children"][0]["info"]["format-specific"]["data"]["extent-size-hint"] = 4096; mutations.append(("child data", changed))
        for name, changed in mutations:
            with self.assertRaises(ValueError, msg=name):
                policy.validate_qemu_img_info(
                    changed, base_path=base, physical_size=621284352, allocated_size=621289472,
                )

    def test_qcow_top_schema_rejects_unknown_external_and_malformed_scalars(self):
        base = Path("/private/base.qcow2")
        _, valid = self.t12_qemu_info(base)
        mutations = []
        for key, value in (("backing-filename", "/external"), ("snapshots", []), ("encrypted", True)):
            changed = json.loads(json.dumps(valid)); changed[key] = value; mutations.append((key, changed))
        for key in ("backing-filename", "data-file", "encrypt"):
            changed = json.loads(json.dumps(valid)); changed["format-specific"]["data"][key] = "x"; mutations.append((key, changed))
        changed = json.loads(json.dumps(valid)); changed["format-specific"]["extra"] = {}; mutations.append(("specific outer key", changed))
        changed = json.loads(json.dumps(valid)); changed["format-specific"]["data"]["corrupt"] = True; mutations.append(("corrupt", changed))
        changed = json.loads(json.dumps(valid)); changed["format-specific"]["data"]["lazy-refcounts"] = True; mutations.append(("lazy", changed))
        changed = json.loads(json.dumps(valid)); changed["format-specific"]["data"]["extended-l2"] = True; mutations.append(("extended", changed))
        changed = json.loads(json.dumps(valid)); changed["format-specific"]["data"]["refcount-bits"] = True; mutations.append(("refcount type", changed))
        changed = json.loads(json.dumps(valid)); changed["virtual-size"] = True; mutations.append(("virtual type", changed))
        changed = json.loads(json.dumps(valid)); changed["actual-size"] = True; mutations.append(("actual type", changed))
        changed = json.loads(json.dumps(valid)); changed["cluster-size"] = 131072; mutations.append(("cluster", changed))
        changed = json.loads(json.dumps(valid)); changed["dirty-flag"] = 0; mutations.append(("dirty type", changed))
        for name, changed in mutations:
            with self.assertRaises(ValueError, msg=name):
                policy.validate_qemu_img_info(
                    changed, base_path=base, physical_size=621284352, allocated_size=621289472,
                )
        with self.assertRaises(ValueError):
            policy.validate_qemu_img_info(
                valid, base_path=base, physical_size=621284353, allocated_size=621289472,
            )
        with self.assertRaises(ValueError):
            policy.validate_qemu_img_info(
                valid, base_path=base, physical_size=621284352, allocated_size=621288960,
            )

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

    def test_k2_loader_fixture_uses_only_exact_canonical_owner(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "k2-loader-ownership.json").read_text())

        def record(argv):
            if argv[1] == "-S":
                raw = fixture["requested_stdout"] if argv[-1] == fixture["requested"] else fixture["resolved_stdout"]
            else:
                raw = "\t".join((fixture["package"], fixture["version"], fixture["architecture"])) + "\n"
            encoded = raw.encode()
            return {
                "argv": argv, "returncode": 0, "timed_out": False, "exec_error": None,
                "stdout_bytes": len(encoded), "stdout_sha256": policy.sha_bytes(encoded),
                "stdout_text": raw, "stdout_truncated": False, "stderr_bytes": 0,
                "stderr_sha256": policy.sha_bytes(b""), "stderr_text": "",
                "stderr_truncated": False,
            }

        with mock.patch.object(host_controller, "bounded_dpkg_query", side_effect=record) as query:
            observed = host_controller.package_for_file(Path(fixture["requested"]), Path(fixture["resolved"]))
        self.assertEqual(query.call_count, 3)
        self.assertEqual(observed["package"], fixture["package"])
        self.assertEqual(observed["version"], fixture["version"])
        self.assertEqual(observed["architecture"], fixture["architecture"])
        self.assertEqual(observed["ownership_queries"][0]["classification"], "diversion-only")
        self.assertIsNone(observed["ownership_queries"][0]["owner"])
        self.assertEqual(observed["ownership_queries"][0]["query"]["stdout_text"], fixture["requested_stdout"])
        self.assertEqual(observed["ownership_queries"][1]["classification"], "one-owner")

    def test_t10_no_match_fixture_uses_only_synthetic_canonical_owner(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "t10-libaio-no-match.json").read_text())
        synthetic = fixture["synthetic_positive"]
        self.assertTrue(synthetic["test_only"])
        self.assertTrue(synthetic["not_observed_real_owner"])
        self.assertFalse(fixture["canonical_query_observed"])
        self.assertIsNone(fixture["canonical_owner_observed"])

        def successful_record(argv, raw):
            encoded = raw.encode()
            return {
                "argv": argv, "returncode": 0, "timed_out": False, "exec_error": None,
                "stdout_bytes": len(encoded), "stdout_sha256": policy.sha_bytes(encoded),
                "stdout_text": raw, "stdout_truncated": False, "stderr_bytes": 0,
                "stderr_sha256": policy.sha_bytes(b""), "stderr_text": "",
                "stderr_truncated": False,
            }

        canonical_argv = [host_controller.DPKG_QUERY, "-S", fixture["resolved"]]
        version_argv = [
            host_controller.DPKG_QUERY, "-W",
            "-f=${binary:Package}\t${Version}\t${Architecture}\n", synthetic["owner"],
        ]
        canonical = successful_record(
            canonical_argv, synthetic["owner"] + ": " + fixture["resolved"] + "\n"
        )
        version = successful_record(
            version_argv,
            "\t".join((synthetic["owner"], synthetic["version"], synthetic["architecture"])) + "\n",
        )
        with mock.patch.object(
            host_controller, "bounded_dpkg_query",
            side_effect=[fixture["requested_query"], canonical, version],
        ) as query:
            observed = host_controller.package_for_file(Path(fixture["requested"]), Path(fixture["resolved"]))
        self.assertEqual(query.call_count, 3)
        self.assertEqual(observed["package"], synthetic["owner"])
        self.assertEqual(observed["version"], synthetic["version"])
        self.assertEqual(observed["ownership_queries"][0]["classification"], "no-match")
        self.assertEqual(observed["ownership_queries"][0]["query"], fixture["requested_query"])
        self.assertEqual(observed["ownership_queries"][1]["classification"], "one-owner")

    def test_no_match_fallback_rejects_warnings_timeout_and_nonexact_records(self):
        path = "/lib/x86_64-linux-gnu/libaio.so.1t64"
        expected = "dpkg-query: no path found matching pattern " + path + "\n"

        def record(**changes):
            stderr = changes.pop("stderr_text", expected)
            value = {
                "returncode": 1, "timed_out": False, "exec_error": None,
                "stdout_bytes": 0, "stdout_text": "", "stdout_truncated": False,
                "stderr_bytes": len(stderr.encode()), "stderr_text": stderr,
                "stderr_truncated": False,
            }
            value.update(changes)
            return value

        self.assertEqual(host_controller.ownership_result(record(), path)["classification"], "no-match")
        rejected = [
            record(stderr_text=expected + "warning not suppressed\n"),
            record(timed_out=True),
            record(exec_error="OSError"),
            record(stdout_bytes=1, stdout_text="x"),
            record(stdout_truncated=True),
            record(stderr_truncated=True),
            record(returncode=0),
            record(returncode=2),
            record(stderr_bytes=len(expected.encode()) - 1),
            record(stderr_text=expected.replace(path, "/different")),
        ]
        for candidate in rejected:
            self.assertNotEqual(
                host_controller.ownership_result(candidate, path)["classification"],
                "no-match",
            )

    def test_direct_exact_owner_does_not_require_canonical_fallback(self):
        requested = "/usr/lib/libexample.so"
        resolved = "/usr/lib/libexample.so.1"

        def record(argv):
            raw = ("example:amd64: " + requested + "\n") if argv[1] == "-S" else "example:amd64\t1.0\tamd64\n"
            encoded = raw.encode()
            return {
                "argv": argv, "returncode": 0, "timed_out": False, "exec_error": None,
                "stdout_bytes": len(encoded), "stdout_sha256": policy.sha_bytes(encoded),
                "stdout_text": raw, "stdout_truncated": False, "stderr_bytes": 0,
                "stderr_sha256": policy.sha_bytes(b""), "stderr_text": "", "stderr_truncated": False,
            }

        with mock.patch.object(host_controller, "bounded_dpkg_query", side_effect=record) as query:
            observed = host_controller.package_for_file(Path(requested), Path(resolved))
        self.assertEqual(query.call_count, 2)
        self.assertEqual(observed["package"], "example:amd64")
        self.assertEqual(len(observed["ownership_queries"]), 1)

    def test_loader_owner_parser_rejects_unknown_multi_path_stderr_and_truncation(self):
        path = "/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"

        def record(raw, **changes):
            encoded = raw.encode()
            value = {
                "returncode": 0, "timed_out": False, "exec_error": None,
                "stdout_text": raw, "stdout_truncated": False, "stderr_bytes": 0,
                "stderr_truncated": False,
            }
            value.update(changes)
            return value

        bad = [
            record("unexpected output\n"),
            record("libc6:amd64, other: " + path + "\n"),
            record("libc6:amd64: /different\n"),
            record("libc6:amd64: " + path + "\n", stderr_bytes=1),
            record("libc6:amd64: " + path + "\n", stdout_truncated=True),
        ]
        for candidate in bad:
            self.assertNotEqual(host_controller.ownership_result(candidate, path)["classification"], "one-owner")
        mixed = record("diversion by libc6 from: " + path + "\nlibc6:amd64: " + path + "\n")
        self.assertEqual(host_controller.ownership_result(mixed, path)["classification"], "ambiguous")
        inconsistent = record(
            "diversion by libc6 from: " + path + "\n"
            "diversion by other to: " + path + ".usr-is-merged\n"
        )
        self.assertEqual(host_controller.ownership_result(inconsistent, path)["classification"], "ambiguous")
        extra_package = record(
            "diversion by libc6 from: " + path + "\n"
            "diversion by libc6 from: " + path + "\n"
            "diversion by libc6 to: " + path + ".usr-is-merged\n"
        )
        extra_local = record(
            "local diversion from: " + path + "\n"
            "local diversion to: " + path + ".one\n"
            "local diversion to: " + path + ".two\n"
        )
        same_destination = record(
            "diversion by libc6 from: " + path + "\n"
            "diversion by libc6 to: " + path + "\n"
        )
        for candidate in (extra_package, extra_local, same_destination):
            self.assertEqual(host_controller.ownership_result(candidate, path)["classification"], "ambiguous")

    def test_package_version_requires_one_finite_newline_terminated_record(self):
        requested = Path("/usr/lib/libexample.so")

        def result(raw):
            encoded = raw.encode()
            return {
                "argv": [], "returncode": 0, "timed_out": False, "exec_error": None,
                "stdout_bytes": len(encoded), "stdout_sha256": policy.sha_bytes(encoded),
                "stdout_text": raw, "stdout_truncated": False, "stderr_bytes": 0,
                "stderr_sha256": policy.sha_bytes(b""), "stderr_text": "", "stderr_truncated": False,
            }

        owner = result("example:amd64: " + str(requested) + "\n")
        for invalid in (
            "example:amd64\t1.0\nforged\tamd64\n",
            "example:amd64\t1.0 bad\tamd64\n",
            "example:amd64\t1.0\tamd64",
        ):
            with mock.patch.object(host_controller, "bounded_dpkg_query", side_effect=[owner, result(invalid)]), \
                    self.assertRaises(host_controller.PackageOwnershipError):
                host_controller.package_for_file(requested, requested)

    def test_unknown_alias_failure_retains_its_bounded_raw_query(self):
        requested = Path("/lib64/ld-linux-x86-64.so.2")
        raw = "unknown output\n"
        query = {
            "argv": [host_controller.DPKG_QUERY, "-S", str(requested)], "returncode": 0,
            "timed_out": False, "exec_error": None, "stdout_bytes": len(raw.encode()),
            "stdout_sha256": policy.sha_bytes(raw.encode()), "stdout_text": raw,
            "stdout_truncated": False, "stderr_bytes": 0,
            "stderr_sha256": policy.sha_bytes(b""), "stderr_text": "", "stderr_truncated": False,
        }
        with mock.patch.object(host_controller, "bounded_dpkg_query", return_value=query), \
                self.assertRaises(host_controller.PackageOwnershipError) as failure:
            host_controller.package_for_file(requested, Path("/usr/lib/loader"))
        self.assertEqual(failure.exception.observation["ownership_queries"][0]["query"], query)
        self.assertEqual(failure.exception.observation["ownership_queries"][0]["classification"], "ambiguous")

    def test_dpkg_query_capture_has_clean_locale_and_hard_output_cap(self):
        script = "import json,os; print(json.dumps(dict(os.environ),sort_keys=True,separators=(',',':')))"
        with mock.patch.object(host_controller, "DPKG_QUERY", sys.executable):
            environment = host_controller.bounded_dpkg_query([sys.executable, "-c", script])
            overflow = host_controller.bounded_dpkg_query([
                sys.executable, "-c", "import os; os.write(1,b'x'*8192)",
            ])
        self.assertTrue(host_controller.accepted_query(environment))
        self.assertEqual(json.loads(environment["stdout_text"]), {
            "HOME": "/nonexistent", "LANG": "C.UTF-8", "LANGUAGE": "C.UTF-8",
            "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin",
        })
        self.assertEqual(overflow["stdout_bytes"], host_controller.DPKG_OUTPUT_MAX)
        self.assertTrue(overflow["stdout_truncated"])
        self.assertFalse(host_controller.accepted_query(overflow))

    def test_root_create_uses_read_only_root_controls_and_separate_populated_source(self):
        name = "dm-direct-boot-" + "a" * 16
        fixture = json.loads((Path(__file__).parent / "fixtures" / "k2-cgroup-root-source.json").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            controllers = fixture["root_cgroup_controllers"]
            subtree_control = fixture["root_cgroup_subtree_control"]
            (root / "cgroup.controllers").write_text(controllers)
            (root / "cgroup.subtree_control").write_text(subtree_control)
            source = root / fixture["source_cgroup"].lstrip("/")
            source.mkdir(parents=True)
            (source / "cgroup.procs").write_text("111\n222\n")
            target = root / name
            original_mkdir = Path.mkdir

            def kernel_mkdir(path, mode=0o777, parents=False, exist_ok=False):
                original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)
                if path == target:
                    (path / "cgroup.procs").write_text("")
                    (path / "cgroup.events").write_text("populated 0\n")

            with mock.patch.object(cgroup_admin, "ROOT", root), \
                    mock.patch.object(cgroup_admin, "own_cgroup", return_value=source), \
                    mock.patch.object(cgroup_admin, "own_cgroup_relative", return_value=fixture["source_cgroup"]), \
                    mock.patch.object(cgroup_admin.os, "geteuid", return_value=0), \
                    mock.patch.object(Path, "mkdir", new=kernel_mkdir):
                receipt = cgroup_admin.create(name)
            self.assertEqual(receipt["path"], str(target))
            self.assertEqual(receipt["control_parent"]["path"], str(root))
            self.assertEqual(receipt["control_parent"]["cgroup"], "/")
            self.assertEqual(receipt["source"]["path"], str(source))
            self.assertEqual(receipt["source"]["cgroup"], fixture["source_cgroup"])
            self.assertEqual((source / "cgroup.procs").read_text(), "111\n222\n")
            self.assertEqual((root / "cgroup.controllers").read_text(), controllers)
            self.assertEqual((root / "cgroup.subtree_control").read_text(), subtree_control)
            self.assertFalse((source / name).exists())

    def test_root_create_missing_controller_fails_before_leaf_creation(self):
        name = "dm-direct-boot-" + "9" * 16
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "cgroup.controllers").write_text("cpu memory pids\n")
            (root / "cgroup.subtree_control").write_text("cpu pids\n")
            source = root / "service"; source.mkdir()
            with mock.patch.object(cgroup_admin, "ROOT", root), \
                    mock.patch.object(cgroup_admin, "own_cgroup", return_value=source), \
                    mock.patch.object(cgroup_admin, "own_cgroup_relative", return_value="/service"), \
                    mock.patch.object(cgroup_admin.os, "geteuid", return_value=0), \
                    self.assertRaisesRegex(RuntimeError, "required root controllers"):
                cgroup_admin.create(name)
            self.assertFalse((root / name).exists())

    def test_root_attach_is_one_write_with_separate_control_and_source_checks(self):
        name = "dm-direct-boot-" + "b" * 16
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "cgroup.controllers").write_text("cpuset cpu io memory pids\n")
            (root / "cgroup.subtree_control").write_text("cpuset cpu io memory pids\n")
            source = root / "service"; source.mkdir()
            (source / "cgroup.procs").write_text("111\n222\n")
            target = root / name; target.mkdir()
            for filename, value in cgroup_admin.LIMITS.items():
                (target / filename).write_text(value)
            (target / "cgroup.procs").write_text("")
            (target / "cgroup.events").write_text("populated 0\n")
            control_identity = cgroup_admin.identity(root)
            source_identity = cgroup_admin.identity(source)
            target_identity = cgroup_admin.identity(target)
            pid, start, uid, gid = 4321, 9876, 1001, 1001
            state = {"cgroup": "/service", "writes": 0}
            controls = ["cpu", "cpuset", "io", "memory", "pids"]

            def fact(observed_pid):
                return {"pid": observed_pid, "start_ticks": start, "cgroup": state["cgroup"],
                        "uids": [uid] * 4, "gids": [gid] * 4}

            def move(observed_target, observed_pid):
                self.assertEqual((observed_target, observed_pid), (target, pid))
                state["writes"] += 1
                state["cgroup"] = "/" + name
                (target / "cgroup.procs").write_text(str(pid))

            with mock.patch.object(cgroup_admin, "ROOT", root), \
                    mock.patch.object(cgroup_admin, "own_cgroup", return_value=source), \
                    mock.patch.object(cgroup_admin, "own_cgroup_relative", return_value="/service"), \
                    mock.patch.object(cgroup_admin.os, "geteuid", return_value=0), \
                    mock.patch.object(cgroup_admin, "process_fact", side_effect=fact), \
                    mock.patch.object(cgroup_admin, "write_member", side_effect=move):
                receipt = cgroup_admin.attach(
                    name, control_identity, source_identity, target_identity, controls, controls,
                    pid, start, uid, gid, "/service"
                )
            self.assertEqual(state["writes"], 1)
            self.assertEqual(receipt["members"], [pid])
            self.assertEqual(receipt["before"]["cgroup"], "/service")
            self.assertEqual(receipt["after"]["cgroup"], "/" + name)
            self.assertEqual(receipt["limits"], cgroup_admin.LIMITS)
            self.assertEqual(receipt["control_parent"]["path"], str(root))
            self.assertEqual(receipt["source"]["path"], str(source))
            self.assertEqual((source / "cgroup.procs").read_text(), "111\n222\n")

    def test_root_attach_rejects_control_source_process_empty_and_limit_mismatch(self):
        name = "dm-direct-boot-" + "c" * 16

        def candidate(mutation):
            temporary = tempfile.TemporaryDirectory()
            root = Path(temporary.name)
            (root / "cgroup.controllers").write_text("cpu memory pids\n")
            (root / "cgroup.subtree_control").write_text("cpu memory pids\n")
            source = root / "service"; source.mkdir()
            target = root / name; target.mkdir()
            for filename, value in cgroup_admin.LIMITS.items():
                (target / filename).write_text(value)
            (target / "cgroup.procs").write_text("999\n" if mutation == "nonempty" else "")
            (target / "cgroup.events").write_text("populated 1\n" if mutation == "nonempty" else "populated 0\n")
            return temporary, root, source, target

        for mutation in ("control", "source-identity", "leaf", "controllers", "enabled", "pid", "start", "uid", "gid", "source-path", "nonempty", "limit"):
            temporary, root, source, target = candidate(mutation)
            try:
                control_identity = cgroup_admin.identity(root)
                source_identity = cgroup_admin.identity(source)
                target_identity = cgroup_admin.identity(target)
                pid, start, uid, gid = 4321, 9876, 1001, 1001
                fact = {"pid": pid, "start_ticks": start, "cgroup": "/service",
                        "uids": [uid] * 4, "gids": [gid] * 4}
                args = [name, control_identity.copy(), source_identity.copy(), target_identity.copy(),
                        ["cpu", "memory", "pids"], ["cpu", "memory", "pids"],
                        pid, start, uid, gid, "/service"]
                if mutation == "control": args[1][1] += 1
                elif mutation == "source-identity": args[2][1] += 1
                elif mutation == "leaf": args[3][1] += 1
                elif mutation == "controllers": args[4] = ["cpu", "pids"]
                elif mutation == "enabled": args[5] = ["cpu", "pids"]
                elif mutation == "pid": fact["pid"] += 1
                elif mutation == "start": fact["start_ticks"] += 1
                elif mutation == "uid": fact["uids"] = [uid + 1] * 4
                elif mutation == "gid": fact["gids"] = [gid + 1] * 4
                elif mutation == "source-path": args[10] = "/different"
                elif mutation == "limit": (target / "pids.max").write_text("65")
                with mock.patch.object(cgroup_admin, "ROOT", root), \
                        mock.patch.object(cgroup_admin, "own_cgroup", return_value=source), \
                        mock.patch.object(cgroup_admin, "own_cgroup_relative", return_value="/service"), \
                        mock.patch.object(cgroup_admin.os, "geteuid", return_value=0), \
                        mock.patch.object(cgroup_admin, "process_fact", return_value=fact), \
                        mock.patch.object(cgroup_admin, "write_member") as write:
                    with self.assertRaises(RuntimeError, msg=mutation):
                        cgroup_admin.attach(*args)
                    write.assert_not_called()
            finally:
                temporary.cleanup()

    def test_root_attach_rechecks_post_write_process_membership_and_limits(self):
        name = "dm-direct-boot-" + "d" * 16
        for mutation in ("process", "membership", "limit"):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "cgroup.controllers").write_text("cpu memory pids\n")
                (root / "cgroup.subtree_control").write_text("cpu memory pids\n")
                source = root / "service"; source.mkdir()
                target = root / name; target.mkdir()
                for filename, value in cgroup_admin.LIMITS.items():
                    (target / filename).write_text(value)
                (target / "cgroup.procs").write_text("")
                (target / "cgroup.events").write_text("populated 0\n")
                control_identity = cgroup_admin.identity(root)
                source_identity = cgroup_admin.identity(source)
                target_identity = cgroup_admin.identity(target)
                pid, start, uid, gid = 4321, 9876, 1001, 1001
                calls = {"facts": 0}

                def fact(observed_pid):
                    calls["facts"] += 1
                    cgroup = "/service" if calls["facts"] == 1 else "/" + name
                    if mutation == "process" and calls["facts"] > 1:
                        observed_pid += 1
                    return {"pid": observed_pid, "start_ticks": start, "cgroup": cgroup,
                            "uids": [uid] * 4, "gids": [gid] * 4}

                def move(observed_target, observed_pid):
                    value = str(observed_pid + 1) if mutation == "membership" else str(observed_pid)
                    (observed_target / "cgroup.procs").write_text(value)
                    if mutation == "limit":
                        (observed_target / "pids.max").write_text("65")

                with mock.patch.object(cgroup_admin, "ROOT", root), \
                        mock.patch.object(cgroup_admin, "own_cgroup", return_value=source), \
                        mock.patch.object(cgroup_admin, "own_cgroup_relative", return_value="/service"), \
                        mock.patch.object(cgroup_admin.os, "geteuid", return_value=0), \
                        mock.patch.object(cgroup_admin, "process_fact", side_effect=fact), \
                        mock.patch.object(cgroup_admin, "write_member", side_effect=move):
                    with self.assertRaises(RuntimeError, msg=mutation):
                        cgroup_admin.attach(
                            name, control_identity, source_identity, target_identity,
                            ["cpu", "memory", "pids"], ["cpu", "memory", "pids"],
                            pid, start, uid, gid, "/service"
                        )

    def test_old_service_child_placement_and_nested_cleanup_paths_are_rejected(self):
        name = "dm-direct-boot-" + "e" * 16
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "service"; source.mkdir()
            old_target = source / name; old_target.mkdir()
            with mock.patch.object(cgroup_admin, "ROOT", root):
                self.assertEqual(cgroup_admin.leaf(name), root / name)
                self.assertNotEqual(cgroup_admin.leaf(name), old_target)
        self.assertTrue(qemu_watchdog.valid_leaf(Path("/sys/fs/cgroup") / name))
        self.assertFalse(qemu_watchdog.valid_leaf(Path("/sys/fs/cgroup/service") / name))
        self.assertFalse(qemu_watchdog.valid_leaf(Path("/sys/fs/cgroup/not-owned")))
        self.assertTrue(cleanup_wait.valid_leaf(Path("/sys/fs/cgroup") / name))
        self.assertFalse(cleanup_wait.valid_leaf(Path("/sys/fs/cgroup/service") / name))

    def test_controller_receipt_separately_binds_root_source_and_leaf(self):
        name = "dm-direct-boot-" + "f" * 16
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "cgroup.controllers").write_text("cpu memory pids\n")
            (root / "cgroup.subtree_control").write_text("cpu memory pids\n")
            source = root / "service"; source.mkdir()
            target = root / name; target.mkdir()
            receipt = {
                "path": str(target), "identity": cgroup_admin.identity(target),
                "control_parent": {
                    "path": str(root), "identity": cgroup_admin.identity(root), "cgroup": "/",
                    "controllers": ["cpu", "memory", "pids"],
                    "subtree_control": ["cpu", "memory", "pids"],
                },
                "source": {
                    "path": str(source), "identity": cgroup_admin.identity(source), "cgroup": "/service",
                },
            }
            with mock.patch.object(host_controller, "CGROUP_ROOT", root):
                control, observed_source, _, _, _ = host_controller.cgroup_receipt(receipt, target)
                self.assertEqual(control["cgroup"], "/")
                self.assertEqual(observed_source["cgroup"], "/service")
                for mutation in ("control", "source", "controllers"):
                    changed = json.loads(json.dumps(receipt))
                    if mutation == "control":
                        changed["control_parent"]["identity"][1] += 1
                    elif mutation == "source":
                        changed["source"]["identity"][1] += 1
                    else:
                        changed["control_parent"]["subtree_control"] = ["cpu", "pids"]
                    with self.assertRaises(RuntimeError, msg=mutation):
                        host_controller.cgroup_receipt(changed, target)

    def test_qemu_attach_order_keeps_child_unprivileged_and_gated(self):
        source = (Path(__file__).parent / "host_controller.py").read_text()
        child = source[source.index("def spawn_qemu"):source.index("def cgroup_members")]
        boot = source[source.index("pid, pidfd, gate, stderr_fd, exec_fd, fact = spawn_qemu"):source.index("serial_sock = connect_unix")]
        admin = (Path(__file__).parent / "cgroup_admin.py").read_text()
        self.assertNotIn("cgroup.procs", child)
        self.assertNotIn("os.chown", admin)
        self.assertLess(boot.index("attach_qemu"), boot.index("qemu-handoff.json"))
        self.assertLess(boot.index("qemu-handoff.json"), boot.index("watchdog-ready.json"))
        self.assertLess(boot.index("watchdog-ready.json"), boot.index('os.write(gate, b"G")'))
        self.assertIn("if gate is not None:\n            os.close(gate)", source)

    def test_qemu_exec_sentinel_live_executable_and_stderr_are_independent(self):
        with tempfile.TemporaryDirectory() as temporary:
            inert = Path(temporary); inert.chmod(0o500)
            executable = Path(sys.executable).resolve()
            executable_sha, executable_bytes = policy.sha_file(executable, 512 * policy.MIB)
            executable_stat = executable.stat()
            expected = {
                "path": str(executable), "sha256": executable_sha, "bytes": executable_bytes,
                "device": executable_stat.st_dev, "inode": executable_stat.st_ino,
            }
            root_owned = SimpleNamespace(
                st_dev=executable_stat.st_dev, st_ino=executable_stat.st_ino,
                st_mode=stat.S_IFREG | 0o755, st_uid=0, st_gid=0, st_nlink=1,
                st_size=executable_bytes, st_mtime_ns=1, st_ctime_ns=1,
            )
            with mock.patch.object(host_controller.os, "fstat", return_value=root_owned), \
                    mock.patch.object(Path, "lstat", return_value=root_owned):
                bound = host_controller.launch_executable_identity(
                    executable,
                    {"path": str(executable), "sha256": executable_sha, "bytes": executable_bytes},
                    512 * policy.MIB,
                )
            self.assertEqual((bound["device"], bound["inode"]), (expected["device"], expected["inode"]))
            argv = [str(executable), "-c", "import os,time; os.write(2,b'qemu-diagnostic\\n'); time.sleep(.5); raise SystemExit(7)"]
            with mock.patch.object(host_controller, "QEMU_SYSTEM", executable):
                pid, pidfd, gate, stderr_fd, exec_fd, fact = host_controller.spawn_qemu(argv, inert)
                try:
                    os.write(gate, b"G"); os.close(gate)
                    exec_raw = bytearray(); stderr_raw = bytearray()
                    stderr_state = {"truncated": False, "bytes_observed_at_least": 0}
                    deadline = time.monotonic() + 2
                    exec_closed = False
                    while not exec_closed and time.monotonic() < deadline:
                        exec_closed = host_controller.read_exec_sentinel(exec_fd, exec_raw)
                        host_controller.drain_qemu_stderr(stderr_fd, stderr_raw, stderr_state)
                        time.sleep(0.01)
                    self.assertTrue(exec_closed)
                    self.assertEqual(exec_raw, b"")
                    binding = host_controller.verify_live_qemu_exe(pid, fact, expected)
                    self.assertTrue(binding["verified"])
                    self.assertEqual((binding["device"], binding["inode"]), (expected["device"], expected["inode"]))
                    wrong_inode = dict(expected, inode=expected["inode"] + 1)
                    with self.assertRaises(RuntimeError):
                        host_controller.verify_live_qemu_exe(pid, fact, wrong_inode)
                    while not select.select([pidfd], [], [], 0.05)[0] and time.monotonic() < deadline:
                        host_controller.drain_qemu_stderr(stderr_fd, stderr_raw, stderr_state)
                    state = {"status": None, "reaped": False, "wait_attempted": False, "phase": None}
                    with mock.patch.object(host_controller, "wait_direct_child", wraps=host_controller.wait_direct_child) as waiter:
                        self.assertTrue(host_controller.reap_direct_child(pid, pidfd, state, "runtime"))
                        self.assertFalse(host_controller.reap_direct_child(pid, pidfd, state, "runtime"))
                        waiter.assert_called_once_with(pid, os.WNOHANG)
                    while host_controller.drain_qemu_stderr(stderr_fd, stderr_raw, stderr_state):
                        time.sleep(0.01)
                    self.assertEqual(host_controller.wait_status_fact(state["status"]), {"kind": "exited", "code": 7})
                    self.assertEqual(stderr_raw, b"qemu-diagnostic\n")
                    self.assertFalse(stderr_state["truncated"])
                finally:
                    for fd in (pidfd, stderr_fd, exec_fd):
                        os.close(fd)

    def test_qemu_exec_failure_sentinel_and_stderr_prefix_cap_are_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            inert = Path(temporary); inert.chmod(0o500)
            pid, pidfd, gate, stderr_fd, exec_fd, _ = host_controller.spawn_qemu(
                ["/definitely-absent-dm-qemu"], inert,
            )
            try:
                os.write(gate, b"G"); os.close(gate)
                raw = bytearray(); deadline = time.monotonic() + 2
                while not host_controller.read_exec_sentinel(exec_fd, raw) and time.monotonic() < deadline:
                    time.sleep(0.01)
                value = json.loads(raw)
                self.assertEqual(value["error_type"], "FileNotFoundError")
                self.assertEqual(value["errno"], 2)
                deadline = time.monotonic() + 2
                while not select.select([pidfd], [], [], 0.01)[0] and time.monotonic() < deadline:
                    pass
                state = {"status": None, "reaped": False, "wait_attempted": False, "phase": None}
                self.assertTrue(host_controller.reap_direct_child(pid, pidfd, state, "pre-exec-failure"))
                self.assertEqual(host_controller.wait_status_fact(state["status"]), {"kind": "exited", "code": 126})
            finally:
                for fd in (pidfd, stderr_fd, exec_fd):
                    os.close(fd)
        read_fd, write_fd = os.pipe()
        try:
            os.set_blocking(read_fd, False)
            os.write(write_fd, b"abcdef"); os.close(write_fd); write_fd = None
            captured = bytearray(); state = {"truncated": False, "bytes_observed_at_least": 0}
            with mock.patch.object(host_controller.policy, "STREAM_MAX", 4):
                self.assertTrue(host_controller.drain_qemu_stderr(read_fd, captured, state))
            self.assertEqual(captured, b"abcd")
            self.assertEqual(state, {"truncated": True, "bytes_observed_at_least": 5})
        finally:
            os.close(read_fd)
            if write_fd is not None:
                os.close(write_fd)

    def test_stderr_overflow_returns_promptly_under_sustained_writer(self):
        threading = __import__("threading")
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        stopped = threading.Event()
        def writer():
            try:
                block = b"x" * 65536
                while not stopped.is_set():
                    os.write(write_fd, block)
            except OSError:
                pass
            finally:
                os.close(write_fd)
        worker = threading.Thread(target=writer, daemon=True); worker.start()
        captured = bytearray(); state = {"truncated": False, "bytes_observed_at_least": 0}
        started = time.monotonic()
        try:
            with mock.patch.object(host_controller.policy, "STREAM_MAX", 4096):
                self.assertTrue(host_controller.drain_qemu_stderr(read_fd, captured, state))
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertEqual(len(captured), 4096)
            self.assertEqual(state, {"truncated": True, "bytes_observed_at_least": 4097})
        finally:
            stopped.set(); os.close(read_fd)
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())

    def test_spawn_identity_and_pidfd_failures_kill_and_reap_gated_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            inert = Path(temporary); inert.chmod(0o500)
            with mock.patch.object(host_controller, "proc_fact", return_value=None), \
                    mock.patch.object(host_controller, "wait_direct_child", wraps=host_controller.wait_direct_child) as waiter:
                with self.assertRaisesRegex(RuntimeError, "child identity unavailable"):
                    host_controller.spawn_qemu([str(Path(sys.executable).resolve())], inert)
                waiter.assert_called_once()
            with mock.patch.object(host_controller.os, "pidfd_open", side_effect=OSError("pidfd fixture")), \
                    mock.patch.object(host_controller, "wait_direct_child", wraps=host_controller.wait_direct_child) as waiter:
                with self.assertRaisesRegex(OSError, "pidfd fixture"):
                    host_controller.spawn_qemu([str(Path(sys.executable).resolve())], inert)
                waiter.assert_called_once()

    def test_forced_cleanup_reaps_exact_child_once_and_closes_pipes(self):
        with tempfile.TemporaryDirectory() as temporary:
            inert = Path(temporary); inert.chmod(0o500)
            executable = Path(sys.executable).resolve()
            with mock.patch.object(host_controller, "QEMU_SYSTEM", executable):
                pid, pidfd, gate, stderr_fd, exec_fd, fact = host_controller.spawn_qemu(
                    [str(executable), "-c", "import time; time.sleep(30)"], inert,
                )
                try:
                    os.write(gate, b"G"); os.close(gate)
                    exec_raw = bytearray(); deadline = time.monotonic() + 2
                    while not host_controller.read_exec_sentinel(exec_fd, exec_raw) and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertEqual(exec_raw, b"")
                    host_controller.signal.pidfd_send_signal(pidfd, host_controller.signal.SIGTERM, None, 0)
                    while not select.select([pidfd], [], [], 0.01)[0] and time.monotonic() < deadline:
                        pass
                    state = {"status": None, "reaped": False, "wait_attempted": False, "phase": None}
                    original_error = "RuntimeError: startup fixture"
                    with mock.patch.object(host_controller, "wait_direct_child", wraps=host_controller.wait_direct_child) as waiter:
                        retained_error = host_controller.preserve_primary_during_diagnostic(
                            original_error, "direct-child reap",
                            lambda: host_controller.reap_direct_child(pid, pidfd, state, "after-watchdog-cleanup"),
                        )
                        self.assertFalse(host_controller.reap_direct_child(pid, pidfd, state, "after-watchdog-cleanup"))
                        waiter.assert_called_once_with(pid, os.WNOHANG)
                    captured = bytearray(); stderr_state = {"truncated": False, "bytes_observed_at_least": 0}
                    self.assertFalse(host_controller.drain_qemu_stderr(stderr_fd, captured, stderr_state))
                    self.assertEqual(state["phase"], "after-watchdog-cleanup")
                    self.assertEqual(host_controller.wait_status_fact(state["status"])["kind"], "signaled")
                    self.assertEqual(retained_error, original_error)
                    self.assertTrue(host_controller.preserve_primary_during_diagnostic(
                        original_error, "fixture", lambda: (_ for _ in ()).throw(OSError("later")),
                    ).startswith(original_error + "; fixture failed: OSError"))
                finally:
                    for fd in (pidfd, stderr_fd, exec_fd):
                        os.close(fd)

    def test_final_success_rejects_late_stderr_or_incomplete_child_state(self):
        valid_state = {"status": 0, "reaped": True, "wait_attempted": True, "phase": "runtime"}
        observed = host_controller.validate_qemu_completion(
            stderr_open=False, stderr_state={"truncated": False}, exec_open=False,
            exec_bytes=b"", exec_identity={"verified": True}, child_state=dict(valid_state),
        )
        self.assertEqual(observed, {"kind": "exited", "code": 0})
        for changes in (
            {"stderr_open": True}, {"stderr_state": {"truncated": True}},
            {"exec_open": True}, {"exec_bytes": b"error"},
            {"exec_identity": None}, {"child_state": {**valid_state, "phase": "after-watchdog-cleanup"}},
            {"child_state": {**valid_state, "status": 7 << 8}},
        ):
            values = {
                "stderr_open": False, "stderr_state": {"truncated": False},
                "exec_open": False, "exec_bytes": b"", "exec_identity": {"verified": True},
                "child_state": dict(valid_state),
            }
            values.update(changes)
            with self.assertRaises(RuntimeError, msg=changes):
                host_controller.validate_qemu_completion(**values)

    def test_socket_lstat_and_cgroup_counter_diagnostics_are_fixed_and_nofollow(self):
        name = "dm-direct-boot-" + "5" * 16
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "serial.sock"
            with mock.patch.object(Path, "lstat", side_effect=FileNotFoundError):
                self.assertEqual(host_controller.socket_lstat(missing), {"name": "serial.sock", "exists": False})
            observed = SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600, st_uid=1001, st_gid=1001,
                                       st_nlink=1, st_size=0, st_dev=11, st_ino=12)
            with mock.patch.object(Path, "lstat", return_value=observed):
                self.assertEqual(host_controller.socket_lstat(missing)["type"], "socket")
            qmp = root / "qmp.sock"
            observed.st_mode = stat.S_IFLNK | 0o777
            with mock.patch.object(Path, "lstat", return_value=observed):
                self.assertEqual(host_controller.socket_lstat(qmp)["type"], "symlink")
            with self.assertRaises(RuntimeError):
                host_controller.socket_lstat(root / "unknown.sock")

            leaf = root / name; leaf.mkdir()
            (leaf / "memory.events").write_text("oom 0\noom_kill 1\n")
            (leaf / "pids.events").write_text("max 2\n")
            identity = [leaf.stat().st_dev, leaf.stat().st_ino]
            with mock.patch.object(qemu_watchdog, "CGROUP_ROOT", root):
                counters = qemu_watchdog.cgroup_counters(leaf, identity)
            self.assertEqual(counters["memory.events"]["oom_kill"], 1)
            self.assertEqual(counters["pids.events"], {"max": 2})
            with mock.patch.object(qemu_watchdog, "cgroup_ok", side_effect=[True, False]):
                with self.assertRaises(RuntimeError):
                    qemu_watchdog.cgroup_counters(leaf, identity)
            (leaf / "pids.events").write_text("max not-a-number\n")
            with mock.patch.object(qemu_watchdog, "cgroup_ok", return_value=True):
                with self.assertRaises(RuntimeError):
                    qemu_watchdog.cgroup_counters(leaf, identity)

            core = {"forced_cleanup": True, "reason": "fixture", "cgroup_empty": True, "events": []}
            with mock.patch.object(qemu_watchdog, "counter_diagnostics", return_value=(
                None, {"error_type": "RuntimeError", "message": "counter fixture", "message_truncated": False},
            )):
                error = qemu_watchdog.publish_cleanup_result(root, leaf, identity, core)
            retained = json.loads((root / "watchdog-result.json").read_bytes())
            self.assertEqual({key: retained[key] for key in core}, core)
            self.assertIsNone(retained["cgroup_counters"])
            self.assertEqual(retained["cgroup_counter_error"], error)

    def test_qemu_startup_diagnostics_do_not_change_argv_or_socket_deadlines(self):
        source = (Path(__file__).parent / "host_controller.py").read_text()
        self.assertEqual(source.count("os.waitpid("), 1)
        self.assertIn('if state["wait_attempted"]:', source)
        self.assertIn('raise RuntimeError("pidfd ready without direct-child wait status")', source)
        self.assertIn("os.pipe2(os.O_CLOEXEC)", source)
        self.assertIn("verify_live_qemu_exe(pid, fact, launch_qemu)", source)
        self.assertIn("connect_unix(serial_socket, time.monotonic() + 5, startup_progress)", source)
        self.assertIn("connect_unix(qmp_socket, time.monotonic() + 5, startup_progress)", source)
        self.assertIn('"-chardev", "socket,id=serial0,path=" + str(serial_socket) + ",server=on,wait=off"', source)

    def test_t14_fixture_binds_duplicate_accelerator_failure_and_v18_has_one_accel_route(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "t14-duplicate-accelerator-failure.json").read_text())
        self.assertEqual(fixture["run"], 40376417684)
        self.assertEqual(fixture["commit"], "f1226c621d3f48736aff056a4af8f893b2e206b7")
        self.assertEqual(fixture["tree"], "80806d4a0068ccc76380070aeb57631710d70036")
        self.assertEqual(fixture["qemu"]["package_version"], "1:8.2.2+ds-0ubuntu1.18")
        self.assertEqual(fixture["stderr"]["bytes"], 78)
        self.assertEqual(fixture["stderr"]["sha256"], "083df175480808f016b1c1d3257c157ce3840d7e173c9f4168beaa19517cfe7f")
        self.assertEqual(
            fixture["stderr"]["text"],
            'qemu-system-x86_64: The -accel and "-machine accel=" options are incompatible\n',
        )
        self.assertEqual(fixture["observed_argv"]["machine"], "pc,accel=tcg")
        self.assertEqual(fixture["observed_argv"]["accel"], "tcg,thread=single")
        self.assertFalse(fixture["outcome"]["measurement_success"])
        self.assertFalse(fixture["outcome"]["guest_boot_ready_observed"])
        self.assertEqual(fixture["outcome"]["G0"], 0)
        self.assertEqual(fixture["outcome"]["E1"], 0)
        self.assertEqual(fixture["outcome"]["E2"], 0)

        source = (Path(__file__).parent / "host_controller.py").read_text()
        self.assertNotIn('"pc,accel=tcg"', source)
        self.assertEqual(source.count('"-machine", "pc"'), 1)
        self.assertEqual(source.count('"-accel", "tcg,thread=single"'), 1)
        self.assertIn('"machine": "pc"', source)

    def test_qmp_handshake_drains_stderr_concurrently_under_existing_deadlines(self):
        threading = __import__("threading")
        qmp_read, qmp_write = os.pipe()
        stderr_read, stderr_write = os.pipe()
        os.set_blocking(qmp_read, False)
        os.set_blocking(stderr_read, False)
        result = {}; command_seen = threading.Event()
        class PipeSocket:
            def fileno(self):
                return qmp_read
            def setblocking(self, value):
                self.blocking = value
            def recv(self, size):
                return os.read(qmp_read, size)
            def sendall(self, raw):
                result["command"] = raw; command_seen.set()
        parent_sock = PipeSocket()
        def peer():
            try:
                remaining = memoryview(b"d" * 65536)
                while remaining:
                    remaining = remaining[os.write(stderr_write, remaining):]
                os.write(qmp_write, b'{"QMP":{"version":{}}}\r\n')
                if command_seen.wait(1):
                    os.write(qmp_write, b'{"return":{}}\r\n')
            finally:
                os.close(qmp_write); os.close(stderr_write)
        worker = threading.Thread(target=peer, daemon=True); worker.start()
        prefix = bytearray(); state = {"truncated": False, "bytes_observed_at_least": 0}
        try:
            qmp_buffer, events, total, stderr_open = host_controller.qmp_handshake(
                parent_sock, stderr_read, prefix, state,
            )
            worker.join(timeout=1)
            self.assertFalse(worker.is_alive())
            while stderr_open:
                stderr_open = host_controller.drain_qemu_stderr(stderr_read, prefix, state)
            self.assertEqual(result["command"], b'{"execute":"qmp_capabilities"}\r\n')
            self.assertEqual((qmp_buffer, events), (bytearray(), []))
            self.assertEqual(total, len(b'{"QMP":{"version":{}}}\r\n') + len(b'{"return":{}}\r\n'))
            self.assertEqual(prefix, b"d" * 65536)
            self.assertFalse(state["truncated"])
        finally:
            os.close(qmp_read); os.close(stderr_read)

    def test_watchdog_pre_handoff_cleanup_request_parent_exit_and_timeout_are_forced(self):
        class ParentSelector:
            def __init__(self, ready):
                self.ready = ready

            def select(self, timeout):
                return [object()] if self.ready else []

        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / "cleanup-request").write_text("failure\n")
            self.assertEqual(
                qemu_watchdog.pre_handoff_reason(work, ParentSelector(False), time.monotonic() + 5),
                "controller-cleanup-request-before-handoff",
            )
            (work / "cleanup-request").unlink()
            self.assertEqual(
                qemu_watchdog.pre_handoff_reason(work, ParentSelector(True), time.monotonic() + 5),
                "parent-exited-before-handoff",
            )
            self.assertEqual(
                qemu_watchdog.pre_handoff_reason(work, ParentSelector(False), time.monotonic() - 1),
                "handoff-timeout",
            )

        event = {"op": "pidfd_send_signal", "signal": 15, "identity": {"pid": 4321}}
        with mock.patch.object(qemu_watchdog, "cleanup", return_value=(True, [event])) as cleanup:
            reason, events = qemu_watchdog.finish_forced_cleanup(
                Path("/sys/fs/cgroup/private-leaf"), [1, 2], None, None,
                "parent-exited-before-handoff", True,
            )
        cleanup.assert_called_once_with(Path("/sys/fs/cgroup/private-leaf"), [1, 2], None, None)
        self.assertEqual(reason, "parent-exited-before-handoff")
        self.assertEqual(events, [event])

    def test_watchdog_forced_cleanup_signals_exact_leaf_members_without_handoff(self):
        leaf = Path("/sys/fs/cgroup/private-leaf")
        identity = [11, 22]
        fact = {"pid": 4321, "start_ticks": 99, "cgroup": "/private-leaf"}
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        events = []
        try:
            with mock.patch.object(qemu_watchdog, "members", return_value=[fact]), \
                    mock.patch.object(qemu_watchdog, "open_verified_pidfd", return_value=read_fd), \
                    mock.patch.object(qemu_watchdog.signal, "pidfd_send_signal") as send:
                qemu_watchdog.signal_members(leaf, identity, qemu_watchdog.signal.SIGTERM, events)
            send.assert_called_once_with(read_fd, qemu_watchdog.signal.SIGTERM, None, 0)
            self.assertEqual(events[0]["identity"], fact)
        finally:
            try:
                os.close(read_fd)
            except OSError:
                pass

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
        self.assertIn("APT::Cache-Limit=268435456", argv)
        self.assertFalse(any("APT::Cache-Start=" in item or "APT::Cache-Grow=" in item for item in argv))
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

    def test_apt_query_post_launch_capture_error_is_not_an_exec_error(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        real_read = os.read
        read_calls = 0

        def fail_collector_read(fd, count):
            nonlocal read_calls
            read_calls += 1
            if read_calls == 1:
                return real_read(fd, count)
            raise OSError("capture fixture")

        with mock.patch.object(apt_metadata.os, "read", side_effect=fail_collector_read):
            raw, diagnostic = apt_metadata.bounded_query(
                [sys.executable, "-c", "print('ready',flush=True)"], package
            )
        self.assertEqual(raw, b"")
        self.assertEqual(diagnostic["outcome"], "capture-error")
        self.assertIsNone(diagnostic["launch_error"])
        self.assertTrue(diagnostic["capture_error"].startswith("OSError: capture fixture"))
        self.assertIn("capture-error", diagnostic["failure_reasons"])
        self.assertEqual(diagnostic["stdout_sha256_scope"], "captured-prefix")
        self.assertFalse(diagnostic["accepted"])

    def test_apt_query_pipe_overflow_is_capped_and_fatal(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        raw, diagnostic = apt_metadata.bounded_query(
            [sys.executable, "-c", "import os; os.write(1, b'x' * 196608)"], package
        )
        self.assertLessEqual(len(raw), apt_metadata.QUERY_MAX + 1)
        self.assertGreater(diagnostic["stdout_bytes"], apt_metadata.QUERY_MAX)
        self.assertIn("stdout-cap", diagnostic["failure_reasons"])
        self.assertEqual(diagnostic["stdout_sha256_scope"], "captured-prefix")
        self.assertTrue(diagnostic["stdout_capture_truncated"])
        self.assertFalse(diagnostic["accepted"])

    def test_apt_query_concurrently_drains_full_stdout_and_stderr_caps(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        code = (
            "import os,threading\n"
            "def emit(fd, data):\n"
            " while data:\n"
            "  data = data[os.write(fd, data):]\n"
            "jobs=[threading.Thread(target=emit,args=(1,b'o'*131072)),"
            "threading.Thread(target=emit,args=(2,b'e'*131072))]\n"
            "[job.start() for job in jobs]\n"
            "[job.join() for job in jobs]\n"
        )
        raw, diagnostic = apt_metadata.bounded_query([sys.executable, "-c", code], package)
        self.assertEqual(len(raw), apt_metadata.QUERY_MAX)
        self.assertEqual(diagnostic["stderr_bytes"], apt_metadata.QUERY_MAX)
        self.assertEqual(diagnostic["stdout_sha256_scope"], "complete")
        self.assertEqual(diagnostic["stderr_sha256_scope"], "complete")
        self.assertNotIn("stdout-cap", diagnostic["failure_reasons"])
        self.assertNotIn("stderr-cap", diagnostic["failure_reasons"])
        self.assertIn("stderr-nonempty", diagnostic["failure_reasons"])

    def test_apt_query_overflow_kills_term_ignoring_owned_child_boundedly(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        code = (
            "import os,signal,time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "while True:\n"
            " try: os.write(1,b'x'*65536)\n"
            " except BrokenPipeError: time.sleep(10)\n"
        )
        started = time.monotonic()
        raw, diagnostic = apt_metadata.bounded_query([sys.executable, "-c", code], package)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3)
        self.assertLessEqual(len(raw), apt_metadata.QUERY_MAX + 1)
        self.assertEqual(diagnostic["returncode"], -9)
        self.assertIn("stdout-cap", diagnostic["failure_reasons"])
        self.assertEqual(diagnostic["stdout_sha256_scope"], "captured-prefix")
        self.assertTrue(diagnostic["stdout_capture_truncated"])

    def test_apt_query_timeout_terminates_owned_child_and_is_fatal(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        raw, diagnostic = apt_metadata.bounded_query(
            [sys.executable, "-c", "import time; time.sleep(2)"], package, timeout_seconds=0.05
        )
        self.assertEqual(raw, b"")
        self.assertEqual(diagnostic["outcome"], "timeout")
        self.assertIn("timeout", diagnostic["failure_reasons"])
        self.assertEqual(diagnostic["stdout_sha256_scope"], "captured-prefix")
        self.assertEqual(diagnostic["stderr_sha256_scope"], "captured-prefix")
        self.assertTrue(diagnostic["stdout_capture_truncated"])
        self.assertTrue(diagnostic["stderr_capture_truncated"])
        self.assertFalse(diagnostic["accepted"])

    def test_apt_query_inherited_pipe_holder_has_bounded_incomplete_drain(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        code = (
            "import subprocess,sys\n"
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(0.4)'])\n"
            "print('prefix',end='',flush=True)\n"
        )
        started = time.monotonic()
        raw, diagnostic = apt_metadata.bounded_query(
            [sys.executable, "-c", code], package, drain_seconds=0.05
        )
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 1)
        self.assertEqual(raw, b"prefix")
        self.assertTrue(diagnostic["pipe_drain_timeout"])
        self.assertIn("pipe-drain-timeout", diagnostic["failure_reasons"])
        self.assertEqual(diagnostic["stdout_sha256_scope"], "captured-prefix")
        self.assertEqual(diagnostic["stderr_sha256_scope"], "captured-prefix")
        self.assertTrue(diagnostic["stdout_capture_truncated"])
        self.assertTrue(diagnostic["stderr_capture_truncated"])
        self.assertFalse(diagnostic["accepted"])

    def test_apt_query_child_file_over_128k_succeeds_below_separate_file_cap(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        stanza = "Package: libcacard0\nVersion: 1:2.8.0-3build4\nArchitecture: amd64\nInstalled-Size: 108\n"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "child-internal"
            code = "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'x' * 262144); print(sys.argv[2], end='')"
            raw, diagnostic = apt_metadata.bounded_query(
                [sys.executable, "-c", code, str(target), stanza], package, temp_dir=Path(tmp)
            )
            self.assertEqual(target.stat().st_size, 262144)
        self.assertEqual(raw.decode(), stanza)
        self.assertEqual(diagnostic["returncode"], 0)
        self.assertTrue(diagnostic["accepted"])

    def test_apt_query_uses_exact_clean_environment_and_one_private_directory(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        code = "import json,os; print(json.dumps({'cwd':os.getcwd(),'env':dict(os.environ)}),end='')"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.dict(os.environ, {"APT_CONFIG": "/host/must-not-leak", "UNREVIEWED": "must-not-leak"}):
                raw, diagnostic = apt_metadata.bounded_query(
                    [sys.executable, "-c", code], package, temp_dir=root
                )
            expected = str(root)
        observed = json.loads(raw)
        self.assertEqual(observed["cwd"], expected)
        self.assertEqual(observed["env"], {
            "PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
            "HOME": expected, "TMPDIR": expected,
        })
        self.assertNotIn("APT_CONFIG", observed["env"])
        self.assertTrue(diagnostic["accepted"])

    def test_apt_query_batch_measures_every_package_before_failing(self):
        packages = [
            {"name": name, "version": "1.0", "architecture": "amd64"}
            for name in ("first", "second", "third")
        ]
        seen = []

        def fake_query(argv, package, *, text_cap, temp_dir):
            seen.append(package["name"])
            self.assertEqual(text_cap, apt_metadata.diagnostic_text_cap(len(packages)))
            self.assertIsNone(temp_dir)
            raw = ("Package: %s\nVersion: 1.0\nArchitecture: amd64\nInstalled-Size: 1\n" % package["name"]).encode()
            failed = package["name"] == "first"
            return raw, {
                "name": package["name"], "failure_reasons": ["stderr-nonempty"] if failed else [],
                "stdout_bytes": len(raw),
                "parse_status": "not-attempted", "parse_error": None, "accepted": not failed,
            }

        with mock.patch.object(apt_metadata, "bounded_query", side_effect=fake_query):
            records, diagnostics, failures, integrity_errors, charged = apt_metadata.collect_queries(
                packages, Path("/private/sources.list"), Path("/private/lists")
            )
        self.assertEqual(seen, ["first", "second", "third"])
        self.assertEqual(failures, ["first"])
        self.assertEqual([record["name"] for record in records], ["second", "third"])
        self.assertEqual([item["parse_status"] for item in diagnostics], ["not-attempted", "ok", "ok"])
        self.assertEqual(integrity_errors, [])
        self.assertGreater(charged, 0)

    def test_apt_query_batch_stops_if_private_temp_gains_an_entry(self):
        packages = [
            {"name": name, "version": "1.0", "architecture": "amd64"}
            for name in ("first", "second")
        ]
        seen = []

        def fake_query(argv, package, *, text_cap, temp_dir):
            seen.append(package["name"])
            (temp_dir / "unexpected").write_bytes(b"bounded residue")
            raw = b"Package: first\nVersion: 1.0\nArchitecture: amd64\nInstalled-Size: 1\n"
            return raw, {
                "name": package["name"], "failure_reasons": [], "stdout_bytes": len(raw),
                "parse_status": "not-attempted", "parse_error": None, "accepted": True,
            }

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            apt_metadata, "bounded_query", side_effect=fake_query
        ):
            result = apt_metadata.collect_queries(
                packages, Path("/private/sources.list"), Path("/private/lists"), temp_dir=Path(tmp)
            )
        records, diagnostics, failures, integrity_errors, charged = result
        self.assertEqual(seen, ["first"])
        self.assertEqual(len(records), 1)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(failures, [])
        self.assertEqual(integrity_errors, ["apt-query-temporary-directory-not-empty-after:first"])
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
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["keyring-bootstrap.json"], policy.STREAM_MAX)
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["keyring-cleanup.json"], policy.STREAM_MAX)
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["host-inventory-failure.json"], policy.STREAM_MAX)
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["cgroup-attach.json"], policy.STREAM_MAX)
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["qemu-img-info.raw.json"], policy.STREAM_MAX)
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["qemu-img-check.raw.json"], policy.STREAM_MAX)
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["qemu-stderr.log"], policy.STREAM_MAX)
        self.assertEqual(host_controller.ALLOWED_EVIDENCE["watchdog-stderr.log"], policy.STREAM_MAX)
        for name in ("qemu-img-info-failure.json", "qemu-img-check-failure.json",
                     "qemu-startup.json", "cgroup-create.json", "cleanup-wait.json",
                     "cgroup-destroy.json", "watchdog-ready.json", "watchdog-result.json"):
            self.assertEqual(host_controller.ALLOWED_EVIDENCE[name], 16384)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipt.json").write_bytes(b"{}")
            total, observed = policy.ensure_evidence_allowlist(root, {"receipt.json": 16})
            self.assertEqual((total, list(observed)), (2, ["receipt.json"]))
            (root / "raw-serial.log").write_bytes(b"secret")
            with self.assertRaises(ValueError):
                policy.ensure_evidence_allowlist(root, {"receipt.json": 16})

    def test_unknown_qemu_info_is_retained_before_strict_policy_rejection(self):
        base = Path("/private/base.qcow2")
        value = {
            "virtual-size": 3 * policy.GIB, "filename": str(base), "format": "qcow2",
            "actual-size": 700 * policy.MIB,
            "format-specific": {
                "type": "qcow2",
                "data": {"compat": "1.1", "compression-type": "zlib", "lazy-refcounts": False,
                         "refcount-bits": 16, "corrupt": False, "extended-l2": False},
            },
            "unreviewed-field": {"must": "remain rejected"},
        }
        raw = json.dumps(value, sort_keys=False, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            with self.assertRaises(ValueError):
                host_controller.retain_and_validate_qemu_img_info(
                    evidence, raw, base_path=base, physical_size=700 * policy.MIB,
                    allocated_size=700 * policy.MIB,
                )
            self.assertEqual((evidence / "qemu-img-info.raw.json").read_bytes(), raw)
            failure = json.loads((evidence / "qemu-img-info-failure.json").read_bytes())
            self.assertIs(failure["accepted"], False)
            self.assertEqual(failure["raw_bytes"], len(raw))
            self.assertEqual(failure["raw_sha256"], policy.sha_bytes(raw))
            self.assertLessEqual(len(failure["error"]), 1024)
            self.assertRegex(failure["error_type"], r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

    def test_qemu_check_raw_is_retained_before_strict_policy_rejection(self):
        base = Path("/private/base.qcow2")
        value = {
            "filename": str(base), "format": "qcow2", "check-errors": 0,
            "image-end-offset": 700 * policy.MIB, "total-clusters": 100,
            "allocated-clusters": 80, "fragmented-clusters": 3,
            "compressed-clusters": 4, "unreviewed-field": 1,
        }
        raw = json.dumps(value, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            with self.assertRaises(ValueError):
                host_controller.retain_and_validate_qemu_img_check(evidence, raw, base_path=base)
            self.assertEqual((evidence / "qemu-img-check.raw.json").read_bytes(), raw)
            failure = json.loads((evidence / "qemu-img-check-failure.json").read_bytes())
            self.assertIs(failure["accepted"], False)
            self.assertEqual(failure["raw_bytes"], len(raw))
            self.assertEqual(failure["raw_sha256"], policy.sha_bytes(raw))
        value.pop("unreviewed-field")
        accepted_raw = json.dumps(value, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            accepted = host_controller.retain_and_validate_qemu_img_check(
                evidence, accepted_raw, base_path=base,
            )
            self.assertEqual(accepted["check-errors"], 0)
            self.assertEqual((evidence / "qemu-img-check.raw.json").read_bytes(), accepted_raw)
            self.assertFalse((evidence / "qemu-img-check-failure.json").exists())

    def test_lifecycle_receipts_are_fixed_bounded_and_failure_stays_false(self):
        name = "dm-direct-boot-" + "7" * 16
        path = "/sys/fs/cgroup/" + name
        create = {
            "path": path, "identity": [11, 12],
            "control_parent": {
                "path": "/sys/fs/cgroup", "identity": [11, 1], "cgroup": "/",
                "controllers": ["cpu", "memory", "pids"],
                "subtree_control": ["cpu", "memory", "pids"],
            },
            "source": {"path": "/sys/fs/cgroup/service", "identity": [11, 2], "cgroup": "/service"},
            **host_controller.CGROUP_LIMITS,
        }
        cleanup = {"cgroup_empty": True, "handoff_seen": False, "watchdog_result_seen": True}
        destroy = {"removed": True, "path": path, "identity": [11, 12]}
        result = {"forced_cleanup": True, "reason": "controller-cleanup-request-before-handoff",
                  "cgroup_empty": True, "events": [],
                  "cgroup_counters": {"memory.events": {"oom": 0, "oom_kill": 0},
                                      "pids.events": {"max": 0}},
                  "cgroup_counter_error": None}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); evidence = root / "evidence"; evidence.mkdir(mode=0o700)
            values = {"cgroup.json": create, "cleanup-wait.json": cleanup,
                      "cgroup-destroy.json": destroy, "watchdog-result.json": result}
            raw = {}
            for filename, value in values.items():
                raw[filename] = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
                (root / filename).write_bytes(raw[filename])
            failure_receipt = {
                "schema": "dm-direct-boot-receipt-v1", "success": False,
                "forced_cleanup_cannot_pass": True, "cgroup_removed": False,
                "claim": "offline boot measurement only; no ENOSPC, product import, G0, E1, or E2",
                "reason": "strict image metadata policy rejected an unknown field",
            }
            (evidence / "receipt.json").write_bytes(policy.canonical(failure_receipt))
            host_controller.retain_lifecycle_receipts(root)
            self.assertEqual((evidence / "cgroup-create.json").read_bytes(), raw["cgroup.json"])
            self.assertEqual((evidence / "cleanup-wait.json").read_bytes(), raw["cleanup-wait.json"])
            self.assertEqual((evidence / "cgroup-destroy.json").read_bytes(), raw["cgroup-destroy.json"])
            self.assertEqual((evidence / "watchdog-result.json").read_bytes(), raw["watchdog-result.json"])
            self.assertFalse((evidence / "watchdog-ready.json").exists())
            self.assertFalse((evidence / "cgroup-attach.json").exists())
            destination = root / "upload"
            host_controller.export(root, destination)
            host_controller.verify_export(root, destination)
            exported = json.loads((destination / "receipt.json").read_bytes())
            self.assertIs(exported["success"], False)
            self.assertIs(exported["cgroup_removed"], False)
            manifest = json.loads((destination / "artifact-manifest.json").read_bytes())
            self.assertIn("cgroup-create.json", manifest["files"])
            self.assertIn("watchdog-result.json", manifest["files"])
            counter_failure = dict(
                result, cgroup_counters=None,
                cgroup_counter_error={
                    "error_type": "RuntimeError", "message": "counter fixture",
                    "message_truncated": False,
                },
            )
            host_controller.validate_lifecycle_receipts(
                {"cgroup-create.json": create, "cleanup-wait.json": cleanup,
                 "cgroup-destroy.json": destroy, "watchdog-result.json": counter_failure},
                None,
            )

    def test_watchdog_ready_requires_attached_handoff_state(self):
        name = "dm-direct-boot-" + "9" * 16
        path = "/sys/fs/cgroup/" + name
        create = {
            "path": path, "identity": [11, 12],
            "control_parent": {
                "path": "/sys/fs/cgroup", "identity": [11, 1], "cgroup": "/",
                "controllers": ["cpu", "memory", "pids"],
                "subtree_control": ["cpu", "memory", "pids"],
            },
            "source": {"path": "/sys/fs/cgroup/service", "identity": [11, 2], "cgroup": "/service"},
            **host_controller.CGROUP_LIMITS,
        }
        before = {"pid": 111, "start_ticks": 222, "cgroup": "/service",
                  "uids": [1001] * 4, "gids": [1001] * 4}
        after = {**before, "cgroup": "/" + name}
        attach = {
            "operation": "attach", "control_parent": create["control_parent"],
            "source": create["source"], "leaf": {"path": path, "identity": [11, 12]},
            "limits": host_controller.CGROUP_LIMITS, "before": before, "after": after,
            "members": [111],
        }
        values = {
            "cgroup-create.json": create,
            "cleanup-wait.json": {"cgroup_empty": True, "handoff_seen": False,
                                  "watchdog_result_seen": True},
            "watchdog-ready.json": {
                "ready": True,
                "qemu": {key: after[key] for key in ("pid", "start_ticks", "cgroup")},
                "watchdog": {"pid": 333, "start_ticks": 444, "cgroup": "/service"},
            },
            "watchdog-result.json": {
                "forced_cleanup": True, "reason": "controller-cleanup-request",
                "cgroup_empty": True, "events": [],
                "cgroup_counters": {"memory.events": {"oom": 0, "oom_kill": 0},
                                    "pids.events": {"max": 0}},
                "cgroup_counter_error": None,
            },
        }
        with self.assertRaises(RuntimeError):
            host_controller.validate_lifecycle_receipts(values, attach)
        values["cleanup-wait.json"]["handoff_seen"] = True
        host_controller.validate_lifecycle_receipts(values, attach)

    def test_lifecycle_receipt_identity_and_symlink_are_rejected(self):
        name = "dm-direct-boot-" + "8" * 16
        create = {
            "path": "/sys/fs/cgroup/" + name, "identity": [1, 2],
            "control_parent": {"path": "/sys/fs/cgroup", "identity": [1, 3], "cgroup": "/",
                               "controllers": ["cpu", "memory", "pids"],
                               "subtree_control": ["cpu", "memory", "pids"]},
            "source": {"path": "/sys/fs/cgroup/service", "identity": [1, 4], "cgroup": "/service"},
            **host_controller.CGROUP_LIMITS,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / "evidence").mkdir()
            create["identity"] = [1, 0]
            (root / "cgroup.json").write_bytes(policy.canonical(create))
            with self.assertRaises(RuntimeError):
                host_controller.retain_lifecycle_receipts(root)
            (root / "cgroup.json").unlink()
            target = root / "target"; target.write_bytes(b"{}")
            (root / "cgroup.json").symlink_to(target)
            with self.assertRaises(RuntimeError):
                host_controller.retain_lifecycle_receipts(root)

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
        info_gate = source.index("image_info = retain_and_validate_qemu_img_info(")
        image_check = source.index("check_raw = command([str(QEMU_IMG), \"check\"")
        check_gate = source.index("image_check = retain_and_validate_qemu_img_check(")
        overlay_create = source.index("overlay = root / \"overlay.qcow2\"")
        self.assertLess(info_gate, image_check)
        self.assertLess(image_check, check_gate)
        self.assertLess(check_gate, overlay_create)

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
        self.assertNotIn("/usr/share/keyrings/ubuntu-archive-keyring.gpg", workflow)
        self.assertIn("F6ECB3762474EDA9D21B7022871920D1991BC93C!", workflow)
        self.assertIn("keyring_bootstrap.py\" destroy", workflow)
        self.assertIn("--apt-keyring-receipt", workflow)
        self.assertIn('cgroup_admin.py" create "$CG_NAME" >', workflow)
        self.assertNotIn('cgroup_admin.py" create "$CG_NAME" "$(id -u)"', workflow)

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

    def test_pinned_keyring_create_verify_modes_and_narrow_destroy(self):
        source_dir = Path(__file__).parent
        with tempfile.TemporaryDirectory() as temporary_parent, tempfile.TemporaryDirectory() as receipt_parent:
            public_parent = Path(temporary_parent)
            private_parent = Path(receipt_parent)
            public_parent.chmod(0o1777)
            private_parent.chmod(0o700)
            parent_info = public_parent.lstat()
            receipt = private_parent / "keyring-bootstrap.json"
            report = private_parent / "keyring-cleanup.json"
            with mock.patch.object(keyring_bootstrap, "TMP_ROOT", public_parent), mock.patch.object(
                keyring_bootstrap, "validate_tmp", return_value=(public_parent, parent_info)
            ):
                created = keyring_bootstrap.create(
                    source_dir / "ubuntu-archive-keyring-2023.11.28.1.gpg",
                    source_dir / "official-source-pin.json",
                    receipt,
                )
                directory = Path(created["directory"]["path"])
                key = directory / keyring_bootstrap.KEY_NAME
                self.assertEqual(stat.S_IMODE(directory.lstat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE(key.lstat().st_mode), 0o444)
                self.assertEqual(key.read_bytes(), (source_dir / "ubuntu-archive-keyring-2023.11.28.1.gpg").read_bytes())
                self.assertEqual(keyring_bootstrap.verify_receipt(receipt)["accepted_signer"], keyring_bootstrap.ARCHIVE_SIGNER)
                removed = keyring_bootstrap.destroy(receipt, report)
                self.assertEqual(removed["status"], "removed")
                self.assertFalse(directory.exists())

    def test_pinned_keyring_rejects_wrong_source_and_public_file_mode_change(self):
        source_dir = Path(__file__).parent
        with tempfile.TemporaryDirectory() as temporary_parent, tempfile.TemporaryDirectory() as receipt_parent:
            public_parent = Path(temporary_parent)
            private_parent = Path(receipt_parent)
            public_parent.chmod(0o1777)
            private_parent.chmod(0o700)
            parent_info = public_parent.lstat()
            wrong = private_parent / "wrong.gpg"
            wrong.write_bytes(b"wrong")
            with mock.patch.object(keyring_bootstrap, "TMP_ROOT", public_parent), mock.patch.object(
                keyring_bootstrap, "validate_tmp", return_value=(public_parent, parent_info)
            ):
                with self.assertRaises(RuntimeError):
                    keyring_bootstrap.create(wrong, source_dir / "official-source-pin.json", private_parent / "wrong.json")
                receipt = private_parent / "keyring-bootstrap.json"
                report = private_parent / "keyring-cleanup.json"
                created = keyring_bootstrap.create(
                    source_dir / "ubuntu-archive-keyring-2023.11.28.1.gpg",
                    source_dir / "official-source-pin.json",
                    receipt,
                )
                key = Path(created["directory"]["path"]) / keyring_bootstrap.KEY_NAME
                key.chmod(0o644)
                with self.assertRaises(RuntimeError):
                    keyring_bootstrap.verify_receipt(receipt)
                key.chmod(0o444)
                extra = key.parent / "unexpected"
                extra.write_bytes(b"x")
                with self.assertRaises(RuntimeError):
                    keyring_bootstrap.destroy(receipt, report)
                self.assertEqual(json.loads(report.read_text())["status"], "failed")
                report.unlink()
                extra.unlink()
                keyring_bootstrap.destroy(receipt, report)

    def test_apt_cache_queries_verify_keyring_before_and_after_each_child(self):
        package = {"name": "libcacard0", "version": "1:2.8.0-3build4", "architecture": "amd64"}
        raw = b"Package: libcacard0\nVersion: 1:2.8.0-3build4\nArchitecture: amd64\nInstalled-Size: 1\n"
        diagnostic = {"stdout_bytes": len(raw), "failure_reasons": [], "accepted": True,
                      "parse_status": "not-attempted", "parse_error": None}
        with mock.patch.object(apt_metadata, "bounded_query", return_value=(raw, diagnostic.copy())), mock.patch.object(
            apt_metadata.keyring_bootstrap, "verify_receipt", return_value={}
        ) as verify:
            records, diagnostics, failures, integrity, charged = apt_metadata.collect_queries(
                [package], Path("/private/sources.list"), Path("/private/lists"), keyring_receipt=Path("/private/keyring.json")
            )
        self.assertEqual((len(records), len(diagnostics), failures, integrity, charged), (1, 1, [], [], len(raw)))
        self.assertEqual(verify.call_count, 2)

        with mock.patch.object(apt_metadata, "bounded_query", return_value=(raw, diagnostic.copy())), mock.patch.object(
            apt_metadata.keyring_bootstrap, "verify_receipt", side_effect=[{}, RuntimeError("changed")]
        ):
            _, _, _, integrity, _ = apt_metadata.collect_queries(
                [package], Path("/private/sources.list"), Path("/private/lists"), keyring_receipt=Path("/private/keyring.json")
            )
        self.assertEqual(len(integrity), 1)
        self.assertTrue(integrity[0].startswith("apt-keyring-postcheck-error:libcacard0:"))

    def test_keyring_symlink_and_hardlink_replacements_are_rejected_without_cleanup_touch(self):
        source_dir = Path(__file__).parent
        for replacement in ("symlink", "hardlink"):
            with tempfile.TemporaryDirectory() as temporary_parent, tempfile.TemporaryDirectory() as receipt_parent:
                public_parent = Path(temporary_parent)
                private_parent = Path(receipt_parent)
                public_parent.chmod(0o1777)
                private_parent.chmod(0o700)

                def validate_parent():
                    return public_parent, public_parent.lstat()

                receipt = private_parent / "keyring-bootstrap.json"
                report = private_parent / "keyring-cleanup.json"
                with mock.patch.object(keyring_bootstrap, "TMP_ROOT", public_parent), mock.patch.object(
                    keyring_bootstrap, "validate_tmp", side_effect=validate_parent
                ):
                    created = keyring_bootstrap.create(
                        source_dir / "ubuntu-archive-keyring-2023.11.28.1.gpg",
                        source_dir / "official-source-pin.json",
                        receipt,
                    )
                    directory = Path(created["directory"]["path"])
                    key = directory / keyring_bootstrap.KEY_NAME
                    external = public_parent / ("saved-" + replacement)
                    if replacement == "symlink":
                        key.rename(external)
                        key.symlink_to(external)
                    else:
                        os.link(key, external)
                    with self.assertRaises(RuntimeError, msg=replacement):
                        keyring_bootstrap.verify_receipt(receipt)
                    with self.assertRaises(RuntimeError, msg=replacement):
                        keyring_bootstrap.destroy(receipt, report)
                    self.assertTrue(external.exists())
                    self.assertEqual(json.loads(report.read_text())["status"], "failed")
                    report.unlink()
                    if replacement == "symlink":
                        self.assertTrue(key.is_symlink())
                        key.unlink()
                        external.rename(key)
                    else:
                        external.unlink()
                    keyring_bootstrap.destroy(receipt, report)

    def test_keyring_directory_identity_replacement_is_not_touched_by_destroy(self):
        source_dir = Path(__file__).parent
        with tempfile.TemporaryDirectory() as temporary_parent, tempfile.TemporaryDirectory() as receipt_parent:
            public_parent = Path(temporary_parent)
            private_parent = Path(receipt_parent)
            public_parent.chmod(0o1777)
            private_parent.chmod(0o700)

            def validate_parent():
                return public_parent, public_parent.lstat()

            receipt = private_parent / "keyring-bootstrap.json"
            report = private_parent / "keyring-cleanup.json"
            with mock.patch.object(keyring_bootstrap, "TMP_ROOT", public_parent), mock.patch.object(
                keyring_bootstrap, "validate_tmp", side_effect=validate_parent
            ):
                created = keyring_bootstrap.create(
                    source_dir / "ubuntu-archive-keyring-2023.11.28.1.gpg",
                    source_dir / "official-source-pin.json",
                    receipt,
                )
                directory = Path(created["directory"]["path"])
                saved = public_parent / "saved-original-directory"
                directory.rename(saved)
                directory.mkdir(mode=0o755)
                marker = directory / "replacement-marker"
                marker.write_bytes(b"do-not-touch")
                with self.assertRaises(RuntimeError):
                    keyring_bootstrap.verify_receipt(receipt)
                with self.assertRaises(RuntimeError):
                    keyring_bootstrap.destroy(receipt, report)
                self.assertEqual(marker.read_bytes(), b"do-not-touch")
                self.assertTrue((saved / keyring_bootstrap.KEY_NAME).is_file())
                report.unlink()
                marker.unlink()
                directory.rmdir()
                saved.rename(directory)
                keyring_bootstrap.destroy(receipt, report)

    def test_keyring_tmp_parent_identity_replacement_is_not_touched_by_destroy(self):
        source_dir = Path(__file__).parent
        with tempfile.TemporaryDirectory() as base_parent, tempfile.TemporaryDirectory() as receipt_parent:
            base = Path(base_parent)
            public_parent = base / "public-root"
            private_parent = Path(receipt_parent)
            public_parent.mkdir(mode=0o700)
            public_parent.chmod(0o1777)
            private_parent.chmod(0o700)

            def validate_parent():
                return public_parent, public_parent.lstat()

            receipt = private_parent / "keyring-bootstrap.json"
            report = private_parent / "keyring-cleanup.json"
            with mock.patch.object(keyring_bootstrap, "TMP_ROOT", public_parent), mock.patch.object(
                keyring_bootstrap, "validate_tmp", side_effect=validate_parent
            ):
                created = keyring_bootstrap.create(
                    source_dir / "ubuntu-archive-keyring-2023.11.28.1.gpg",
                    source_dir / "official-source-pin.json",
                    receipt,
                )
                original_parent = base / "saved-public-root"
                public_parent.rename(original_parent)
                public_parent.mkdir(mode=0o700)
                public_parent.chmod(0o1777)
                marker = public_parent / "replacement-marker"
                marker.write_bytes(b"do-not-touch")
                with self.assertRaises(RuntimeError):
                    keyring_bootstrap.verify_receipt(receipt)
                with self.assertRaises(RuntimeError):
                    keyring_bootstrap.destroy(receipt, report)
                self.assertEqual(marker.read_bytes(), b"do-not-touch")
                self.assertTrue((original_parent / Path(created["directory"]["path"]).name / keyring_bootstrap.KEY_NAME).is_file())
                report.unlink()
                marker.unlink()
                public_parent.rmdir()
                original_parent.rename(public_parent)
                keyring_bootstrap.destroy(receipt, report)


if __name__ == "__main__":
    unittest.main()

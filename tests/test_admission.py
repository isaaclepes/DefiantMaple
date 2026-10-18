"""Real process ownership oracles; generated files only, no deployed catalogs."""
import hashlib
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from defiantmaple.admission import (AdmissionError, LibraryInUseError, admission_session,
                                   current_session, key_bytes, registry_path)


def contender(path, registry, connection, create=False):
    try:
        with admission_session(Path(path), create=create, _registry_path=Path(registry)) as owner:
            if owner.created:
                Path(path).write_bytes(b"created")
                owner.ready()
            connection.send("owned")
            connection.recv()
    except LibraryInUseError:
        connection.send("busy")
    except BaseException as exc:
        connection.send((type(exc).__name__, str(exc)))
    finally:
        connection.close()


def idle_worker(connection):
    connection.send("ready")
    connection.recv()
    connection.close()


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = self.root / "registry"
        self.catalog = self.root / "catalog.sqlite3"
        self.catalog.write_bytes(b"fictional catalog")
        self.context = multiprocessing.get_context("spawn")

    def launch(self, path=None, create=False):
        parent, child = self.context.Pipe()
        process = self.context.Process(target=contender, args=(str(path or self.catalog), str(self.registry), child, create))
        process.start()
        child.close()
        self.addCleanup(parent.close)
        self.addCleanup(self.stop, process)
        self.assertTrue(parent.poll(10), "child did not report admission")
        return process, parent, parent.recv()

    @staticmethod
    def stop(process):
        try:
            alive = process.is_alive()
        except ValueError:  # caller deliberately closed an already exited process
            return
        if alive:
            process.kill()
        process.join(5)

    def test_protocol_golden(self):
        if os.name != "nt":
            self.assertEqual(hashlib.sha256(key_bytes("directory", (1, 2))).hexdigest(),
                             "8e99209d350b394ded05dbd1f9f281b9fd421f3bae6642f36a7659d6c5d8549f")
            self.assertEqual(hashlib.sha256(key_bytes("path", (1, 2), b"catalog.sqlite3")).hexdigest(),
                             "bd3c832253fb07ad885e70666342fd13dd338c33c7831d7c582cd90ffa8bd720")
        else:
            self.assertEqual(hashlib.sha256(key_bytes("path", (123456789, 18446744073709551615),
                                                      "Catalog.sqlite3".encode("utf-16le"))).hexdigest(),
                             "04a1f2261f67e44a13a82aed50f8b5a03d88356f5bfcf490587475f21f244b9e")
            self.assertEqual(hashlib.sha256(key_bytes("file", (2**64 - 1, 2**128 - 1))).hexdigest(),
                             "f17b74909787c9e81a1cdffd2c59b68085b6dd5b9ff43e6d91cf91a692318377")
            identifier = int.from_bytes(bytes(range(16)), "little")
            self.assertEqual(hashlib.sha256(key_bytes("directory", (123456789, identifier))).hexdigest(),
                             "dedc302e7e9278dafe33c908f1f1ba47ca6df6c7cbff6b2e4a8ae719e54a33b0")
            self.assertEqual(hashlib.sha256(key_bytes("path", (123456789, identifier),
                                                      "Catalog.sqlite3".encode("utf-16le"))).hexdigest(),
                             "da38d0e2cca6a7a9dc2d771350519e1ef0b212327720116b322a50d47161dcdf")
        self.assertTrue(key_bytes("file", (1, 2)).endswith(b"\n\n"))

    def test_windows128_key_serialization_vectors_on_any_host(self):
        # Serialization only: this does not execute or certify a Windows adapter.
        with patch("defiantmaple.admission.sys.platform", "win32"):
            self.assertEqual(hashlib.sha256(key_bytes("file", (2**64 - 1, 2**128 - 1))).hexdigest(),
                             "f17b74909787c9e81a1cdffd2c59b68085b6dd5b9ff43e6d91cf91a692318377")
            identity = (123456789, int.from_bytes(bytes(range(16)), "little"))
            self.assertEqual(hashlib.sha256(key_bytes("directory", identity)).hexdigest(),
                             "dedc302e7e9278dafe33c908f1f1ba47ca6df6c7cbff6b2e4a8ae719e54a33b0")
            self.assertEqual(hashlib.sha256(key_bytes("path", identity, "Catalog.sqlite3".encode("utf-16le"))).hexdigest(),
                             "da38d0e2cca6a7a9dc2d771350519e1ef0b212327720116b322a50d47161dcdf")

    def test_owner_refuses_real_child_and_preserves_catalog(self):
        before = self.catalog.read_bytes()
        with admission_session(self.catalog, _registry_path=self.registry):
            process, pipe, result = self.launch()
            self.assertEqual(result, "busy")
            process.join(5)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(self.catalog.read_bytes(), before)
        self.assertGreater(len(list(self.registry.glob("*.lock"))), 0)
        process, pipe, result = self.launch()
        self.assertEqual(result, "owned")
        pipe.send("release")
        process.join(5)
        self.assertEqual(process.exitcode, 0)

    def test_child_crash_releases_kernel_locks_without_unlink(self):
        process, pipe, result = self.launch()
        self.assertEqual(result, "owned")
        names = sorted(p.name for p in self.registry.iterdir())
        process.kill()
        process.join(5)
        with admission_session(self.catalog, _registry_path=self.registry):
            self.assertEqual(sorted(p.name for p in self.registry.iterdir()), names)

    def test_hardlink_alias_is_same_physical_resource(self):
        other = self.root / "other"
        other.mkdir()
        alias = other / "alias.sqlite3"
        try:
            os.link(self.catalog, alias)
        except OSError as exc:
            self.skipTest(f"hardlinks unavailable: {exc}")
        with admission_session(self.catalog, _registry_path=self.registry):
            process, pipe, result = self.launch(alias)
            self.assertEqual(result, "busy")
            process.join(5)

    def test_copy_independent_even_with_identical_content(self):
        copy = self.root / "copy.sqlite3"
        copy.write_bytes(self.catalog.read_bytes())
        with admission_session(self.catalog, _registry_path=self.registry):
            process, pipe, result = self.launch(copy)
            self.assertEqual(result, "owned")
            pipe.send("release")
            process.join(5)

    def test_nested_session_retains_until_last_reference(self):
        with admission_session(self.catalog, _registry_path=self.registry) as owner:
            with admission_session(self.catalog, _registry_path=self.registry) as nested:
                self.assertIs(owner, nested)
                self.assertIs(current_session(self.catalog), owner)
            self.assertFalse(owner.closed)
        self.assertTrue(owner.closed)

    def test_only_one_gui_coordinator_but_nested_core_session_can_borrow(self):
        with admission_session(self.catalog, _registry_path=self.registry) as owner:
            owner.claim_coordinator()
            with admission_session(self.catalog, _registry_path=self.registry) as nested:
                self.assertIs(nested, owner)
                with self.assertRaises(LibraryInUseError):
                    nested.claim_coordinator()
            owner.release_coordinator()
            owner.claim_coordinator()
            owner.release_coordinator()

    def test_gui_claim_outlives_window_close_while_child_survives(self):
        parent, child = self.context.Pipe()
        process = self.context.Process(target=idle_worker, args=(child,))
        process.start()
        child.close()
        self.addCleanup(parent.close)
        self.addCleanup(self.stop, process)
        self.assertTrue(parent.poll(10))
        parent.recv()
        with admission_session(self.catalog, _registry_path=self.registry) as owner:
            owner.claim_coordinator()
            owner.retain_process(process)
            owner.release_coordinator()
            with self.assertRaises(LibraryInUseError):
                owner.claim_coordinator()
        self.assertFalse(owner.closed)
        parent.send("finish")
        process.join(5)
        self.assertTrue(owner.released.wait(5))

    def test_create_keeps_directory_gate_until_ready(self):
        missing = self.root / "new.sqlite3"
        with admission_session(missing, create=True, _registry_path=self.registry) as owner:
            self.assertTrue(owner.created)
            process, pipe, result = self.launch()
            self.assertEqual(result, "busy")
            process.join(5)
            missing.write_bytes(b"initialized")
            owner.ready()
            process, pipe, result = self.launch()
            self.assertEqual(result, "owned")
            pipe.send("release")
            process.join(5)

    def test_restore_stage_stays_owned_across_publication(self):
        destination = self.root / "restored.sqlite3"
        stage = self.root / "stage.sqlite3"
        with admission_session(destination, destination=True, _registry_path=self.registry) as owner:
            stage.write_bytes(b"verified stage")
            owner.pin_stage(stage)
            os.link(stage, destination)
            owner.bind_published()
            stage.unlink()
            process, pipe, result = self.launch(destination)
            self.assertEqual(result, "busy")
            process.join(5)
        self.assertEqual(destination.read_bytes(), b"verified stage")

    def test_replacement_is_observable_and_never_adopted(self):
        with admission_session(self.catalog, _registry_path=self.registry) as owner:
            replacement = self.root / "replacement"
            replacement.write_bytes(b"new inode")
            replacement.replace(self.catalog)
            with self.assertRaisesRegex(AdmissionError, "file changed"):
                owner.validate()

    def test_owned_late_child_retains_session_after_context_return(self):
        parent, child = self.context.Pipe()
        process = self.context.Process(target=idle_worker, args=(child,))
        process.start()
        child.close()
        self.addCleanup(parent.close)
        self.addCleanup(self.stop, process)
        self.assertTrue(parent.poll(10))
        self.assertEqual(parent.recv(), "ready")
        with admission_session(self.catalog, _registry_path=self.registry) as owner:
            owner.retain_process(process)
        self.assertFalse(owner.closed)
        contender_process, pipe, result = self.launch()
        self.assertEqual(result, "busy")
        contender_process.join(5)
        parent.send("finish")
        process.join(5)
        self.assertEqual(process.exitcode, 0)
        self.assertTrue(owner.released.wait(5), "owned process exit did not release session")

    def test_reaper_start_failure_stays_owned_until_explicit_exit_reap(self):
        parent, child = self.context.Pipe()
        process = self.context.Process(target=idle_worker, args=(child,))
        process.start()
        child.close()
        self.addCleanup(parent.close)
        self.addCleanup(self.stop, process)
        self.assertTrue(parent.poll(10))
        self.assertEqual(parent.recv(), "ready")
        with admission_session(self.catalog, _registry_path=self.registry) as owner:
            with patch("threading.Thread.start", side_effect=RuntimeError("generated startup failure")):
                with self.assertRaises(RuntimeError):
                    owner.retain_process(process)
        self.assertFalse(owner.closed)
        self.assertEqual(owner.reap_owned_processes(), 1)
        contender_process, pipe, result = self.launch()
        self.assertEqual(result, "busy")
        contender_process.join(5)
        parent.send("finish")
        process.join(5)
        self.assertEqual(process.exitcode, 0)
        process.close()  # The retained duplicated sentinel survives caller close.
        self.assertEqual(owner.reap_owned_processes(), 0)
        self.assertEqual(owner.owned_processes, [])
        self.assertTrue(owner.released.is_set())

    def test_cleanup_reference_survives_invalidated_catalog(self):
        parent, child = self.context.Pipe()
        process = self.context.Process(target=idle_worker, args=(child,))
        process.start()
        child.close()
        self.addCleanup(parent.close)
        self.addCleanup(self.stop, process)
        self.assertTrue(parent.poll(10))
        parent.recv()
        with admission_session(self.catalog, _registry_path=self.registry) as owner:
            replacement = self.root / "replacement"
            replacement.write_bytes(b"replacement")
            replacement.replace(self.catalog)
            with self.assertRaises(AdmissionError):
                owner.validate()
            owner.retain_process(process)
        self.assertFalse(owner.closed)
        parent.send("finish")
        process.join(5)
        self.assertTrue(owner.released.wait(5))

    @unittest.skipUnless(hasattr(os, "fork"), "POSIX fork cleanup")
    def test_fork_closes_inherited_handles_without_unlocking_parent(self):
        with admission_session(self.catalog, _registry_path=self.registry) as owner:
            parent, child = multiprocessing.get_context("fork").Pipe()
            process = multiprocessing.get_context("fork").Process(
                target=contender, args=(str(self.catalog), str(self.registry), child))
            process.start()
            child.close()
            self.addCleanup(parent.close)
            self.addCleanup(self.stop, process)
            self.assertTrue(parent.poll(5))
            self.assertEqual(parent.recv(), "busy")
            process.join(5)
            owner.validate()
            spawned, pipe, result = self.launch()
            self.assertEqual(result, "busy")
            spawned.join(5)

    @unittest.skipIf(os.name == "nt", "POSIX account registry namespace")
    def test_home_and_xdg_do_not_select_registry(self):
        original = registry_path()
        with patch.dict(os.environ, {"HOME": str(self.root), "XDG_STATE_HOME": str(self.root / "else")}):
            self.assertEqual(registry_path(), original)

    @unittest.skipIf(os.name == "nt", "POSIX permission qualification")
    def test_unsafe_registry_refused_without_permission_repair(self):
        self.registry.mkdir(mode=0o755)
        with self.assertRaises(AdmissionError):
            with admission_session(self.catalog, _registry_path=self.registry):
                pass
        self.assertEqual(self.registry.stat().st_mode & 0o777, 0o755)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO qualification")
    def test_fifo_refuses_without_waiting_for_writer(self):
        fifo = self.root / "not-a-catalog"
        os.mkfifo(fifo)
        process, pipe, result = self.launch(fifo)
        self.assertEqual(result[0], "AdmissionError")
        process.join(5)
        self.assertEqual(process.exitcode, 0)


if __name__ == "__main__":
    unittest.main()

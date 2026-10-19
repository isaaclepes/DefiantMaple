"""Generated-fixture real-process admission races; no personal catalogs."""
from contextlib import closing, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from defiantmaple import catalog
from defiantmaple.admission import AdmissionError, LibraryInUseError, admission_session, key_bytes


FIXTURE_UUID = "00000000-0000-4000-8000-000000000047"
# Same v1 shape as test_catalog_migration.LEGACY_V1; independent of test import order.
LEGACY = """
CREATE TABLE assets (asset_id TEXT PRIMARY KEY,current_path TEXT NOT NULL UNIQUE,
media_type TEXT NOT NULL,sha256 TEXT NOT NULL,byte_size INTEGER NOT NULL,
workflow_state TEXT NOT NULL,discovered_at TEXT NOT NULL);
CREATE TABLE provenance (provenance_id TEXT PRIMARY KEY,asset_id TEXT NOT NULL,
source_kind TEXT NOT NULL,details_json TEXT NOT NULL,recorded_at TEXT NOT NULL);
INSERT INTO assets VALUES('fictional-asset','/fictional.png','image/png',
'fictional-hash',12,'needs_review','original time');
INSERT INTO provenance VALUES('fictional-provenance','fictional-asset',
'fictional-import','{"fictional":true}','original provenance time');
PRAGMA user_version=1;
"""


def snapshot(path):
    """Read-only full logical state, durability settings, integrity and byte hash."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return (hashlib.sha256(Path(path).read_bytes()).hexdigest(), tuple(db.iterdump()),
                tuple((name, db.execute(f"PRAGMA {name}").fetchall()) for name in
                      ("user_version", "application_id", "journal_mode", "synchronous",
                       "integrity_check", "foreign_key_check")))


def registry_identity(registry):
    return {p.name: (p.stat().st_dev, p.stat().st_ino, p.stat().st_size)
            for p in Path(registry).glob("*.lock")}


def require_command(pipe, command):
    if not pipe.poll(15):
        raise TimeoutError(f"No parent command: {command}")
    if pipe.recv() != command:
        raise RuntimeError(f"Unexpected parent command, expected {command}")


def race_process(path, registry, pipe, barrier, mode="open", cwd=None, package=None,
                 source=None, stage=None):
    """All instrumentation surrounds real operations; no native adapter replacement."""
    try:
        if cwd is not None:
            os.chdir(cwd)
        pipe.send({"event": "ready"})
        barrier.wait(15)
        wall, cpu = time.monotonic_ns(), time.process_time_ns()
        def event(name, **extra):
            pipe.send(dict(event=name, wall_ns=time.monotonic_ns() - wall,
                           cpu_ns=time.process_time_ns() - cpu, **extra))
        if mode in ("open", "create"):
            with admission_session(Path(path), create=mode == "create",
                                   _registry_path=Path(registry)) as owner:
                event("owned", created=owner.created)
                if mode == "create":
                    require_command(pipe, "initialize")
                    catalog.initialize(Path(path))
                    owner.ready()
                    event("initialized")
                require_command(pipe, "release")
        elif mode == "migration":
            from defiantmaple import __main__ as cli
            real_initialize = cli.initialize
            def synchronized_initialize(*args, **kwargs):
                event("owned")
                require_command(pipe, "initialize")
                result = real_initialize(*args, **kwargs)
                event("initialized", result=result)
                require_command(pipe, "release")
                return result
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(cli, "initialize", synchronized_initialize), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                status = cli.main(["init", path])
            if status:
                event("cli_refused", status=status, error=json.loads(stderr.getvalue())["error"])
            else:
                event("done", status=status, result=json.loads(stdout.getvalue()))
        elif mode == "restore":
            from defiantmaple import recovery
            real_read = recovery._read_package
            def synchronized_read(*args, **kwargs):
                # _restore_worker owns destination before its first package/stage read.
                event("owned")
                require_command(pipe, "initialize")
                return real_read(*args, **kwargs)
            with patch.object(recovery, "_read_package", synchronized_read):
                result = recovery._restore_worker(Path(package), Path(path), Path(stage),
                    (Path(source).parent / "cache",), Path(source), threading.Event())
            event("done", result=result)
        else:
            raise RuntimeError("Unknown fixture mode")
    except LibraryInUseError as exc:
        event("busy", error=str(exc))
    except BaseException as exc:
        pipe.send({"event": "error", "type": type(exc).__name__, "error": str(exc)})
    finally:
        pipe.close()


class AdversarialAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "catalog.sqlite3"
        with patch.object(catalog.uuid, "uuid4", return_value=uuid.UUID(FIXTURE_UUID)):
            catalog.initialize(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,"
                       "workflow_state,discovered_at) VALUES('fictional-asset','/fictional.png',"
                       "'image/png','fictional-hash',12,'needs_review','original time')")
            db.execute("INSERT INTO provenance VALUES('fictional-provenance','fictional-asset',"
                       "'fictional-import','{\"fictional\":true}','original provenance time')")
            db.commit()
        self.registry = self.root / "private-registry"
        self.context = multiprocessing.get_context("spawn")
        self.children = []
        self.addCleanup(self.cleanup_children)

    def cleanup_children(self):
        # Always release blocked harness participants, then contain only these children.
        for process, pipe, barrier in self.children:
            try:
                barrier.abort()
                if process.is_alive():
                    pipe.close()
                    process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                pipe.close()
                process.close()
            except (OSError, ValueError):
                pass

    def start(self, path=None, *, barrier=None, **kwargs):
        barrier = barrier or self.context.Barrier(2)
        pipe, child = self.context.Pipe()
        process = self.context.Process(target=race_process,
            args=(str(self.path if path is None else path), str(self.registry), child, barrier),
            kwargs=kwargs)
        process.start()
        child.close()
        self.children.append((process, pipe, barrier))
        self.assertEqual(self.receive(pipe, 15)["event"], "ready")
        return process, pipe, barrier

    def receive(self, pipe, seconds=2):
        self.assertTrue(pipe.poll(seconds), "generated contender response deadline expired")
        result = pipe.recv()
        self.assertNotEqual(result["event"], "error", result)
        return result

    def exited(self, process):
        process.join(5)
        self.assertEqual(process.exitcode, 0, "generated child did not exit cleanly")

    def refused(self, result, cli=False):
        print("admission-refusal " + json.dumps(dict(test=self.id(), **result), sort_keys=True),
              flush=True)
        self.assertEqual(result["event"], "cli_refused" if cli else "busy", result)
        self.assertIn("in use", result["error"], result)
        self.assertIn("close", result["error"].lower(), result)
        self.assertGreaterEqual(result["cpu_ns"], 0)
        self.assertLessEqual(result["wall_ns"], 250_000_000,
            f"Timing not accepted: preserve wall/CPU evidence and investigate scheduler stall: {result}")

    def probe(self, path=None, **kwargs):
        process, pipe, barrier = self.start(path, **kwargs)
        barrier.wait(15)
        return process, pipe, self.receive(pipe)

    def pair(self, path, *, mode="open", reverse=False, **kwargs):
        barrier = self.context.Barrier(3)
        handles = {}
        for label in (("B", "A") if reverse else ("A", "B")):
            specific = dict(kwargs)
            if mode == "restore":
                specific["stage"] = str(self.root / f"{label}.restore-stage")
            handles[label] = self.start(path, barrier=barrier, mode=mode, **specific)
        barrier.wait(15)
        results = {label: self.receive(handle[1]) for label, handle in handles.items()}
        winners = [label for label, result in results.items() if result["event"] == "owned"]
        self.assertEqual(len(winners), 1, results)
        winner = winners[0]
        loser = "B" if winner == "A" else "A"
        self.refused(results[loser], cli=mode == "migration")
        self.exited(handles[loser][0])
        return handles[winner], results[winner], loser

    def test_simultaneous_existing_open_both_launch_orders(self):
        before = snapshot(self.path)
        for reverse in (False, True):
            for trial in range(3):
                with self.subTest(reverse=reverse, trial=trial):
                    (process, pipe, _), _, _ = self.pair(self.path, reverse=reverse)
                    pipe.send("release")
                    self.exited(process)
                    with admission_session(self.path, _registry_path=self.registry):
                        pass
                    self.assertEqual(snapshot(self.path), before)

    def test_ready_contender_refusal_has_wall_and_cpu_measurements(self):
        before = snapshot(self.path)
        with admission_session(self.path, _registry_path=self.registry):
            locks = registry_identity(self.registry)
            process, _, result = self.probe()
            self.refused(result)
            self.exited(process)
            self.assertEqual(registry_identity(self.registry), locks)
        self.assertEqual(snapshot(self.path), before)

    def assert_alias_refused(self, alias, **kwargs):
        before = snapshot(self.path)
        with admission_session(self.path, _registry_path=self.registry) as owner:
            owner.validate()
            locks = registry_identity(self.registry)
            process, _, result = self.probe(alias, **kwargs)
            self.refused(result)
            self.exited(process)
            after = registry_identity(self.registry)
            self.assertEqual({name: after.get(name) for name in locks}, locks)
            # Equivalent filesystem spellings may have distinct pathname keys.
            # A contender retains that permanent empty lock before the shared
            # physical-file lock refuses; it must never replace an owner lock.
            alias_path = Path(alias)
            if not alias_path.is_absolute():
                alias_path = Path(kwargs.get("cwd", self.root)) / alias_path
            leaf = alias_path.resolve(strict=False).name
            encoded = leaf.encode("utf-16le", "surrogatepass") if os.name == "nt" else os.fsencode(leaf)
            alias_lock = hashlib.sha256(key_bytes("path", owner.parent.identity, encoded)).hexdigest() + ".lock"
            self.assertLessEqual(set(after) - set(locks), {alias_lock})
            for name in after:
                info = (self.registry / name).lstat()
                self.assertTrue(stat.S_ISREG(info.st_mode))
                self.assertEqual(info.st_size, 0)
                if os.name != "nt":
                    self.assertEqual(info.st_uid, os.getuid())
                    self.assertEqual(info.st_mode & 0o077, 0)
            owner.validate()
        self.assertEqual(snapshot(self.path), before)

    def test_relative_alias(self):
        self.assert_alias_refused(self.path.name, cwd=str(self.root))

    def test_symlink_alias(self):
        alias = self.root / "link.sqlite3"
        try:
            alias.symlink_to(self.path)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"Native symlink creation unavailable: {type(exc).__name__}: {exc}")
        self.assertTrue(alias.samefile(self.path))
        self.assert_alias_refused(alias)

    def test_case_equivalent_alias_on_host_filesystem(self):
        alias = self.root / "CATALOG.sqlite3"
        if not alias.exists() or not alias.samefile(self.path):
            self.skipTest("Generated filesystem is case-sensitive; no case-equivalent alias")
        self.assert_alias_refused(alias)

    def test_unicode_equivalent_alias_on_host_filesystem(self):
        composed = self.root / "caf\u00e9.sqlite3"
        composed.write_bytes(self.path.read_bytes())
        alias = self.root / "cafe\u0301.sqlite3"
        if not alias.exists() or not alias.samefile(composed):
            self.skipTest("Generated filesystem preserves distinct Unicode normalization names")
        self.path = composed
        self.assert_alias_refused(alias)

    def test_valid_same_uuid_copies_are_independent_owners(self):
        copy = self.root / "copy.sqlite3"
        shutil.copyfile(self.path, copy)
        self.assertFalse(copy.samefile(self.path))
        before = {path: snapshot(path) for path in (self.path, copy)}
        with admission_session(self.path, _registry_path=self.registry):
            process, pipe, result = self.probe(copy)
            self.assertEqual(result["event"], "owned")
            for path in (self.path, copy):
                blocked, _, refusal = self.probe(path)
                self.refused(refusal)
                self.exited(blocked)
            pipe.send("release")
            self.exited(process)
        self.assertEqual({path: snapshot(path) for path in before}, before)

    def test_create_race_third_opener_and_independent_existing_owner(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                self.assert_create_race(reverse)

    def assert_create_race(self, reverse):
        missing = self.root / f"missing-{reverse}.sqlite3"
        independent = self.root / f"independent-{reverse}.sqlite3"
        before = snapshot(self.path)
        catalog.initialize(independent)
        with admission_session(independent, _registry_path=self.registry) as existing:
            (process, pipe, _), result, _ = self.pair(missing, mode="create", reverse=reverse)
            self.assertTrue(result["created"])
            for path in (missing, self.path):
                blocked, _, result = self.probe(path)
                self.refused(result)
                self.exited(blocked)
            existing.validate()
            with closing(sqlite3.connect(independent)) as db:
                db.execute("CREATE TABLE fictional_work(value TEXT)")
                db.execute("INSERT INTO fictional_work VALUES('completed while gate held')")
                db.commit()
            pipe.send("initialize")
            self.assertEqual(self.receive(pipe)["event"], "initialized")
            blocked, _, result = self.probe(missing)
            self.refused(result)
            self.exited(blocked)
            independent_process, independent_pipe, result = self.probe(self.path)
            self.assertEqual(result["event"], "owned")
            independent_pipe.send("release")
            self.exited(independent_process)
            pipe.send("release")
            self.exited(process)
        with admission_session(missing, _registry_path=self.registry):
            self.assertEqual(catalog.initialize(missing)["schema_version"], 7)
        self.assertEqual(snapshot(self.path), before)
        with closing(sqlite3.connect(independent)) as db:
            self.assertEqual(db.execute("SELECT value FROM fictional_work").fetchall(),
                             [("completed while gate held",)])

    def test_missing_open_and_failed_initialization_release_without_deletion(self):
        missing = self.root / "failed.sqlite3"
        before = snapshot(self.path)
        with self.assertRaises(FileNotFoundError):
            with admission_session(missing, _registry_path=self.registry):
                pass
        self.assertFalse(missing.exists())
        with self.assertRaisesRegex(RuntimeError, "generated initialization failure"):
            with admission_session(missing, create=True, _registry_path=self.registry):
                with patch.object(catalog, "_execute_schema",
                                  side_effect=RuntimeError("generated initialization failure")):
                    catalog.initialize(missing)
        # An empty/uninitialized file may persist: never delete a possibly published file.
        self.assertTrue(missing.is_file())
        retained_identity = (missing.stat().st_dev, missing.stat().st_ino)
        with admission_session(missing, _registry_path=self.registry):
            self.assertEqual(catalog.initialize(missing)["schema_version"], 7)
        self.assertEqual((missing.stat().st_dev, missing.stat().st_ino), retained_identity)
        self.assertEqual(snapshot(self.path), before)

    def test_overlapping_thread_sessions_retain_until_last_exit(self):
        entered = [threading.Event(), threading.Event()]
        release = [threading.Event(), threading.Event()]
        exited = [threading.Event(), threading.Event()]
        owners, failures = [], []
        def borrower(index):
            try:
                with admission_session(self.path, _registry_path=self.registry) as owner:
                    owners.append(owner)
                    entered[index].set()
                    if not release[index].wait(15):
                        raise TimeoutError("Thread release not received")
            except BaseException as exc:
                failures.append(exc)
                entered[index].set()
            finally:
                exited[index].set()
        threads = [threading.Thread(target=borrower, args=(index,)) for index in range(2)]
        try:
            with admission_session(self.path, _registry_path=self.registry) as owner:
                for thread in threads:
                    thread.start()
                for event in entered:
                    self.assertTrue(event.wait(5))
                self.assertEqual(failures, [])
                self.assertEqual(len(owners), 2)
                self.assertTrue(all(nested is owner for nested in owners))
            for index in range(2):
                blocked, _, result = self.probe()
                self.refused(result)
                self.exited(blocked)
                release[index].set()
                self.assertTrue(exited[index].wait(5))
            self.assertEqual(failures, [])
            acquired, pipe, result = self.probe()
            self.assertEqual(result["event"], "owned")
            pipe.send("release")
            self.exited(acquired)
        finally:
            for event in release:
                event.set()
            for thread in threads:
                if thread.ident is not None:
                    thread.join(5)
                    self.assertFalse(thread.is_alive(), "Generated thread did not stop")

    def test_actual_cli_migration_race_preserves_original_backup(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                legacy = self.root / f"legacy-{reverse}.sqlite3"
                with closing(sqlite3.connect(legacy)) as db:
                    db.executescript(LEGACY)
                before = snapshot(legacy)
                directory_before = set(self.root.iterdir())
                (process, pipe, _), _, _ = self.pair(legacy, mode="migration", reverse=reverse)
                self.assertEqual(snapshot(legacy), before)
                self.assertEqual(set(self.root.iterdir()), directory_before)
                pipe.send("initialize")
                initialized = self.receive(pipe, 15)
                self.assertTrue(initialized["result"]["migrated"])
                backup = Path(initialized["result"]["backup_path"])
                self.assertEqual(snapshot(backup)[1:], before[1:])
                pipe.send("release")
                self.assertEqual(self.receive(pipe)["event"], "done")
                self.exited(process)
                with closing(sqlite3.connect(legacy)) as db:
                    self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 7)
                    self.assertEqual(db.execute("SELECT asset_id,current_path FROM assets").fetchall(),
                                     [("fictional-asset", "/fictional.png")])

    def test_actual_restore_worker_race_preserves_source_package_and_holds(self):
        from PIL import Image
        from defiantmaple.recovery import backup_metadata
        from defiantmaple.recovery_storage import private_local_parent
        from defiantmaple.sources import add_source
        # Match test_recovery: generated publication fixture on the checkout backing.
        temporary = tempfile.TemporaryDirectory(dir=Path(catalog.__file__).resolve().parents[1])
        self.addCleanup(temporary.cleanup)
        self.addCleanup(self.cleanup_children)  # Stop children before deleting their fixture.
        self.root = Path(temporary.name)
        try:
            with private_local_parent(self.root / ".native-capability-probe"):
                pass
        except ValueError as exc:
            if str(exc) in ("Recovery publication has no reviewed native adapter on this platform",
                            "Recovery requires a verified durable local filesystem"):
                self.skipTest(f"Real recovery publication capability unavailable: {exc}")
            raise
        source, package = self.root / "source.sqlite3", self.root / "fixture.dmbackup"
        media = self.root / "media"
        media.mkdir()
        image = media / "fictional.png"
        Image.new("RGB", (2, 2), "purple").save(image)
        with patch.object(catalog.uuid, "uuid4", return_value=uuid.UUID(FIXTURE_UUID)):
            catalog.initialize(source)
        registered = add_source(source, media, existing_file_policy="inbox")
        catalog.index_file(source, image, source_id=registered["source_id"])
        with admission_session(source) as source_owner:
            backup_metadata(source, package, cache_roots=(self.root / "cache",))
            before_source = snapshot(source)
            before_package = hashlib.sha256(package.read_bytes()).hexdigest()
            def image_state():
                digest = hashlib.sha256(image.read_bytes()).hexdigest()
                stat = image.stat()
                return digest, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
            before_image = image_state()
            for reverse in (False, True):
                with self.subTest(reverse=reverse):
                    destination = self.root / f"restored-{reverse}.sqlite3"
                    (process, pipe, _), _, loser = self.pair(destination, mode="restore",
                        reverse=reverse, package=str(package), source=str(source))
                    self.assertFalse(destination.exists())
                    self.assertFalse((self.root / f"{loser}.restore-stage").exists())
                    source_owner.validate()
                    self.assertEqual(snapshot(source), before_source)
                    pipe.send("initialize")
                    result = self.receive(pipe, 30)
                    self.assertEqual(result["event"], "done", result)
                    self.assertEqual(result["result"]["restored"]["state"], "restore_pending")
                    self.exited(process)
                    with closing(sqlite3.connect(source)) as original, \
                            closing(sqlite3.connect(destination)) as restored:
                        self.assertEqual(restored.execute("PRAGMA user_version").fetchone(), (7,))
                        self.assertEqual(catalog.catalog_state(restored), "restore_pending")
                        for table in ("assets", "provenance", "tags", "collections",
                                      "collection_members", "library_identity"):
                            self.assertEqual(restored.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall(),
                                             original.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall())
                        source_id, enabled, health, detail = restored.execute(
                            "SELECT source_id,enabled,health,health_detail FROM sources").fetchone()
                        self.assertEqual((source_id, enabled, health),
                                         (registered["source_id"], 0, "paused"))
                        self.assertTrue(catalog.is_restored_root_review_detail(
                            detail, source_id, str(media)))
                        self.assertEqual(restored.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
                    self.assertEqual(snapshot(source), before_source)
                    self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(), before_package)
                    self.assertEqual(image_state(), before_image)
                    self.assertFalse((self.root / "cache").exists())
                    # Real publish removes its staged name after the final binding.
                    winner = "B" if loser == "A" else "A"
                    self.assertFalse((self.root / f"{winner}.restore-stage").exists())


if __name__ == "__main__":
    unittest.main()

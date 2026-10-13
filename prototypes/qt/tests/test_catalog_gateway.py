"""Generated rollback-journal tests for the dormant Qt catalog gateway."""
from __future__ import annotations

import sqlite3
from contextlib import closing
import tempfile
import threading
import time
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QThread, QTimer, Slot

from defiantmaple.catalog import connect, initialize
from defiantmaple import curation
from prototypes.qt.gallery_filters import (
    CatalogGateway, CatalogRequest, OperationSpec, RequestClass,
)


_HOLDS: dict[str, tuple[threading.Event, threading.Event]] = {}


def _asset_count(database_or_connection):
    if isinstance(database_or_connection, Path):
        with closing(sqlite3.connect(database_or_connection)) as db:
            return db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    return database_or_connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0]


def hold_read(db, context, key):
    entered, release = _HOLDS[key]
    _asset_count(db)
    entered.set()
    # Deliberately simulate a native read that cannot observe cancellation yet.
    release.wait(3)
    context.check()
    return "read finished"


def count_assets(db, context):
    context.check()
    return _asset_count(db)


def unexpected_failure(_db, _context):
    raise AssertionError("Generated handler failure")


def oversized_result(_db, _context):
    return ["x" * 4_096 for _ in range(700)]


def slow_large_legacy_result(_db, context):
    time.sleep(.04)
    context.check()
    return ["x" * 70_000] + ["y" * 4_096 for _ in range(1_100)]


def slow_bounded_result(_db, context):
    time.sleep(.04)
    context.check()
    return "should not publish"


def legacy_unsafe_result(_db, _context):
    return {"items": [QObject()]}


def ends_read_snapshot(db, _context):
    db.execute("SELECT COUNT(*) FROM assets").fetchone()
    db.rollback()
    return "incorrectly finished"


def set_rating(database, _context, expected_revision):
    return curation.set_curation(database, "generated-asset", rating=5,
                                 favorite=True, expected_revision=expected_revision)


def hold_write(database, _context, key, leased_path=None):
    entered, release = _HOLDS[key]
    entered.set()
    release.wait(3)
    if leased_path is not None and not Path(leased_path).is_file():
        raise ValueError("Captured temporary input was removed before write finished")
    return curation.set_curation(database, "generated-asset", rating=4,
                                 favorite=False, expected_revision=0)


def write_with_large_result(database, _context):
    curation.set_curation(database, "generated-asset", rating=3,
                          favorite=False, expected_revision=0)
    return ["x" * 4_096 for _ in range(700)]


def write_then_raise(database, _context):
    curation.set_curation(database, "generated-asset", rating=2,
                          favorite=False, expected_revision=0)
    raise RuntimeError("Generated failure after commit")


OPERATIONS = {
    "hold_read": OperationSpec(False, hold_read),
    "count": OperationSpec(False, count_assets),
    "unexpected": OperationSpec(False, unexpected_failure),
    "oversized": OperationSpec(False, oversized_result),
    "slow_large_legacy": OperationSpec(False, slow_large_legacy_result),
    "slow_bounded": OperationSpec(False, slow_bounded_result),
    "legacy_unsafe": OperationSpec(False, legacy_unsafe_result),
    "ends_snapshot": OperationSpec(False, ends_read_snapshot),
    "rate": OperationSpec(True, set_rating),
    "hold_write": OperationSpec(True, hold_write),
    "write_large": OperationSpec(True, write_with_large_result),
    "write_then_raise": OperationSpec(True, write_then_raise),
}


class Recorder(QObject):
    def __init__(self):
        super().__init__()
        self.replies = []
        self.threads = []
        self.failures = []
        self.gateway = None
        self.auto_ack = True

    @Slot(object)
    def received(self, reply):
        self.replies.append(reply)
        self.threads.append(QThread.currentThread())
        if reply.category == RequestClass.MUTATION and self.auto_ack:
            acknowledgement = self.gateway.acknowledge_write(reply.request_id)
            if acknowledgement.resources:
                raise AssertionError("Test recorder must explicitly clean retained resources")

    @Slot(str)
    def failed(self, message):
        self.failures.append(message)


class CatalogGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gallery-gateway-generated-")
        self.database = Path(self.temp.name) / "catalog.sqlite3"
        initialize(self.database)
        with connect(self.database) as db:
            db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                       "VALUES(?,?,?,?,?)",
                       ("generated-asset", str(Path(self.temp.name) / "placeholder.png"),
                        "image/png", "generated-digest", 0))
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=DELETE").fetchone()[0], "delete")
        self.gateways = []
        self.keys = []

    def tearDown(self):
        for key in self.keys:
            _HOLDS[key][1].set()
        for gateway in self.gateways:
            gateway.request_close()
        self._until(lambda: all(gateway.close_complete for gateway in self.gateways), 4)
        for key in self.keys:
            _HOLDS.pop(key, None)
        self.temp.cleanup()

    def _hold(self, label):
        key = f"{id(self)}-{label}"
        _HOLDS[key] = (threading.Event(), threading.Event())
        self.keys.append(key)
        return key, *_HOLDS[key]

    def _gateway(self, *, start=True):
        gateway = CatalogGateway(self.database, OPERATIONS)
        recorder = Recorder()
        recorder.gateway = gateway
        gateway.completed.connect(recorder.received)
        gateway.failed.connect(recorder.failed)
        self.gateways.append(gateway)
        if start:
            gateway.start()
        return gateway, recorder

    def _until(self, predicate, seconds=3):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertTrue(predicate(), "Qt event-loop result did not arrive")

    @staticmethod
    def _reply(recorder, request_id):
        return next(reply for reply in recorder.replies if reply.request_id == request_id)

    def test_rollback_read_write_keeps_qt_heartbeat_and_core_result(self):
        gateway, recorder = self._gateway()
        key, entered, release = self._hold("read")
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.APPLY,
                                                      "hold_read", (key,))).accepted)
        self.assertTrue(entered.wait(2))

        ticks = []
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(time.monotonic()))
        timer.start()
        started = time.monotonic()
        self.assertTrue(gateway.submit(CatalogRequest(2, RequestClass.MUTATION,
                                                      "rate", (0,))).accepted)
        self.assertLess(time.monotonic() - started, .05)
        self._until(lambda: len(ticks) >= 6, 1)
        self.assertFalse(any(reply.request_id == 2 for reply in recorder.replies))
        release.set()
        self._until(lambda: any(reply.request_id == 2 for reply in recorder.replies))
        timer.stop()

        self.assertEqual(self._reply(recorder, 1).status, "cancelled")
        result = self._reply(recorder, 2)
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.value["changed"])
        self.assertNotEqual(result.worker_thread_id, threading.get_ident())
        self.assertTrue(all(thread is self.app.thread() for thread in recorder.threads))
        with connect(self.database) as db:
            row = db.execute("SELECT rating,favorite,revision FROM assets WHERE asset_id=?",
                             ("generated-asset",)).fetchone()
        self.assertEqual(tuple(row), (5, 1, 1))
        gateway.request_close()
        self._until(lambda: gateway.close_complete)

    def test_external_writer_waits_off_gui_and_next_snapshot_sees_change(self):
        gateway, recorder = self._gateway()
        key, entered, release = self._hold("external")
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.APPLY,
                                                      "hold_read", (key,))).accepted)
        self.assertTrue(entered.wait(2))
        write_started = threading.Event()
        write_done = threading.Event()
        write_errors = []

        def independent_writer():
            try:
                with closing(sqlite3.connect(self.database)) as db:
                    db.execute("UPDATE assets SET workflow_state='reviewed' WHERE asset_id=?",
                               ("generated-asset",))
                    write_started.set()
                    db.commit()
            except Exception as exc:
                write_errors.append(exc)
            finally:
                write_done.set()

        writer = threading.Thread(target=independent_writer)
        writer.start()
        self.assertTrue(write_started.wait(2))
        ticks = []
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        self._until(lambda: len(ticks) >= 5, 1)
        self.assertFalse(write_done.is_set())
        release.set()
        self._until(lambda: write_done.is_set() and
                    any(reply.request_id == 1 for reply in recorder.replies))
        timer.stop()
        writer.join(timeout=1)
        self.assertFalse(writer.is_alive())
        self.assertFalse(write_errors)
        before_version = self._reply(recorder, 1).data_version
        self.assertTrue(gateway.submit(CatalogRequest(2, RequestClass.APPLY, "count")).accepted)
        self._until(lambda: any(reply.request_id == 2 for reply in recorder.replies))
        self.assertGreater(self._reply(recorder, 2).data_version, before_version)
        with connect(self.database) as db:
            state = db.execute("SELECT workflow_state FROM assets WHERE asset_id=?",
                               ("generated-asset",)).fetchone()[0]
        self.assertEqual(state, "reviewed")

    def test_legacy_service_does_not_extend_its_read_lock_during_non_db_work(self):
        gateway, recorder = self._gateway()
        key, entered, release = self._hold("legacy-after-service")
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.LEGACY,
                                                      "hold_read", (key,),
                                                      context="taxonomy")).accepted)
        self.assertTrue(entered.wait(2))
        write_done = threading.Event()
        write_errors = []

        def external_writer():
            try:
                with closing(sqlite3.connect(self.database)) as db:
                    db.execute("UPDATE assets SET workflow_state='reviewed' WHERE asset_id=?",
                               ("generated-asset",))
                    db.commit()
            except Exception as exc:
                write_errors.append(exc)
            finally:
                write_done.set()

        writer = threading.Thread(target=external_writer)
        writer.start()
        ticks = []
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        try:
            self._until(lambda: write_done.is_set() and len(ticks) >= 5, 1)
            self.assertFalse(release.is_set())
        finally:
            timer.stop()
            release.set()
            writer.join(timeout=2)
        self.assertFalse(writer.is_alive())
        self.assertFalse(write_errors)
        self._until(lambda: any(reply.request_id == 1 for reply in recorder.replies))
        self.assertEqual(self._reply(recorder, 1).status, "ok")
        self.assertIsNone(self._reply(recorder, 1).data_version)

    def test_mutation_priority_and_stale_revision_refusal(self):
        gateway, recorder = self._gateway()
        key, entered, release = self._hold("priority")
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.PAGE,
                                                      "hold_read", (key,), context="page-0")).accepted)
        self.assertTrue(entered.wait(2))
        self.assertTrue(gateway.submit(CatalogRequest(2, RequestClass.LEGACY,
                                                      "count", context="source-list")).accepted)
        self.assertTrue(gateway.submit(CatalogRequest(3, RequestClass.MUTATION,
                                                      "rate", (77,))).accepted)
        self.assertFalse(gateway.submit(CatalogRequest(4, RequestClass.MUTATION,
                                                       "rate", (0,))).accepted)
        release.set()
        self._until(lambda: len(recorder.replies) >= 3)
        self.assertEqual([reply.request_id for reply in recorder.replies], [1, 3, 2])
        self.assertEqual(self._reply(recorder, 1).status, "cancelled")
        self.assertEqual(self._reply(recorder, 3).status, "outcome_unknown")
        self.assertIn("changed since", self._reply(recorder, 3).message.lower())
        self.assertEqual(self._reply(recorder, 2).value, 1)
        with connect(self.database) as db:
            row = db.execute("SELECT rating,favorite,revision FROM assets WHERE asset_id=?",
                             ("generated-asset",)).fetchone()
        self.assertEqual(tuple(row), (None, 0, 0))

    def test_fixed_pending_queue_and_snapshot_version(self):
        gateway, recorder = self._gateway(start=False)
        for index in range(4):
            self.assertTrue(gateway.submit(CatalogRequest(index + 1, RequestClass.LEGACY,
                                                          "count", context=f"editor-{index}")).accepted)
        self.assertEqual(gateway.pending_count, 4)
        self.assertFalse(gateway.submit(CatalogRequest(5, RequestClass.LEGACY,
                                                       "count", context="editor-4")).accepted)
        self.assertTrue(gateway.submit(CatalogRequest(6, RequestClass.LEGACY,
                                                      "count", context="editor-0")).accepted)
        self.assertEqual(gateway.pending_count, 4)
        self.assertTrue(gateway.submit(CatalogRequest(7, RequestClass.PAGE,
                                                      "count", context="page-0")).accepted)
        self.assertTrue(gateway.submit(CatalogRequest(8, RequestClass.PAGE,
                                                      "count", context="page-1")).accepted)
        self.assertTrue(gateway.submit(CatalogRequest(9, RequestClass.PAGE,
                                                      "count", context="page-2")).accepted)
        self.assertEqual(gateway.pending_count, 6)
        self._until(lambda: {1, 7}.issubset({reply.request_id for reply in recorder.replies}))
        self.assertEqual(self._reply(recorder, 1).status, "superseded")
        self.assertEqual(self._reply(recorder, 7).status, "superseded")
        gateway.start()
        self._until(lambda: any(reply.request_id == 9 for reply in recorder.replies))
        self.assertEqual(self._reply(recorder, 9).status, "ok")
        self.assertIsInstance(self._reply(recorder, 9).data_version, int)
        self.assertEqual(len(self._reply(recorder, 9).file_identity), 2)

    def test_close_retains_active_write_until_actual_finish(self):
        gateway, recorder = self._gateway()
        key, entered, release = self._hold("write")
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.MUTATION,
                                                      "hold_write", (key,))).accepted)
        self.assertTrue(entered.wait(2))
        self.assertFalse(gateway.cancel_pending(1))
        gateway.request_close()
        self.assertFalse(gateway.close_complete)
        self.assertFalse(gateway.submit(CatalogRequest(2, RequestClass.APPLY,
                                                       "count")).accepted)
        release.set()
        self._until(lambda: gateway.close_complete)
        self._until(lambda: any(reply.request_id == 1 for reply in recorder.replies))
        self.assertEqual(self._reply(recorder, 1).status, "ok")
        with connect(self.database) as db:
            row = db.execute("SELECT rating,revision FROM assets WHERE asset_id=?",
                             ("generated-asset",)).fetchone()
        self.assertEqual(tuple(row), (4, 1))

    def test_write_result_requires_gui_ack_before_next_write(self):
        gateway, recorder = self._gateway()
        recorder.auto_ack = False
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.MUTATION,
                                                      "rate", (0,))).accepted)
        self._until(lambda: any(reply.request_id == 1 for reply in recorder.replies))
        self.assertEqual(self._reply(recorder, 1).status, "ok")
        self.assertFalse(gateway.submit(CatalogRequest(2, RequestClass.MUTATION,
                                                       "rate", (0,))).accepted)
        self.assertTrue(gateway.acknowledge_write(1).accepted)
        self.assertFalse(gateway.acknowledge_write(1).accepted)
        self.assertTrue(gateway.submit(CatalogRequest(3, RequestClass.MUTATION,
                                                      "rate", (0,))).accepted)
        self._until(lambda: any(reply.request_id == 3 for reply in recorder.replies))
        self.assertEqual(self._reply(recorder, 3).status, "outcome_unknown")
        self.assertTrue(gateway.acknowledge_write(3).accepted)

    def test_retained_request_resource_survives_dialog_style_close(self):
        gateway, recorder = self._gateway()
        recorder.auto_ack = False
        key, entered, release = self._hold("leased-write")
        owned = tempfile.TemporaryDirectory(prefix="gateway-owned-input-")
        input_path = Path(owned.name) / "captured.txt"
        input_path.write_text("generated", encoding="utf-8")
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.MUTATION,
                                                      "hold_write", (key, input_path)),
                                       retain=(owned,)).accepted)
        del owned  # The dialog-style caller releases its own reference.
        self.assertTrue(entered.wait(2))
        gateway.request_close()
        self.assertTrue(input_path.exists())
        self.assertFalse(gateway.close_complete)
        release.set()
        self._until(lambda: any(reply.request_id == 1 for reply in recorder.replies))
        self.assertEqual(self._reply(recorder, 1).status, "ok")
        self.assertTrue(input_path.exists())
        self.assertFalse(gateway.close_complete)  # Result still owns the lease.
        acknowledgement = gateway.acknowledge_result(1)
        self.assertTrue(acknowledgement.accepted)
        self.assertEqual(len(acknowledgement.resources), 1)
        acknowledgement.resources[0].cleanup()
        self._until(lambda: gateway.close_complete)
        self.assertFalse(input_path.exists())

    def test_close_cancels_queued_write_without_late_dispatch(self):
        gateway, recorder = self._gateway()
        recorder.auto_ack = False
        key, entered, release = self._hold("cancel-queued")
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.APPLY,
                                                      "hold_read", (key,))).accepted)
        self.assertTrue(entered.wait(2))
        owned = tempfile.TemporaryDirectory(prefix="gateway-queued-input-")
        input_path = Path(owned.name) / "captured.txt"
        input_path.write_text("generated", encoding="utf-8")
        self.assertTrue(gateway.submit(CatalogRequest(2, RequestClass.MUTATION,
                                                      "hold_write", (key, input_path)),
                                       retain=(owned,)).accepted)
        del owned
        gateway.request_close()
        self._until(lambda: any(reply.request_id == 2 for reply in recorder.replies))
        self.assertEqual(self._reply(recorder, 2).status, "cancelled")
        self.assertTrue(input_path.exists())
        self.assertFalse(gateway.close_complete)
        acknowledgement = gateway.acknowledge_result(2)
        self.assertTrue(acknowledgement.accepted)
        self.assertEqual(len(acknowledgement.resources), 1)
        acknowledgement.resources[0].cleanup()
        release.set()
        self._until(lambda: gateway.close_complete)
        self.assertFalse(input_path.exists())
        with connect(self.database) as db:
            row = db.execute("SELECT rating,revision FROM assets WHERE asset_id=?",
                             ("generated-asset",)).fetchone()
        self.assertEqual(tuple(row), (None, 0))

    def test_request_payload_refuses_qobject(self):
        gateway, _recorder = self._gateway(start=False)
        with self.assertRaises(TypeError):
            gateway.submit(CatalogRequest(1, RequestClass.LEGACY, "count",
                                          args=(QObject(),), context="bad"))
        with self.assertRaises(ValueError):
            gateway.submit(CatalogRequest(2, RequestClass.LEGACY, "count",
                                          args=(tuple("x" * 3_000 for _ in range(800)),),
                                          context="too-large"))
        gateway.request_close()
        self.assertTrue(gateway.close_complete)

    def test_handler_exception_and_large_reply_are_visible_refusals(self):
        gateway, recorder = self._gateway()
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.APPLY,
                                                      "unexpected")).accepted)
        self.assertTrue(gateway.submit(CatalogRequest(2, RequestClass.DETAIL,
                                                      "oversized")).accepted)
        self._until(lambda: len(recorder.replies) >= 2)
        self.assertEqual(self._reply(recorder, 1).status, "error")
        self.assertIn("AssertionError", self._reply(recorder, 1).message)
        self.assertEqual(self._reply(recorder, 2).status, "error")
        self.assertIn("size bound", self._reply(recorder, 2).message)
        self.assertFalse(recorder.failures)

    def test_legacy_result_keeps_duration_and_size_while_gallery_stays_bounded(self):
        gateway, recorder = self._gateway()
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.LEGACY,
                                                      "slow_large_legacy", context="taxonomy",
                                                      deadline_seconds=.001)).accepted)
        self._until(lambda: any(reply.request_id == 1 for reply in recorder.replies))
        legacy = self._reply(recorder, 1)
        self.assertEqual(legacy.status, "ok")
        self.assertEqual(len(legacy.value), 1_101)
        self.assertEqual(len(legacy.value[0]), 70_000)
        self.assertTrue(gateway.submit(CatalogRequest(2, RequestClass.DETAIL,
                                                      "slow_bounded",
                                                      deadline_seconds=.001)).accepted)
        self._until(lambda: any(reply.request_id == 2 for reply in recorder.replies))
        self.assertEqual(self._reply(recorder, 2).status, "deadline")
        self.assertTrue(gateway.submit(CatalogRequest(3, RequestClass.LEGACY,
                                                      "legacy_unsafe",
                                                      context="unsafe")).accepted)
        self._until(lambda: any(reply.request_id == 3 for reply in recorder.replies))
        self.assertEqual(self._reply(recorder, 3).status, "error")
        self.assertIn("QObject", self._reply(recorder, 3).message)

    def test_startup_failure_drains_pending_without_dispatch(self):
        gateway, recorder = self._gateway(start=False)
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.LEGACY,
                                                      "count", context="startup-read")).accepted)
        self.assertTrue(gateway.submit(CatalogRequest(2, RequestClass.MUTATION,
                                                      "rate", (0,))).accepted)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("PRAGMA user_version=99")
        gateway.start()
        self._until(lambda: len(recorder.replies) == 2 and len(recorder.failures) == 1)
        self.assertEqual([reply.status for reply in recorder.replies], ["error", "error"])
        self.assertIn("Unsupported catalog schema", recorder.failures[0])
        self._until(lambda: gateway.close_complete)
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute("SELECT rating,revision FROM assets WHERE asset_id=?",
                             ("generated-asset",)).fetchone()
        self.assertEqual(tuple(row), (None, 0))

    def test_mutation_invalidates_queued_gallery_reads(self):
        gateway, recorder = self._gateway()
        key, entered, release = self._hold("invalidate")
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.LEGACY,
                                                      "hold_read", (key,), context="active")).accepted)
        self.assertTrue(entered.wait(2))
        for request in (
            CatalogRequest(2, RequestClass.APPLY, "count"),
            CatalogRequest(3, RequestClass.PAGE, "count", context="page-0"),
            CatalogRequest(4, RequestClass.RANK, "count"),
            CatalogRequest(5, RequestClass.DETAIL, "count"),
            CatalogRequest(6, RequestClass.TAXONOMY, "count"),
            CatalogRequest(7, RequestClass.SOURCE, "count"),
        ):
            self.assertTrue(gateway.submit(request).accepted)
        self.assertTrue(gateway.submit(CatalogRequest(8, RequestClass.MUTATION,
                                                      "rate", (0,))).accepted)
        self.assertFalse(gateway.submit(CatalogRequest(9, RequestClass.APPLY,
                                                       "count")).accepted)
        self._until(lambda: {2, 3, 4, 5, 6, 7}.issubset(
            {reply.request_id for reply in recorder.replies}))
        self.assertTrue(all(self._reply(recorder, request_id).status == "cancelled"
                            for request_id in range(2, 8)))
        self.assertEqual(gateway.pending_count, 1)
        release.set()
        self._until(lambda: any(reply.request_id == 8 for reply in recorder.replies))
        self.assertEqual(self._reply(recorder, 8).status, "ok")

    def test_read_handler_cannot_publish_after_ending_snapshot(self):
        gateway, recorder = self._gateway()
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.APPLY,
                                                      "ends_snapshot")).accepted)
        self._until(lambda: any(reply.request_id == 1 for reply in recorder.replies))
        self.assertEqual(self._reply(recorder, 1).status, "error")
        self.assertIn("ended its snapshot", self._reply(recorder, 1).message)
        self.assertIsNone(self._reply(recorder, 1).data_version)

    def test_completed_write_with_oversized_reply_never_claims_failed_edit(self):
        gateway, recorder = self._gateway()
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.MUTATION,
                                                      "write_large")).accepted)
        self._until(lambda: any(reply.request_id == 1 for reply in recorder.replies))
        reply = self._reply(recorder, 1)
        self.assertEqual(reply.status, "completed_no_payload")
        self.assertIn("Reload catalog", reply.message)
        self.assertIsNone(reply.value)
        with connect(self.database) as db:
            row = db.execute("SELECT rating,revision FROM assets WHERE asset_id=?",
                             ("generated-asset",)).fetchone()
        self.assertEqual(tuple(row), (3, 1))

    def test_committed_write_then_exception_requires_reload(self):
        gateway, recorder = self._gateway()
        self.assertTrue(gateway.submit(CatalogRequest(1, RequestClass.MUTATION,
                                                      "write_then_raise")).accepted)
        self._until(lambda: any(reply.request_id == 1 for reply in recorder.replies))
        reply = self._reply(recorder, 1)
        self.assertEqual(reply.status, "outcome_unknown")
        self.assertIn("RuntimeError: Generated failure after commit", reply.message)
        self.assertIn("reload catalog state", reply.message)
        with connect(self.database) as db:
            row = db.execute("SELECT rating,revision FROM assets WHERE asset_id=?",
                             ("generated-asset",)).fetchone()
        self.assertEqual(tuple(row), (2, 1))


if __name__ == "__main__":
    unittest.main()

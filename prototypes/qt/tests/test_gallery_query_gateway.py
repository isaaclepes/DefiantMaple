"""Actual Qt gateway transport and catalog-incarnation tests for gallery reads."""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from PySide6.QtCore import QCoreApplication, QObject, QThread, Slot

from defiantmaple.catalog import initialize
from defiantmaple.gallery_query import (
    GalleryQuery, count_first_page, detail_for_asset, later_page, rank_for_asset,
)
from prototypes.qt.gallery_filters import (
    CatalogGateway, CatalogRequest, OperationSpec, RequestClass,
)


def oversized_reply(_db, _context):
    return ["x" * 4_096 for _ in range(700)]


def too_many_reply_nodes(_db, _context):
    return tuple(tuple(range(40)) for _ in range(500))


_WRITE_DISPATCHED = threading.Event()
_LEGACY_DISPATCHED = threading.Event()


def captured_write(database, _context):
    _WRITE_DISPATCHED.set()
    with closing(sqlite3.connect(database)) as db:
        db.execute("UPDATE assets SET workflow_state='reviewed' WHERE asset_id='replacement-only'")
        db.commit()
    return "updated"


def captured_legacy_read(database, _context):
    _LEGACY_DISPATCHED.set()
    with closing(sqlite3.connect(database)) as db:
        return db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]


OPERATIONS = {
    "initial": OperationSpec(False, count_first_page),
    "page": OperationSpec(False, later_page),
    "rank": OperationSpec(False, rank_for_asset),
    "detail": OperationSpec(False, detail_for_asset),
    "large": OperationSpec(False, oversized_reply),
    "many_nodes": OperationSpec(False, too_many_reply_nodes),
    "captured_write": OperationSpec(True, captured_write),
    "captured_legacy": OperationSpec(False, captured_legacy_read),
}


class Recorder(QObject):
    def __init__(self):
        super().__init__()
        self.replies = []
        self.threads = []
        self.failures = []

    @Slot(object)
    def received(self, reply):
        self.replies.append(reply)
        self.threads.append(QThread.currentThread())

    @Slot(str)
    def failed(self, message):
        self.failures.append(message)


class InjectedIdentityGateway(CatalogGateway):
    """Portable mismatch injection without replacing an open SQLite file."""

    def __init__(self, *args, **kwargs):
        self.inject_mismatch = threading.Event()
        super().__init__(*args, **kwargs)

    def _path_identity(self):
        identity = super()._path_identity()
        return (identity[0], identity[1] + 1) if self.inject_mismatch.is_set() else identity


class GalleryGatewayQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gallery-query-gateway-generated-")
        self.database = Path(self.temp.name) / "catalog.sqlite3"
        initialize(self.database)
        with closing(sqlite3.connect(self.database)) as db:
            db.executemany(
                "INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,discovered_at) "
                "VALUES(?,?,?,?,?,?)",
                ((f"asset-{number:04d}", f"/generated/{number:04d}.png", "image/png",
                  "generated-digest", 0, "2026-01-01") for number in range(257)),
            )
            db.commit()
        self.gateways = []

    def tearDown(self):
        for gateway in self.gateways:
            gateway.request_close()
        self._until(lambda: all(gateway.close_complete for gateway in self.gateways), 4)
        self.temp.cleanup()

    def _gateway(self, gateway_type=CatalogGateway):
        gateway = gateway_type(self.database, OPERATIONS)
        recorder = Recorder()
        gateway.completed.connect(recorder.received)
        gateway.failed.connect(recorder.failed)
        self.gateways.append(gateway)
        gateway.start()
        return gateway, recorder

    def _until(self, predicate, seconds=3):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertTrue(predicate(), "Qt gateway result did not arrive")

    @staticmethod
    def _reply(recorder, request_id):
        return next(reply for reply in recorder.replies if reply.request_id == request_id)

    def _initial(self, gateway, recorder):
        query = GalleryQuery()
        self.assertTrue(gateway.submit(CatalogRequest(
            1, RequestClass.APPLY, "initial", (query, 1, "reader-incarnation-1"),
            generation=1)).accepted)
        self._until(lambda: any(reply.request_id == 1 for reply in recorder.replies))
        result = self._reply(recorder, 1)
        self.assertEqual(result.status, "ok", result.message)
        self.assertEqual(result.value.token.data_version, result.data_version)
        self.assertEqual(result.value.token.file_identity, result.file_identity)
        return query, result.value

    def test_full_page_actual_context_later_rank_detail_and_reply_caps(self):
        for mode in ("delete", "wal"):
            with self.subTest(mode=mode):
                with closing(sqlite3.connect(self.database)) as db:
                    self.assertEqual(db.execute(f"PRAGMA journal_mode={mode}").fetchone()[0], mode)
                gateway, recorder = self._gateway()
                query, first = self._initial(gateway, recorder)
                self.assertEqual(first.token.count, 257)
                self.assertEqual(len(first.rows), 256)
                self.assertEqual(first.rows[0]["asset_id"], "asset-0000")
                self.assertEqual(first.rows[-1]["asset_id"], "asset-0255")
                self.assertTrue(all(reply_thread is self.app.thread() for reply_thread in recorder.threads))
                with self.assertRaises(ValueError):
                    gateway.submit(CatalogRequest(
                        2, RequestClass.DETAIL, "large",
                        args=(tuple(tuple(range(100)) for _ in range(100)),)))
                self.assertTrue(gateway.submit(CatalogRequest(
                    3, RequestClass.PAGE, "page",
                    args=(query, first.token, "reader-incarnation-1", 1, 1),
                    context="page-1", generation=1)).accepted)
                self._until(lambda: any(reply.request_id == 3 for reply in recorder.replies))
                page = self._reply(recorder, 3)
                self.assertEqual(page.status, "ok", page.message)
                self.assertEqual([row["asset_id"] for row in page.value.rows], ["asset-0256"])
                self.assertTrue(gateway.submit(CatalogRequest(
                    4, RequestClass.RANK, "rank",
                    args=(query, first.token, "reader-incarnation-1", 1, "asset-0256"),
                    generation=1)).accepted)
                self._until(lambda: any(reply.request_id == 4 for reply in recorder.replies))
                self.assertEqual(self._reply(recorder, 4).value.row, 256)
                self.assertTrue(gateway.submit(CatalogRequest(
                    5, RequestClass.DETAIL, "detail",
                    args=(query, first.token, "reader-incarnation-1", 1,
                          "asset-0000", first.rows[0]["revision"]), generation=1)).accepted)
                self._until(lambda: any(reply.request_id == 5 for reply in recorder.replies))
                detail = self._reply(recorder, 5)
                self.assertEqual(detail.status, "ok", detail.message)
                self.assertEqual(detail.value.value["asset"]["asset_id"], "asset-0000")
                self.assertTrue(gateway.submit(CatalogRequest(
                    6, RequestClass.DETAIL, "large", generation=1)).accepted)
                self.assertTrue(gateway.submit(CatalogRequest(
                    7, RequestClass.RANK, "many_nodes", generation=1)).accepted)
                self._until(lambda: {6, 7}.issubset({reply.request_id for reply in recorder.replies}))
                for request_id in (6, 7):
                    reply = self._reply(recorder, request_id)
                    self.assertEqual(reply.status, "error")
                    self.assertIn("size bound", reply.message)
                gateway.request_close()
                self._until(lambda: gateway.close_complete)

    def test_atomic_file_replacement_refuses_old_connection_rows(self):
        gateway, recorder = self._gateway()
        query, first = self._initial(gateway, recorder)
        replacement = Path(self.temp.name) / "replacement.sqlite3"
        initialize(replacement)
        with closing(sqlite3.connect(replacement)) as db:
            db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                       "VALUES('replacement-only','/replacement.png','image/png','digest',0)")
            db.commit()
        try:
            os.replace(replacement, self.database)
        except OSError as exc:
            self.skipTest(f"Atomic replacement of an open SQLite file unavailable: {exc}")
        self.assertTrue(gateway.submit(CatalogRequest(
            2, RequestClass.PAGE, "page",
            args=(query, first.token, "reader-incarnation-1", 1, 1),
            context="page-1", generation=1)).accepted)
        self._until(lambda: any(reply.request_id == 2 for reply in recorder.replies))
        refused = self._reply(recorder, 2)
        self.assertEqual(refused.status, "catalog_replaced")
        self.assertIn("file changed", refused.message)
        self.assertIsNone(refused.value)
        gateway.request_close()
        self._until(lambda: gateway.close_complete)
        fresh, fresh_recorder = self._gateway()
        self.assertTrue(fresh.submit(CatalogRequest(
            1, RequestClass.APPLY, "initial", (query, 1, "reader-incarnation-2"),
            generation=1)).accepted)
        self._until(lambda: bool(fresh_recorder.replies))
        self.assertEqual(fresh_recorder.replies[0].status, "ok")
        self.assertEqual(fresh_recorder.replies[0].value.token.count, 1)
        self.assertEqual(fresh_recorder.replies[0].value.rows[0]["asset_id"], "replacement-only")

    def test_portable_injected_identity_mismatch_refuses_before_query(self):
        gateway, recorder = self._gateway(InjectedIdentityGateway)
        query, first = self._initial(gateway, recorder)
        gateway.inject_mismatch.set()
        self.assertTrue(gateway.submit(CatalogRequest(
            2, RequestClass.RANK, "rank",
            args=(query, first.token, "reader-incarnation-1", 1, "asset-0256"),
            generation=1)).accepted)
        self._until(lambda: any(reply.request_id == 2 for reply in recorder.replies))
        refused = self._reply(recorder, 2)
        self.assertEqual(refused.status, "catalog_replaced")
        self.assertIn("file changed", refused.message)
        self.assertIsNone(refused.value)

    def test_replacement_before_legacy_and_write_never_dispatches_core_handler(self):
        _WRITE_DISPATCHED.clear()
        _LEGACY_DISPATCHED.clear()
        gateway, recorder = self._gateway()
        self._initial(gateway, recorder)
        replacement = Path(self.temp.name) / "replacement-before-write.sqlite3"
        initialize(replacement)
        with closing(sqlite3.connect(replacement)) as db:
            db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                       "VALUES('replacement-only','/replacement.png','image/png','digest',0)")
            db.commit()
        try:
            os.replace(replacement, self.database)
        except OSError as exc:
            self.skipTest(f"Atomic replacement of an open SQLite file unavailable: {exc}")
        self.assertTrue(gateway.submit(CatalogRequest(
            2, RequestClass.LEGACY, "captured_legacy", context="captured-legacy")).accepted)
        self.assertTrue(gateway.submit(CatalogRequest(
            3, RequestClass.MUTATION, "captured_write")).accepted)
        self._until(lambda: {2, 3}.issubset({reply.request_id for reply in recorder.replies}))
        self.assertEqual(self._reply(recorder, 2).status, "catalog_replaced")
        self.assertEqual(self._reply(recorder, 3).status, "catalog_replaced")
        self.assertFalse(_LEGACY_DISPATCHED.is_set())
        self.assertFalse(_WRITE_DISPATCHED.is_set())
        self.assertTrue(gateway.acknowledge_write(3).accepted)
        with closing(sqlite3.connect(self.database)) as db:
            state = db.execute("SELECT workflow_state FROM assets WHERE asset_id='replacement-only'").fetchone()[0]
        self.assertEqual(state, "new")
        gateway.request_close()
        self._until(lambda: gateway.close_complete)


if __name__ == "__main__":
    unittest.main()

"""Explicit metadata recovery controls for one captured library window."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import threading

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout)

from defiantmaple.catalog import catalog_state, connect
from defiantmaple.recovery import (backup_metadata, enable_reviewed_source,
                                   inspect_package, restore_metadata,
                                   review_restored_sources, _source_roots)


def _identity(path: Path) -> tuple[int, int]:
    info = path.stat()
    return info.st_dev, info.st_ino


def _source_mapping(database: Path) -> dict:
    """Read a complete, bounded mapping without opening source media."""
    with connect(database) as db:
        db.execute("BEGIN")
        state = catalog_state(db)
        captured = _source_roots(db)
        rows = db.execute("SELECT source_id,root_path,enabled,health_detail "
                          "FROM sources ORDER BY source_id").fetchall()
        if [(row[0], row[1]) for row in rows] != captured:
            raise ValueError("Source mapping changed during review capture")
        standalone = db.execute("SELECT COUNT(*) FROM assets WHERE source_id IS NULL").fetchone()[0]
    mapping = []
    for row in rows:
        root = Path(row[1])
        try:
            chain = (Path(root.anchor), *reversed(root.parents), root)
            available = all(stat.S_ISDIR(part.lstat().st_mode) for part in chain)
            available = available and os.access(root, os.R_OK | os.X_OK)
        except (OSError, ValueError):
            available = False
        mapping.append({"source_id": row[0], "root_path": row[1],
                        "enabled": bool(row[2]), "held": bool(row[3] and
                        row[3].startswith("defiantmaple:restored-root-review:v1:")),
                        "available": available})
    return {"state": state, "sources": mapping, "standalone_assets": standalone}


class RecoveryWorker(QThread):
    delivered = Signal(str, object)

    def __init__(self, operation: str, database: Path, catalog_identity: tuple[int, int] | None,
                 cache_roots: tuple[Path, ...], *, package: Path | None = None,
                 package_identity: tuple[int, int] | None = None,
                 output: Path | None = None, captured=None, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.database = Path(database)
        self.catalog_identity = catalog_identity
        self.cache_roots = cache_roots
        self.package = package
        self.package_identity = package_identity
        self.output = output
        self.captured = captured
        self.view_epoch = None
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            if self.catalog_identity is None:
                self.catalog_identity = _identity(self.database)
            if self.operation != "inspect" and _identity(self.database) != self.catalog_identity:
                raise ValueError("Library file changed; reopen it before recovery")
            if self.package is not None and self.package_identity is None:
                self.package_identity = _identity(self.package)
            if self.package_identity is not None and _identity(self.package) != self.package_identity:
                raise ValueError("Selected package changed; select it again")
            if self.operation == "backup":
                result = backup_metadata(self.database, self.output, cache_roots=self.cache_roots,
                                         cancel_event=self.cancel_event)
            elif self.operation == "inspect":
                result = inspect_package(self.package, cancel_event=self.cancel_event)
            elif self.operation == "restore":
                result = restore_metadata(self.package, self.output, cache_roots=self.cache_roots,
                                          live_catalog=self.database, cancel_event=self.cancel_event)
            elif self.operation == "mapping":
                result = _source_mapping(self.database)
            elif self.operation == "review":
                result = review_restored_sources(self.database, self.captured)
            elif self.operation == "enable":
                result = enable_reviewed_source(self.database, *self.captured)
            else:
                raise ValueError("Unknown recovery operation")
            if self.operation in ("review", "enable") and _identity(self.database) != self.catalog_identity:
                raise ValueError("Catalog changed during source review; reopen before refreshing")
            self.delivered.emit("ok", result)
        except Exception as exc:
            self.delivered.emit("error", f"{type(exc).__name__}: {exc}")


class RecoveryDialog(QDialog):
    """One operation at a time; replies never change the active catalog or gallery."""
    catalogChanged = Signal(object)

    def __init__(self, database: Path, cache_roots: tuple[Path, ...], parent=None,
                 catalog_identity: tuple[int, int] | None = None):
        super().__init__(parent)
        self.database = Path(database)
        self.catalog_identity = catalog_identity
        self.cache_roots = tuple(Path(root) for root in cache_roots)
        self.worker: RecoveryWorker | None = None
        self._retired_workers: list[RecoveryWorker] = []
        self.mapping = None
        self._closing = False
        self.setWindowTitle("Metadata recovery")
        self.resize(750, 530)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Backups contain private catalog metadata and original absolute paths. They omit media, "
            "previews, caches, credentials and settings outside the catalog. SHA-256 checks bytes; "
            "it does not authenticate a package. Choose a private local PCIe NVMe directory on Linux. "
            "Other systems and unsupported storage are refused. Older builds may ignore restored holds.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        controls = QHBoxLayout()
        self.backup_button = QPushButton("Back up metadata…")
        self.inspect_button = QPushButton("Inspect package…")
        self.restore_button = QPushButton("Restore to new catalog…")
        self.mapping_button = QPushButton("Review restored roots")
        for button, handler in ((self.backup_button, self.backup),
                                (self.inspect_button, self.inspect),
                                (self.restore_button, self.restore),
                                (self.mapping_button, self.load_mapping)):
            button.clicked.connect(handler)
            controls.addWidget(button)
        layout.addLayout(controls)
        self.status = QLabel("Choose an explicit recovery action. No catalog is switched automatically.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report, 1)
        self.roots = QListWidget()
        self.roots.setAccessibleName("Captured restored source IDs and stored roots")
        layout.addWidget(self.roots)
        review_controls = QHBoxLayout()
        self.activate_button = QPushButton("Confirm all roots reviewed; leave disabled")
        self.enable_button = QPushButton("Enable selected reviewed source")
        self.cancel_button = QPushButton("Cancel operation")
        for button, handler in ((self.activate_button, self.activate),
                                (self.enable_button, self.enable_selected),
                                (self.cancel_button, self.cancel)):
            button.clicked.connect(handler)
            review_controls.addWidget(button)
        layout.addLayout(review_controls)
        self._busy(False)

    def _busy(self, busy: bool, *, cancelable: bool = False):
        for button in (self.backup_button, self.inspect_button, self.restore_button,
                       self.mapping_button, self.activate_button, self.enable_button):
            button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy and cancelable)

    def _start(self, operation: str, **fields):
        if self.worker is not None:
            return
        cancelable = operation in ("backup", "inspect", "restore")
        self._busy(True, cancelable=cancelable)
        self.status.setText(f"{operation.capitalize()} in progress" +
                            ("; cancel is available." if cancelable else "; waiting for the captured result."))
        worker = RecoveryWorker(operation, self.database, self.catalog_identity,
                                self.cache_roots, parent=self, **fields)
        owner = self.parent()
        worker.view_epoch = (getattr(owner, "_selection_epoch", None),
                             getattr(getattr(owner, "model", None), "_generation", None))
        self.worker = worker
        worker.delivered.connect(lambda status, value, own=worker: self._delivered(own, status, value))
        worker.finished.connect(lambda own=worker: self._finished(own))
        worker.start()

    def _delivered(self, worker, status, value):
        if worker is not self.worker:
            return
        if status == "error":
            uncertain = any(marker in str(value).lower() for marker in
                            ("uncertain", "may be published", "remains owned", "inspect target"))
            self.status.setText("Recovery outcome is uncertain; inspect the target before retrying."
                                if uncertain else "Recovery action refused; no success was reported.")
            self.report.setPlainText(str(value))
            if uncertain:
                self._closing = False
            return
        if self._closing:
            if worker.operation in ("review", "enable"):
                changed = value if worker.operation == "review" else {"state": "active", **value}
                self.catalogChanged.emit({"result": changed, "view_epoch": worker.view_epoch})
            return
        if worker.operation == "mapping":
            self.mapping = value
            self.roots.clear()
            for source in value["sources"]:
                condition = ("directory reachable; enable rechecks" if source["available"]
                             else "unavailable or redirected; leave disabled")
                hold = "review held" if source["held"] else "not held"
                self.roots.addItem(f"{source['source_id']} | {source['root_path']} | {condition} | {hold}")
            review_note = (
                "Restored roots are unverified until you review them. Unavailable roots remain disabled. "
                "Standalone assets keep this catalog browse-only until a later durable relink review."
                if value["state"] == "restore_pending" or any(row["held"] for row in value["sources"])
                else "This active catalog has no restored-root review holds.")
            self.report.setPlainText(
                f"Catalog state: {value['state']}\nStandalone assets: {value['standalone_assets']}\n"
                + review_note)
        elif worker.operation == "review":
            self.mapping = None
            self.report.setPlainText("Root review recorded. All restored sources remain disabled. "
                                     "Reload the list, then explicitly enable each available source you trust.")
            self.catalogChanged.emit({"result": value, "view_epoch": worker.view_epoch})
        elif worker.operation == "enable":
            self.mapping = None
            self.report.setPlainText("One captured source was enabled without scanning. Reload root list to review others.")
            self.catalogChanged.emit({"result": {"state": "active", **value},
                                      "view_epoch": worker.view_epoch})
        else:
            self.report.setPlainText(self._format_result(worker.operation, value))
        self.status.setText(f"{worker.operation.capitalize()} completed. The active library was not switched.")

    @staticmethod
    def _format_result(operation: str, value: dict) -> str:
        manifest = value.get("manifest", {})
        catalog = value.get("catalog", {}) if operation != "restore" else value.get("restored", {})
        heading = ("Restore verified" if operation == "restore"
                   else f"{operation.capitalize()} verified: {value.get('package', '')}")
        lines = [heading,
                 f"Package version: {manifest.get('package_version', 'unknown')}",
                 f"Catalog schema: {manifest.get('catalog_schema', 'unknown')}",
                 f"Assets: {catalog.get('assets', 'unknown')}; sources: {catalog.get('sources', 'unknown')}",
                 f"Standalone assets: {catalog.get('standalone_assets', 'unknown')}",
                 "Digest and catalog integrity: verified by bounded worker",
                 "Omitted: original media, derived previews/cache, out-of-catalog settings and credentials",
                 "Stored source roots and absolute paths: unverified, private metadata"]
        if operation == "restore":
            lines.extend((f"New catalog: {value.get('catalog', 'see selected target')}",
                          "Restore remains browse-only. Explicitly open the new catalog to review its roots."))
        return "\n".join(lines)

    def _finished(self, worker):
        if worker is not self.worker:
            return
        self.worker = None
        # Keep the finished QObject under this dialog's ownership. A queued
        # deleteLater racing parent destruction can destroy the same QThread
        # while a later dialog is processing events.
        self._retired_workers.append(worker)
        self._busy(False)
        if self._closing:
            QTimer.singleShot(0, self.close)

    def backup(self):
        selected, _ = QFileDialog.getSaveFileName(self, "New private metadata package", "", "DefiantMaple backup (*.dmbackup)")
        if not selected:
            return
        target = Path(selected)
        self._start("backup", output=target)

    def inspect(self):
        selected, _ = QFileDialog.getOpenFileName(self, "Inspect metadata package", "", "DefiantMaple backup (*.dmbackup)")
        if selected:
            package = Path(selected)
            self._start("inspect", package=package)

    def restore(self):
        selected, _ = QFileDialog.getOpenFileName(self, "Verified package to restore", "", "DefiantMaple backup (*.dmbackup)")
        if not selected:
            return
        package = Path(selected)
        target, _ = QFileDialog.getSaveFileName(self, "New private catalog path", "", "SQLite catalog (*.sqlite3)")
        if not target:
            return
        self._start("restore", package=package, output=Path(target))

    def load_mapping(self):
        self.mapping = None
        self._start("mapping")

    def activate(self):
        mapping = self.mapping
        if not mapping or mapping["state"] != "restore_pending":
            self.status.setText("Load a pending restored catalog's complete root list first.")
            return
        if mapping["standalone_assets"]:
            self.status.setText(f"{mapping['standalone_assets']} standalone assets require later durable relink review; browse-only state remains.")
            return
        if QMessageBox.question(self, "Confirm every stored root",
                                "Confirm that you reviewed every listed ID and exact stored path, including "
                                "unavailable roots. All sources will remain disabled; no scan runs.") != QMessageBox.StandardButton.Yes:
            return
        captured = [(row["source_id"], row["root_path"]) for row in mapping["sources"]]
        self._start("review", captured=captured)

    def enable_selected(self):
        mapping = self.mapping
        index = self.roots.currentRow()
        if not mapping or mapping["state"] != "active" or not 0 <= index < len(mapping["sources"]):
            self.status.setText("Load the active restored catalog list and select one held source.")
            return
        source = mapping["sources"][index]
        if not source["held"] or not source["available"]:
            self.status.setText("Selected source is not held or its root is unavailable.")
            return
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle("Enable this source")
        confirmation.setIcon(QMessageBox.Icon.Question)
        confirmation.setTextFormat(Qt.TextFormat.PlainText)
        confirmation.setText(f"Enable source ID {source['source_id']} at exactly:\n{source['root_path']}\n"
                             "No scan runs. The worker rechecks the captured ID and path.")
        confirmation.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirmation.setDefaultButton(QMessageBox.StandardButton.No)
        if confirmation.exec() != QMessageBox.StandardButton.Yes:
            return
        self._start("enable", captured=(source["source_id"], source["root_path"]))

    def cancel(self):
        if self.worker is not None:
            self.worker.cancel()
            self.status.setText("Cancellation requested; waiting for worker cleanup.")

    def showEvent(self, event):
        if self.worker is None:
            self._closing = False
        super().showEvent(event)

    def closeEvent(self, event):
        if self.worker is not None:
            self._closing = True
            self.worker.cancel()
            self.worker.wait(50)
            self.status.setText("Recovery worker still owns cleanup; this window will close after verified exit, "
                                "or stay open if its outcome is uncertain.")
            event.ignore()
            return
        super().closeEvent(event)

"""Filesystem export worker without catalog access or GUI-thread I/O."""
import threading

from PySide6.QtCore import QObject, Signal, Slot, Qt

from defiantmaple.metadata_name_export import ExportResult, save_name_export

# No QThread is owned by a dialog: parent destruction cannot delete a running
# QThread. Retain the signal object independently until its daemon worker ends.
_ACTIVE = set()


class NameExportWorker(QObject):
    completed = Signal(object)
    _ready = Signal(object)

    def __init__(self, destination, payload):
        super().__init__()
        self.destination = destination
        self.payload = payload
        self._ready.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    def start(self):
        _ACTIVE.add(self)
        try:
            threading.Thread(target=self._run, name="metadata-name-export", daemon=True).start()
        except RuntimeError:
            self._ready.emit(ExportResult(False, error="Export worker could not start"))

    def _run(self):
        try:
            result = save_name_export(self.destination, self.payload)
        except Exception:
            result = ExportResult(None, error="Export outcome unknown; inspect destination before retrying")
        try:
            self._ready.emit(result)
        except RuntimeError:
            # Qt may already be torn down at process exit; never claim success
            # through a destroyed UI or access another application's windows.
            _ACTIVE.discard(self)

    @Slot(object)
    def _deliver(self, result):
        self.completed.emit(result)
        _ACTIVE.discard(self)
        self.deleteLater()

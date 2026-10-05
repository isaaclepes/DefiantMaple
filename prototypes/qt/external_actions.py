"""Bounded external action workers and explicit machine-local Qt controls."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import threading
import time

from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout)

from defiantmaple import external_actions as api
from defiantmaple.private_eval import default_private_root


class ExternalActionWorker(QThread):
    completed = Signal(object)

    def __init__(self, database, target=None, action=None, command=None, *,
                 settings_path=None, settings=None, settings_task=False,
                 probe_only=False, limits=api.ActionLimits(), parent=None):
        super().__init__(parent)
        self.database, self.target, self.action = database, target, action
        self.command = command
        self.settings_path, self.settings = settings_path, settings
        self.settings_task, self.probe_only, self.limits = settings_task, probe_only, limits
        self.cancel_event = threading.Event()
        self.unreaped_process = None
        self.outcome = None

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            if self.settings_task:
                self.outcome = api.execute_settings_task(
                    self.database, self.settings_path, self.settings,
                    timeout_seconds=self.limits.timeout_seconds, cancel_event=self.cancel_event)
            else:
                self.outcome = api.execute_external_action(
                    self.database, self.target, self.action, self.command,
                    limits=self.limits, cancel_event=self.cancel_event, probe_only=self.probe_only)
        except Exception as exc:
            self.unreaped_process = getattr(exc, "process", None)
            self.outcome = exc
        self.completed.emit(self.outcome)


class ExternalSettingsDialog(QDialog):
    saveRequested = Signal(object)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("External tools — this machine")
        self.resize(600, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose trusted installed tools. Arguments are literal values, one per line.\n"
                                "The selected file or folder is added as the last argument."))
        self.fields = {}
        for action, label in ((api.OpenAction.FILE, "Open in Editor"),
                              (api.OpenAction.FOLDER, "Open containing folder")):
            command = settings.file if action == api.OpenAction.FILE else settings.folder
            layout.addWidget(QLabel(label))
            association = QCheckBox("Use this machine's default association")
            association.setAccessibleName(label + " default application")
            association.setChecked(command.executable is None)
            executable = QLineEdit(command.executable or "")
            executable.setAccessibleName(label + " trusted absolute executable")
            executable.setPlaceholderText("Absolute path to a trusted installed executable")
            arguments = QPlainTextEdit("\n".join(command.fixed_args))
            arguments.setAccessibleName(label + " literal fixed arguments, one per line")
            arguments.setMaximumHeight(85)
            arguments.setTabChangesFocus(True)
            association.toggled.connect(executable.setDisabled)
            association.toggled.connect(arguments.setDisabled)
            executable.setDisabled(association.isChecked())
            arguments.setDisabled(association.isChecked())
            for widget in (association, executable, arguments):
                layout.addWidget(widget)
            self.fields[action] = (association, executable, arguments)
        self.feedback = QLabel("Settings remain local to this machine, outside the catalog.")
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        try:
            commands = []
            for action in (api.OpenAction.FILE, api.OpenAction.FOLDER):
                association, executable, arguments = self.fields[action]
                text = arguments.toPlainText()
                commands.append(api.CommandSpec() if association.isChecked() else
                                api.CommandSpec(executable.text(), tuple(text.splitlines()) if text else ()))
            self.saveRequested.emit(api.ExternalSettings(*commands))
        except ValueError as exc:
            self.feedback.setText(str(exc))


class ExternalActionsMixin:
    """Gallery owns exactly one action/settings worker, including cleanup."""

    def _init_external_actions(self, layout, settings_path, settings):
        self.external_settings_path = settings_path or default_private_root().parent / "external-actions.json"
        self._pending_external = None
        self._pending_settings_dialog = False
        self.external_settings = settings
        self.external_worker = None
        self.external_cleanup_failed = False
        self.external_settings_dialog = None
        self._external_close_pending = False
        self.open_external_button = QPushButton("Open in Editor")
        self.open_external_button.setToolTip("Uses the configured editor, or this machine’s default application (which may be a viewer).")
        self.open_folder_button = QPushButton("Open containing folder")
        self.external_settings_button = QPushButton("External tools on this machine…")
        self.external_cancel_button = QPushButton("Cancel external check")
        self.external_feedback = QLabel("External actions use the focused asset. Default associations may open a viewer. Settings load on explicit use.")
        self.external_feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.external_feedback.setWordWrap(True)
        self.external_feedback.setAccessibleName("Captured external action target and handoff result")
        for widget, name in ((self.open_external_button, "openExternalAsset"),
                             (self.open_folder_button, "openContainingFolder"),
                             (self.external_settings_button, "externalToolSettings"),
                             (self.external_cancel_button, "cancelExternalCheck")):
            widget.setObjectName(name)
            widget.setAccessibleName(widget.text())
            layout.addWidget(widget)
        layout.addWidget(self.external_feedback)
        self.open_external_button.clicked.connect(self.open_external_file)
        self.open_folder_button.clicked.connect(self.open_containing_folder)
        self.external_settings_button.clicked.connect(self.open_external_settings)
        self.external_cancel_button.clicked.connect(self.cancel_external_action)
        self.gallery.selectionModel().currentChanged.connect(self._update_external_controls)
        self.model.modelReset.connect(self._update_external_controls)
        self._update_external_controls()

    def _update_external_controls(self, *_args):
        busy = self.external_worker is not None or self.external_cleanup_failed or self._closing
        try:
            asset = self._selected_asset()
            reason = api.observed_unavailable(asset) if asset is not None else None
            eligible = asset is not None and reason is None
            if reason and not busy:
                self.external_feedback.setText(reason)
        except (ValueError, IndexError, sqlite3.Error):
            eligible = False
        enabled = not busy and eligible
        self.open_external_button.setEnabled(enabled)
        self.open_folder_button.setEnabled(enabled)
        self.external_settings_button.setEnabled(not busy)
        self.external_cancel_button.setEnabled(self.external_worker is not None and not self._closing and not self.external_cleanup_failed)

    def _start_external_worker(self, worker):
        if self.external_worker is not None or self.external_cleanup_failed or self._closing:
            worker.deleteLater()
            return False
        self.external_worker = worker
        worker.completed.connect(lambda result: self._external_completed(worker, result))
        worker.finished.connect(lambda: self._external_finished(worker))
        self._update_external_controls()
        worker.start()
        return True

    def open_external_file(self):
        return self._open_external(api.OpenAction.FILE)

    def open_containing_folder(self):
        return self._open_external(api.OpenAction.FOLDER)

    def _open_external(self, action):
        if self.external_worker is not None or self.external_cleanup_failed or self._closing:
            return None
        try:
            asset = self._selected_asset()
            if asset is None:
                raise ValueError("Select a focused asset.")
            reason = api.observed_unavailable(asset)
            if reason:
                raise ValueError(reason)
            target = api.capture_target(asset)
            if self.external_settings is None:
                self._pending_external = (target, action, time.monotonic() + 5.0)
                self.external_feedback.setText(f"Loading local settings for captured {Path(target.path).name} · {target.asset_id}…")
                worker = ExternalActionWorker(self.database, settings_path=self.external_settings_path, settings_task=True, parent=self)
                return worker if self._start_external_worker(worker) else None
            command = self.external_settings.file if action == api.OpenAction.FILE else self.external_settings.folder
            worker = ExternalActionWorker(self.database, target, action, command, parent=self)
            self.external_feedback.setText(f"Checking captured {Path(target.path).name} · {target.asset_id} · revision {target.revision}…")
            return worker if self._start_external_worker(worker) else None
        except (ValueError, IndexError, OSError, sqlite3.Error) as exc:
            self.external_feedback.setText(f"External action refused: {exc}")
            return None

    def _external_completed(self, worker, result):
        if worker is not self.external_worker:
            return
        if isinstance(result, Exception):
            self._pending_external = None
            self._pending_settings_dialog = False
            self.external_feedback.setText(f"External action/settings failed: {result}")
        elif worker.settings_task:
            self.external_settings = result
            self.external_feedback.setText("Machine-local settings ready. Default applications may be viewers; external edits require an explicit scan.")
            if worker.settings is not None and self.external_settings_dialog is not None:
                self.external_settings_dialog.accept()
        else:
            self.external_feedback.setText(f"{Path(result.target.path).name} · {result.target.asset_id}: {result.message}")

    def _external_finished(self, worker):
        if worker is not self.external_worker:
            return
        if worker.unreaped_process is not None:
            self.external_cleanup_failed = True
            self.external_feedback.setText("External helper cleanup failed; ownership retained. Further actions and close are blocked.")
        else:
            self.external_worker = None
            worker.deleteLater()
        self._update_external_controls()
        if self._external_close_pending and not self.external_cleanup_failed:
            self._pending_external = None
            self._pending_settings_dialog = False
            QTimer.singleShot(0, self.close)
        elif not self.external_cleanup_failed and self._pending_external is not None:
            target, action, deadline = self._pending_external
            self._pending_external = None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.external_feedback.setText("Captured external request timed out while loading settings; no dispatch permit issued.")
                return
            command = self.external_settings.file if action == api.OpenAction.FILE else self.external_settings.folder
            self.external_feedback.setText(f"Checking captured {Path(target.path).name} · {target.asset_id} · revision {target.revision}…")
            self._start_external_worker(ExternalActionWorker(self.database, target, action, command, limits=api.ActionLimits(remaining), parent=self))
        elif not self.external_cleanup_failed and self._pending_settings_dialog:
            self._pending_settings_dialog = False
            self.open_external_settings()

    def cancel_external_action(self):
        if self.external_worker is not None:
            self._pending_external = None
            self._pending_settings_dialog = False
            self.external_worker.cancel()
            self.external_feedback.setText("Cancelling captured external check; a permitted handoff may be uncertain…")

    def open_external_settings(self):
        if self.external_worker is not None or self.external_cleanup_failed:
            return None
        if self.external_settings is None:
            self._pending_settings_dialog = True
            worker = ExternalActionWorker(self.database, settings_path=self.external_settings_path, settings_task=True, parent=self)
            self._start_external_worker(worker)
            return worker
        if self.external_settings_dialog is not None:
            self.external_settings_dialog.close()
        dialog = ExternalSettingsDialog(self.external_settings, self)
        self.external_settings_dialog = dialog
        dialog.saveRequested.connect(self._save_external_settings)
        dialog.show()
        return dialog

    def _save_external_settings(self, settings):
        if self.external_worker is not None or self.external_cleanup_failed or self._closing:
            if self.external_settings_dialog is not None:
                self.external_settings_dialog.feedback.setText("Wait for the captured operation to finish before saving settings.")
            return
        self._start_external_worker(ExternalActionWorker(
            self.database, settings_path=self.external_settings_path, settings=settings,
            settings_task=True, parent=self))

    def _close_external_actions(self, event):
        if self.external_cleanup_failed:
            event.ignore()
            return False
        if self.external_worker is not None:
            self._external_close_pending = True
            self.external_worker.cancel()
            self.external_feedback.setText("Stopping external helper and verifying cleanup…")
            event.ignore()
            return False
        if self.external_settings_dialog is not None:
            self.external_settings_dialog.close()
        return True

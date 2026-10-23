"""Plain settings/status widgets; all persistence/work belongs to the controller."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout)

from defiantmaple.scheduled_snapshots import Policy, ScheduleError


def status_text(view):
    names = {'not_checked': 'Schedule not checked', 'checking': 'Checking saved schedule',
        'unconfigured': 'No saved schedule', 'ready': 'Schedule enabled',
        'enabling': 'Saving schedule', 'cleanup_pending': 'Waiting for actual cleanup',
        'stopping_not_saved': 'Stopping — stop request not saved yet',
        'stop_not_saved': 'Stop request was not saved',
        'stop_saved_waiting_cleanup': 'Stop request saved; waiting for cleanup',
        'saved_stop_cleanup_unknown': 'Saved stop; prior cleanup review required',
        'stop_saved_status_unknown': 'Stop saved; current durable status unknown',
        'stopped': 'Scheduling disabled', 'suspended': 'Schedule suspended',
        'canceled': 'Schedule action canceled', 'unsupported': 'Scheduling unavailable'}
    lines = [names.get(view.phase, view.phase)]
    state = view.state
    point = None if state is None else state.last_success
    if point is not None:
        lines.append(f'Historical verified snapshot: #{point.sequence}; verified UTC {point.verified_utc}')
    else:
        lines.append('Historical verified snapshot: unknown' if state is None else 'No verified snapshot recorded')
    if state is not None:
        lines.append(f'Last attempt UTC: {state.status.last_attempt_utc}; outcome: {state.status.outcome}')
    lines.append('Current package verification: ' + ('yes' if view.currently_verified else
                 'unknown' if state is None else 'not currently reverified'))
    timing = getattr(view, 'timing', None)
    if timing is None or timing.remaining_seconds is None:
        lines.append('Next due: unknown / scheduling inactive')
    elif timing.remaining_seconds == 0:
        lines.append('At the last status update, the next run was due (monotonic deadline reached)')
    else:
        lines.append(f'At the last status update, next due was in approximately {timing.remaining_seconds} seconds (monotonic deadline)')
    if timing is not None:
        if timing.active:
            lines.append('Scheduled operation active; overlapping runs are not started')
        if timing.pending:
            lines.append('One scheduled run pending; missed intervals are not replayed')
        if timing.manual_deferred:
            lines.append('Pending run deferred until manual recovery cleanup completes')
        if timing.clock_adjusted:
            lines.append('Backward wall-clock change observed on reopen; a full interval was selected')
        if timing.suspended:
            lines.append('Timing suspended; no next run is promised')
    if getattr(view, 'recovery_review_required', False):
        lines.append('Recovery review required; stopping did not resolve recovery state')
    if view.error:
        lines.append(str(view.error))
    return '\n'.join(lines)


class SnapshotStatusLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)

    def display(self, view):
        self.setText(status_text(view))


class SnapshotSettingsDialog(QDialog):
    """Hiding this dialog never cancels a saved application-running schedule."""
    def __init__(self, controller, parent=None, *, cancel_action=None):
        super().__init__(parent)
        self.controller = controller
        self.cancel_action = cancel_action
        self._dirty = False
        self._interval_changed = False
        self._exact_interval = None
        self._presented = None
        self.setWindowTitle('Scheduled metadata snapshots')
        layout = QVBoxLayout(self)
        notice = QLabel('Metadata only: original media, previews/cache and out-of-catalog settings are omitted. '
            'Scheduling runs only while this library window is open; no background OS service is installed.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.status = SnapshotStatusLabel(self)
        layout.addWidget(self.status)
        form = QFormLayout()
        self.destination = QLineEdit()
        self.destination.setPlaceholderText('New dedicated private directory; it must not already exist')
        self.browse = QPushButton('Choose new directory…')
        destination_row = QHBoxLayout()
        destination_row.addWidget(self.destination); destination_row.addWidget(self.browse)
        form.addRow('Snapshot directory', destination_row)
        self.interval = QSpinBox()
        self.interval.setRange(15, 43200); self.interval.setValue(1440)
        self.interval.setSuffix(' minutes')
        form.addRow('Interval (15 minutes–30 days)', self.interval)
        self.interval_note = QLabel()
        form.addRow('', self.interval_note)
        self.keep_enabled = QCheckBox('Limit package count')
        self.keep_enabled.setChecked(True)
        self.keep = QSpinBox(); self.keep.setRange(1, 1000); self.keep.setValue(10)
        form.addRow(self.keep_enabled, self.keep)
        self.bytes_enabled = QCheckBox('Limit total package bytes')
        self.bytes_limit = QLineEdit(str(1024 * 1024 * 1024))
        form.addRow(self.bytes_enabled, self.bytes_limit)
        units = QLabel('Byte limit: 1,048,576 (1 MiB)–1,099,511,627,776 (1 TiB). At least one limit is required.')
        units.setWordWrap(True); form.addRow('', units)
        self.retention = QCheckBox('Allow deletion of older managed snapshots to enforce these limits')
        self.retention.setChecked(False)
        form.addRow(self.retention)
        protection = QLabel('Retention protects the last verified snapshot and unrelated files. '
            'If protected packages prevent the limits, scheduling stops and reports the exception.')
        protection.setWordWrap(True); form.addRow('', protection)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.enable = QPushButton('Enable / save policy')
        self.disable = QPushButton('Disable scheduling')
        self.snapshot = QPushButton('Snapshot now')
        self.cancel = QPushButton('Cancel scheduled operation')
        self.refresh = QPushButton('Refresh status / saved settings')
        for button in (self.enable, self.disable, self.snapshot, self.cancel, self.refresh):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.feedback = QLabel(); self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback.setWordWrap(True); layout.addWidget(self.feedback)
        self.browse.clicked.connect(self._choose_directory)
        self.enable.clicked.connect(self._save)
        self.disable.clicked.connect(lambda: self._action(controller.disable))
        self.snapshot.clicked.connect(lambda: self._action(controller.snapshot_now))
        self.cancel.clicked.connect(lambda: self._action(self.cancel_action))
        self.refresh.clicked.connect(self._refresh)
        for field in (self.destination, self.bytes_limit):
            field.textEdited.connect(self._edit)
        for field in (self.keep_enabled, self.bytes_enabled, self.retention):
            field.toggled.connect(self._edit)
        self.keep.valueChanged.connect(self._edit)
        self.interval.valueChanged.connect(self._edit_interval)
        controller.changed.connect(self.display)
        controller.idleChanged.connect(lambda idle: self._controls())
        self.display(controller.view)

    def _edit(self, *args):
        self._dirty = True
        self._controls()

    def _edit_interval(self, *args):
        self._interval_changed = True
        self._dirty = True

    def _key(self, view):
        return (view.control_version, None if view.locator is None else view.locator.revision)

    def display(self, view):
        self.status.display(view)
        if not self._dirty and view.phase not in {'checking', 'enabling'}:
            self._presented = self._key(view)
            if view.state is not None:
                policy = view.state.policy
                fields = (self.destination, self.interval, self.keep_enabled, self.keep,
                          self.bytes_enabled, self.bytes_limit, self.retention)
                for field in fields: field.blockSignals(True)
                try:
                    self.destination.setText(view.state.locator.binding.directory_path)
                    self.interval.setValue(max(15, min(43200, (policy.interval_seconds + 59) // 60)))
                    self._exact_interval = policy.interval_seconds
                    self.interval_note.setText(f'Saved exact interval: {policy.interval_seconds} seconds; editing selects whole minutes.')
                    self.keep_enabled.setChecked(policy.keep_count is not None)
                    self.keep.setValue(policy.keep_count or 10)
                    self.bytes_enabled.setChecked(policy.byte_limit is not None)
                    self.bytes_limit.setText(str(policy.byte_limit or 1024**3))
                    self.retention.setChecked(policy.retention_enabled)
                    self._interval_changed = False
                finally:
                    for field in fields: field.blockSignals(False)
        self._controls()

    def _controls(self):
        phase = self.controller.view.phase
        idle = self.controller.idle
        state = self.controller.view.state
        stopping_retention = (not idle and phase == 'ready' and state is not None
            and state.policy.retention_enabled and not self.retention.isChecked())
        self.enable.setEnabled(not self.controller.closing and
            ((idle and phase in {'unconfigured', 'ready', 'stopped'}) or stopping_retention))
        self.snapshot.setEnabled(idle and phase == 'ready')
        self.disable.setEnabled(self.controller.view.locator is not None and not self.controller.closing)
        self.cancel.setEnabled(not idle and callable(self.cancel_action) and not self.controller.closing)
        self.refresh.setEnabled(idle and not self.controller.closing)

    def policy(self):
        if not self.keep_enabled.isChecked() and not self.bytes_enabled.isChecked():
            raise ScheduleError('Choose at least one storage limit')
        byte_limit = None
        if self.bytes_enabled.isChecked():
            text = self.bytes_limit.text().strip()
            if not text.isascii() or not text.isdecimal():
                raise ScheduleError('Byte limit must be an integer number of bytes')
            byte_limit = int(text)
        interval = (self._exact_interval if self._exact_interval is not None and not self._interval_changed
                    else self.interval.value() * 60)
        return Policy(enabled=True, interval_seconds=interval,
            retention_enabled=self.retention.isChecked(),
            keep_count=self.keep.value() if self.keep_enabled.isChecked() else None,
            byte_limit=byte_limit)

    def _action(self, callback):
        try:
            if not callable(callback):
                raise ScheduleError('This action is not connected')
            callback()
        except (ValueError, OSError) as exc:
            self.feedback.setText(str(exc))

    def _save(self):
        try:
            if self._presented != self._key(self.controller.view):
                raise ScheduleError('Saved status changed; refresh before saving policy')
            path = Path(self.destination.text().strip())
            if not path.is_absolute():
                raise ScheduleError('Choose an absolute new dedicated directory path')
            policy = self.policy()
            state = self.controller.view.state
            if (not self.controller.idle and state is not None and state.policy.retention_enabled
                    and not policy.retention_enabled):
                self.controller.disable(reason='retention-off requested')
                self.feedback.setText('Stop requested; refresh and save this policy after cleanup/review completes.')
                return
            request = self.controller.capture_enable()
            self.controller.enable(request, policy, managed_directory=path)
            self._dirty = False
        except (ValueError, OSError) as exc:
            self.feedback.setText(str(exc))

    def _refresh(self):
        self._dirty = False
        self._action(self.controller.check)

    def _choose_directory(self):
        parent = QFileDialog.getExistingDirectory(self, 'Private parent for a NEW snapshot directory')
        if not parent:
            return
        name, accepted = QInputDialog.getText(self, 'New dedicated directory', 'New child directory name:')
        if accepted and name:
            self.destination.setText(str(Path(parent) / name))
            self._edit()

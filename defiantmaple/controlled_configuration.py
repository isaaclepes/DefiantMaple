"""Explicit controlled Enable, borrowing original configuration native stores.

No UI/timer and no import-time I/O. Caller captures the expected control version
at the explicit action, then owns this one-shot operation through actual worker
completion. No recursive configure/operation lock acquisition is used.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import uuid
import threading

from .manual_recovery_operation import ManualRecoveryOperation
from .scheduled_snapshots import Policy, ScheduleError, Version, _integer, _uuid
from .snapshot_control import ControlStore, ScheduleControl
from .snapshot_operations import SnapshotOperations


@dataclass(frozen=True)
class EnableRequest:
    request_id: str
    expected_control: Version | None
    expected_revision: int | None

    def __post_init__(self):
        _uuid(self.request_id)
        if self.expected_control is not None and type(self.expected_control) is not Version:
            raise ScheduleError('Enable requires its captured control version or explicit absence')
        if self.expected_revision is not None:
            _integer(self.expected_revision, 1, 2**63 - 1)

    @classmethod
    def capture(cls, expected_control, expected_revision):
        """Capture a presented snapshot at explicit action; never refresh later."""
        return cls(str(uuid.uuid4()), expected_control, expected_revision)


class _BorrowedInspector(SnapshotOperations):
    def __init__(self, config, context, actor):
        super().__init__(config)
        self.state = context.old_state
        self.managed = context.old_store
        self.cancel = actor.cancel
        self.records = actor.records
        self._manual = actor

    def _begin(self):
        raise ScheduleError('Borrowed inspection cannot acquire upstream locks')

    def _started(self, operation, process, stages):
        self._manual._observer(None)(operation, process, stages)

    def verify(self):
        if self.state is None:
            return
        from .snapshot_retention import pending_intent
        if pending_intent(self.state) is not None:
            raise ScheduleError('Pending retention intent requires explicit review')
        allowed = {'schedule.json', 'schedule.lock', *(p.leaf for p in self.state.packages)}
        if set(self.managed.names()) != allowed:
            raise ScheduleError('Unknown or missing managed package/stage; preserve and review')
        for package in self.state.packages:
            self._inspect(package.leaf, package)
        if not self._cleanup():
            raise ScheduleError('Owned configuration inspection cleanup is pending')


class ControlledEnableOperation:
    """One captured action; retain this object until finish_thread proves cleanup.

    run returning/raising is not permission to drop the actor or its owner slot.
    The caller invokes finish_thread only after its actual worker thread ends.
    """
    def __init__(self, configuration, request):
        if type(request) is not EnableRequest:
            raise ScheduleError('A captured explicit Enable request is required')
        self.config = configuration
        self.request = request
        self.actor = ManualRecoveryOperation(configuration.owner)
        self._used = False
        self._start_lock = threading.Lock()
        self.control_version = None

    @property
    def active(self):
        return self.actor.active

    @property
    def owner(self):
        return self.actor.owner

    def request_cancel(self):
        self.actor.request_cancel()

    def finish_thread(self):
        return self.actor.finish_thread()

    def reap(self):
        return self.actor.reap()

    @contextmanager
    def _transaction(self, context):
        context.validate()
        if context.old_locator is not None and context.old_locator.revision != self.request.expected_revision:
            raise ScheduleError('Configuration changed after explicit Enable')
        inspector = _BorrowedInspector(self.config, context, self.actor)
        inspector.verify()
        if self.actor.cancel.is_set():
            raise ScheduleError('Explicit Enable canceled before control transaction')
        # Actual child inspection/cleanup completed under the same owner+slot
        # and original native stores. Control is acquired strictly last.
        with ControlStore(self.config.root, self.owner.path) as control:
            current, version = control.read_control()
            if version != self.request.expected_control:
                raise ScheduleError('Control changed after explicit Enable; reload')
            if current is not None and current.action == 'stop_requested':
                raise ScheduleError('Saved stop has prior cleanup uncertainty; review required')
            if current is not None and context.old_locator is not None and current.locator != context.old_locator:
                raise ScheduleError('Control/configuration binding changed; review required')
            transaction = _EnableCommit(self, context, control, version)
            yield transaction
            if not transaction.committed:
                raise ScheduleError('Explicit Enable did not commit its control')

    def run(self, policy, *, managed_directory=None):
        with self._start_lock:
            if self._used:
                raise ScheduleError('Explicit Enable action already consumed')
            if type(policy) is not Policy or not policy.enabled:
                raise ScheduleError('Controlled Enable requires an enabled typed policy')
            self._used = True
        self.actor.begin()
        return self.actor._invoke(self.config.configure, policy,
            managed_directory=managed_directory,
            expected_revision=self.request.expected_revision, _transaction=self._transaction)


class _EnableCommit:
    def __init__(self, operation, context, control, version):
        self.operation, self.context = operation, context
        self.control, self.version = control, version
        self.committed = False

    def commit(self, state):
        self.context.validate()
        if self.committed or state != self.context.new_state:
            raise ScheduleError('Configuration commit differs from borrowed state')
        if self.operation.actor.cancel.is_set():
            raise ScheduleError('Explicit Enable canceled before run publication')
        value = ScheduleControl(state.locator, self.operation.request.request_id,
            'run', int(self.operation.config.utc()), 'explicit enable')
        self.operation.control_version = self.control.write_control(value, self.version)
        self.committed = True

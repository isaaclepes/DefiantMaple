"""Explicit durable schedule configuration and exact-key automatic discovery.

No timers, backup children, package inspection or retention deletion run here.
Discovered state needs package reconciliation before an operation may execute.
"""
from contextlib import ExitStack, closing
from dataclasses import dataclass, replace
import os
from pathlib import Path
import sqlite3
import time
import uuid

from .admission import current_session
from .recovery import (_cache_roots, _source_roots, _outside_sources, _outside_caches,
                       _outside_catalog_family, _require_backup_catalog)
from .recovery_storage import private_local_parent
from .locator_bootstrap import bootstrap_locator_directory
from .scheduled_snapshots import (AuditRecord, Binding, ConfigurationTransition, Locator, LockedDirectory,
    Policy, ScheduleError, ScheduleState, StateUncertainError, _integer, _path,
    locator_directory, locator_leaf, validate_pair)


@dataclass(frozen=True)
class _ConfigurationContext:
    """Borrowed stores: valid only inside the original configure ExitStack."""
    old_locator: object
    old_state: object
    old_store: object
    new_locator: object
    new_state: object
    new_store: object
    _lifetime: list

    def validate(self):
        if self._lifetime != [True]:
            raise ScheduleError("Borrowed configuration context expired")
        self.new_store.validate()
        if self.old_store is not None:
            self.old_store.validate()


@dataclass(frozen=True)
class Discovery:
    status: str  # unconfigured, configured (not yet package-reconciled), suspended
    state: ScheduleState | None = None
    reason: str | None = None
    locator: Locator | None = None


def _present(path):
    try:
        Path(path).lstat()
        return True
    except FileNotFoundError:
        return False


def _create_private_directory(path):
    # User-selected managed destination retains the strict existing parent.
    with private_local_parent(path) as (path, parent_fd):
        os.mkdir(path.name, 0o700, dir_fd=parent_fd)
        try:
            os.fsync(parent_fd)
        except OSError as exc:
            raise StateUncertainError("Configuration directory created; durability uncertain") from exc


class SnapshotConfiguration:
    def __init__(self, owner, application_data_root, *, cache_roots, utc=time.time,
                 locator_profile="custom"):
        self.owner = owner
        self.root = locator_directory(Path(_path(str(application_data_root))))
        self.locator_profile = locator_profile
        self.leaf = locator_leaf(owner.path)
        self.transition_leaf = self.leaf + ".transition"
        self.caches = _cache_roots(cache_roots)
        self.utc = utc

    def _validate_owner(self):
        if current_session(self.owner.path) is not self.owner:
            raise ScheduleError("Schedule configuration requires its active admitted library")
        self.owner.validate()

    def _placement(self, managed=None):
        self._validate_owner()
        targets = [self.root] + ([] if managed is None else [Path(_path(str(managed)))])
        with closing(sqlite3.connect(self.owner.path.as_uri() + "?mode=ro", uri=True)) as db:
            _require_backup_catalog(db)
            roots = _source_roots(db)
        for target in targets:
            # Do not resolve target components: the native directory adapter must
            # observe/reject symlinks instead of hiding redirected placement.
            _outside_sources(target, roots)
            _outside_caches(target, self.caches)
            _outside_catalog_family(target, self.owner.path)
            if any(Path(str(self.owner.path) + suffix) in target.parents for suffix in ("-wal", "-shm", "-journal")):
                raise ScheduleError("Schedule storage cannot descend into a catalog sidecar")
            if target == self.owner.path or target in self.owner.path.parents:
                raise ScheduleError("Schedule storage cannot contain the live catalog")
            if any(target in Path(root).parents for _, root in roots) or any(target in root.parents for root in self.caches):
                raise ScheduleError("Schedule storage cannot contain source or cache roots")
        if managed is not None:
            managed = Path(managed)
            if self.root == managed or self.root in managed.parents or managed in self.root.parents:
                raise ScheduleError("Locator and managed directories must be separate")

    def discover(self):
        """Read only the exact configured pointer; absent never means I/O failure."""
        locator = None
        try:
            self._placement()
            if not _present(self.root):
                return Discovery("unconfigured", reason="no_locator_for_location")
            # Do not create a permanent lock for an unconfigured library merely
            # because another library has a locator directory.
            if not _present(self.root / self.leaf) and not _present(self.root / self.transition_leaf):
                with private_local_parent(self.root / self.leaf):
                    pass
                return Discovery("unconfigured", reason="no_locator_for_location")
            with LockedDirectory(self.root, self.leaf + ".lock") as locators:
                locator, _ = locators.read(self.leaf, locator=True)
                transition, _ = locators.read(self.transition_leaf, transition=True)
                if transition is not None and transition.phase == "pending":
                    return Discovery("suspended", reason="configuration_transition_pending", locator=locator)
                if locator is None:
                    raise ScheduleError("Expected locator disappeared during discovery")
                if transition is None or transition.locator != locator:
                    raise ScheduleError("Configuration transition does not match its locator")
                self._placement(locator.binding.directory_path)
                locator.binding.validate(self.owner)
                with LockedDirectory(locator.binding.directory_path, "schedule.lock") as managed:
                    state, _ = managed.read("schedule.json")
                    validate_pair(locator, state, self.owner)
                    blocked = state.status.cleanup_pending or state.status.outcome in {"in_progress", "uncertain", "cleanup_warning"}
                    return Discovery("suspended" if blocked else "configured", state,
                                     "operation_reconciliation_required" if blocked else "package_reconciliation_required", locator)
        except (ValueError, OSError, sqlite3.Error) as exc:
            return Discovery("suspended", reason=type(exc).__name__ + ": " + str(exc)[:256], locator=locator)

    def configure(self, policy, *, managed_directory=None, expected_revision=None,
                  _transaction=None):
        """Explicit enable/edit; state first, matching locator second, then ack.

        New destinations must be absent and become dedicated directories. An
        existing schedule can only be edited at its exact current revision.
        A changed physical library requires an explicit new destination.
        """
        if type(policy) is not Policy:
            raise ScheduleError("Configuration requires a typed policy")
        if expected_revision is not None:
            _integer(expected_revision, 1, 2**63 - 1)
        proposed = None if managed_directory is None else Path(_path(str(managed_directory)))
        self._placement(proposed)
        # Reconfirm child and parent durability even when an earlier Enable
        # created the locator directory but its fsync outcome was uncertain.
        bootstrap_locator_directory(self.root.parent, profile=self.locator_profile)
        with LockedDirectory(self.root, self.leaf + ".lock") as locators:
            old_locator, locator_version = locators.read(self.leaf, locator=True)
            transition, transition_version = locators.read(self.transition_leaf, transition=True)
            if transition is not None and transition.phase != "committed":
                raise ScheduleError("Reconcile the pending configuration transition before updating")
            if (old_locator is not None and (transition is None or transition.locator != old_locator)) or (old_locator is None and transition is not None):
                raise ScheduleError("Configuration transition/locator mismatch")
            if (None if old_locator is None else old_locator.revision) != expected_revision:
                raise ScheduleError("Configuration changed; reload its revision before updating")
            old_directory = None if old_locator is None else Path(old_locator.binding.directory_path)
            directory = proposed if proposed is not None else old_directory
            if directory is None:
                raise ScheduleError("Choose a new managed directory explicitly")
            self._placement(directory)
            reuse = directory == old_directory
            if old_directory is not None and not reuse and (old_directory in directory.parents or directory in old_directory.parents):
                raise ScheduleError("Old and new managed directories must not overlap")
            # Global order: locator key -> old managed schedule -> new managed
            # schedule (if distinct and newly created). No managed-held operation
            # takes the locator lock, and no existing destination can be adopted.
            with ExitStack() as stores:
                old_store = old_state = old_version = None
                if old_locator is not None:
                    self._placement(old_directory)
                    old_store = stores.enter_context(LockedDirectory(old_directory, "schedule.lock"))
                    if old_store.identity != old_locator.binding.directory_identity:
                        raise ScheduleError("Old managed directory changed; reconcile before configuring")
                    old_state, old_version = old_store.read("schedule.json")
                    if old_state is None or old_state.locator != old_locator:
                        raise ScheduleError("Old managed state does not match its locator")
                    if old_state.status.cleanup_pending or old_state.status.outcome in {"in_progress", "uncertain", "cleanup_warning"}:
                        raise ScheduleError("Reconcile the earlier operation before changing policy or destination")
                if reuse:
                    validate_pair(old_locator, old_state, self.owner)
                    managed, previous, version = old_store, old_state, old_version
                    locator = replace(old_locator, revision=old_locator.revision + 1)
                else:
                    if _present(directory):
                        raise ScheduleError("A new managed destination must be absent")
                    _create_private_directory(directory)
                    managed = stores.enter_context(LockedDirectory(directory, "schedule.lock"))
                    previous, version = managed.read("schedule.json")
                    if previous is not None:
                        raise ScheduleError("New schedule directory already contains state")
                    # Revision belongs to the locator key, not the destination;
                    # retaining it prevents stale-UI ABA after destination change.
                    locator = Locator(str(uuid.uuid4()), 1 if old_locator is None else old_locator.revision + 1,
                                      Binding.capture(self.owner, directory))
                    previous = ScheduleState(locator)
                clock = self.utc()
                if type(clock) not in (int, float) or not 0 <= clock <= 253402300799:
                    raise ScheduleError("Invalid configuration UTC clock")
                event = AuditRecord((previous.audit[-1].sequence + 1) if previous.audit else 1,
                                    str(uuid.uuid4()), locator.revision, int(clock), "configured")
                state = replace(previous, locator=locator, policy=policy, audit=(*previous.audit, event))
                # Configuration cannot silently discard ledger/audit or clear an
                # operation failure; strict model/caps run before either write.
                self._validate_owner()
                self._placement(directory)
                transaction = None
                if _transaction is not None:
                    lifetime = [True]
                    stores.callback(lambda: lifetime.__setitem__(0, False))
                    context = _ConfigurationContext(old_locator, old_state, old_store,
                        locator, state, managed, lifetime)
                    transaction = stores.enter_context(_transaction(context))
                state_written = intent_written = False
                try:
                    # This durable per-key pending record prevents a matching
                    # old locator+old state from silently resuming old policy
                    # after a destination-change transaction is interrupted.
                    intent = ConfigurationTransition(locator, str(uuid.uuid4()), "pending")
                    intent_version = locators.write(self.transition_leaf, intent, transition_version)
                    intent_written = True
                    managed.write("schedule.json", state, version)
                    state_written = True
                    self._validate_owner()
                    self._placement(directory)
                    if old_store is not None and not reuse:
                        observed_old, observed_version = old_store.read("schedule.json")
                        if observed_old != old_state or observed_version != old_version:
                            raise StateUncertainError("Old schedule changed during destination transition")
                    locators.write(self.leaf, locator, locator_version)
                    actual_locator, _ = locators.read(self.leaf, locator=True)
                    actual_state, _ = managed.read("schedule.json")
                    validate_pair(actual_locator, actual_state, self.owner)
                    if actual_locator != locator or actual_state != state:
                        raise StateUncertainError("Configuration changed before acknowledgment")
                    committed = replace(intent, phase="committed")
                    locators.write(self.transition_leaf, committed, intent_version)
                    if locators.read(self.transition_leaf, transition=True)[0] != committed:
                        raise StateUncertainError("Configuration completion record changed")
                    if transaction is not None:
                        context.validate()
                        transaction.commit(state)
                    return state
                except BaseException as exc:
                    if state_written or intent_written:
                        raise StateUncertainError("Schedule state saved but configuration acknowledgment uncertain; reconcile revisions") from exc
                    raise

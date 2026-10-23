"""Cooperative native retention: exact-review required before generated deletion.

Participating read leases exclude candidate unlink. Native FD locks do not offer
atomic unlink-by-identity against hostile same-user mutation after the last check.
No uncertain intent is ever replayed as a pathname cleanup instruction.
"""
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import os
import uuid

from . import recovery
from .admission import current_session
from .snapshot_control import require_run
from .recovery_storage import package_lease, regular_existing
from .scheduled_snapshots import (AuditRecord, ScheduleError, _private_regular,
                                 _stat_identity, validate_pair)
from .snapshot_retention import (begin_intent, pending_intent, record_storage_stop,
                                 select_retention)


def _validate(actor, registered, *, absent=()):
    if (not actor.active or not actor._slot.locked()
            or current_session(actor.owner.path) is not actor.owner
            or actor._registered_package is not registered or actor.state.last_success != registered):
        raise ScheduleError('Retention requires this active admitted backup durable success')
    actor.owner.validate()
    actor.config._placement(actor.managed.directory)
    actor.locators.validate()
    actor.managed.validate()
    locator, _ = actor.locators.read(actor.config.leaf, locator=True)
    transition, _ = actor.locators.read(actor.config.transition_leaf, transition=True)
    if (locator is None or transition is None or transition.phase != 'committed'
            or transition.locator != locator or locator != actor.state.locator):
        raise ScheduleError('Retention configuration changed or is uncommitted')
    state, version = actor.managed.read('schedule.json')
    if state != actor.state or version != actor.version:
        raise ScheduleError('Retention state changed')
    validate_pair(locator, state, actor.owner)
    if not state.policy.enabled or not state.policy.retention_enabled:
        raise ScheduleError('Retention is no longer explicitly enabled')
    if not actor._cleanup():
        raise ScheduleError('Owned package worker/stage cleanup remains pending')
    allowed = {'schedule.json', 'schedule.lock', *(p.leaf for p in state.packages)}
    seen = set(actor.managed.names())
    if seen - allowed:
        raise ScheduleError('Unknown managed file/stage; preserve and review')
    if seen != allowed - set(absent):
        raise ScheduleError('Managed package inventory changed')
    # The earlier backup reconciliation is not proof against an observable
    # post-registration replacement of an unselected middle ledger package.
    for package in state.packages:
        if package.leaf in absent:
            intent = pending_intent(state)
            if intent is None or package != intent.candidate:
                raise ScheduleError('Only the exact pending candidate may be absent')
            continue
        if actor._facts(package.leaf) != (package.file_identity, package.size, package.sha256):
            raise ScheduleError('Managed ledger package changed after registration')
    # Last observable control checkpoint. The lock is released before native
    # unlink/commit; an action already past this point may complete after a save.
    require_run(actor.config, locator, actor.locators)


def _pinned_facts(actor, descriptor, package):
    """Hash actual pinned leased FD; compare both named and pinned native facts."""
    actor.managed.validate()
    before = os.fstat(descriptor)
    _private_regular(before)
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest, size = hashlib.sha256(), 0
    while True:
        if actor.cancel.is_set():
            raise ScheduleError('Retention canceled while verifying leased package')
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > recovery.MAX_PACKAGE_BYTES:
            raise ScheduleError('Leased package exceeds size bound')
        digest.update(chunk)
    after = os.fstat(descriptor)
    named = os.stat(package.leaf, dir_fd=actor.managed.fd, follow_symlinks=False)
    _private_regular(after)
    _private_regular(named)
    signature = lambda info: (_stat_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if (signature(before) != signature(after) or signature(after) != signature(named)
            or (_stat_identity(after), size, digest.hexdigest()) != (package.file_identity, package.size, package.sha256)
            or size != after.st_size):
        raise ScheduleError('Pinned/named package differs from exact retention ledger')
    return signature(after)


def _final_name(actor, descriptor, package, verified_signature):
    pinned = os.fstat(descriptor)
    named = os.stat(package.leaf, dir_fd=actor.managed.fd, follow_symlinks=False)
    _private_regular(pinned)
    _private_regular(named)
    signature = lambda info: (_stat_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if signature(pinned) != verified_signature or signature(named) != verified_signature:
        raise ScheduleError('Leased package changed after final hash')


def describe_pending(actor):
    """Actual read-only restart classification, with no intent replay/adoption."""
    intent = pending_intent(actor.state)
    if intent is None:
        raise ScheduleError('No pending retention intent')
    def observe(package):
        try:
            actor._facts(package.leaf)
        except FileNotFoundError:
            return 'absent'
        except (ValueError, OSError):
            return 'changed_or_unverifiable'
        try:
            actor._inspect(package.leaf, package)
        except (ValueError, OSError):
            return 'changed_or_unverifiable'
        return 'exact_present'
    return ('Retention intent requires explicit reconciliation: candidate=' + observe(intent.candidate)
            + ', survivor=' + observe(intent.survivor))


def prune_registered(actor, registered, *, held_packages=()):
    """Run only after this original backup's durable registration before _finish.

    Actual candidate EX / survivor SH leases are mandatory; supplied hold facts
    are additional vetoes only. Preserve both leased FDs through durable completion.
    """
    deleted = []
    try:
        _validate(actor, registered)
        while True:
            if actor.cancel.is_set():
                raise ScheduleError('Retention canceled; verified backup retained')
            plan = select_retention(actor.state, held_packages=held_packages)
            if not plan.candidates:
                if plan.stop_reason is not None:
                    if plan.stop_reason == 'protected_storage_limit':
                        actor._save(record_storage_stop(actor.state, operation_id=str(uuid.uuid4()),
                                                       utc=int(actor.config.utc()), held_packages=held_packages))
                    raise ScheduleError('Retention stopped: ' + plan.stop_reason)
                return tuple(deleted)
            if len(actor.state.audit) > 4094:
                raise ScheduleError('Retention audit capacity exhausted before intent')
            candidate, survivor = plan.candidates[0], plan.survivor
            # These are original spawned inspectors and own real SH leases.
            actor._inspect(candidate.leaf, candidate)
            actor._inspect(survivor.leaf, survivor)
            _validate(actor, registered)
            with ExitStack() as leases:
                descriptors = {}
                for package, exclusive in sorted(((candidate, True), (survivor, False)),
                                                  key=lambda item: item[0].file_identity):
                    descriptor, _ = regular_existing(actor.managed.directory / package.leaf, actor.managed.fd)
                    leases.callback(os.close, descriptor)
                    leases.enter_context(package_lease(descriptor, exclusive=exclusive))
                    descriptors[package.leaf] = descriptor
                candidate_fd, survivor_fd = descriptors[candidate.leaf], descriptors[survivor.leaf]
                _pinned_facts(actor, candidate_fd, candidate)
                _pinned_facts(actor, survivor_fd, survivor)
                # SH is compatible with this real child's SH. Never launch a
                # candidate shared reader while our candidate EX is held.
                actor._inspect(survivor.leaf, survivor)
                _validate(actor, registered)
                if actor.cancel.is_set():
                    raise ScheduleError('Retention canceled before durable intent')
                intent = begin_intent(actor.state, candidate, survivor, operation_id=str(uuid.uuid4()),
                                      utc=int(actor.config.utc()), held_packages=held_packages)
                actor._save(intent)
                candidate_signature = _pinned_facts(actor, candidate_fd, candidate)
                survivor_signature = _pinned_facts(actor, survivor_fd, survivor)
                _validate(actor, registered)
                _final_name(actor, candidate_fd, candidate, candidate_signature)
                _final_name(actor, survivor_fd, survivor, survivor_signature)
                if actor.cancel.is_set():
                    raise ScheduleError('Retention canceled after intent; explicit reconciliation required')
                os.unlink(candidate.leaf, dir_fd=actor.managed.fd)
                # No rollback claim after this point, even on cancellation.
                os.fsync(actor.managed.fd)
                if actor.cancel.is_set():
                    raise ScheduleError('Retention canceled after unlink; outcome uncertain')
                _validate(actor, registered, absent=(candidate.leaf,))
                _pinned_facts(actor, survivor_fd, survivor)
                complete = AuditRecord(actor.state.audit[-1].sequence + 1,
                    intent.audit[-1].operation_id, actor.state.locator.revision,
                    int(actor.config.utc()), 'deleted', candidate, survivor)
                actor._save(replace(actor.state,
                    packages=tuple(p for p in actor.state.packages if p != candidate),
                    audit=(*actor.state.audit, complete), status=replace(actor.state.status, outcome='verified')))
                deleted.append(candidate)
    except Exception:
        try:
            # Preserve exact pending audit + original success regardless of
            # observed package absence. Failed CAS keeps the earlier document.
            actor._save(replace(actor.state, status=replace(actor.state.status, outcome='cleanup_warning')))
        except (ValueError, OSError):
            pass
        raise

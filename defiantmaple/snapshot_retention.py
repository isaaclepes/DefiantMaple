"""Pure retention planning and durable intent state; no filesystem deletion.

Future executors must hold the admitted operation slot and locator/managed locks,
inspect candidate AND survivor through the real package pipeline, and reverify
survivor immediately before dirfd-relative unlink. These values grant no I/O
or ownership authority. Pending intents are never executable pathname retries.
"""
from dataclasses import dataclass, replace

from .scheduled_snapshots import (AuditRecord, PackageRecord, ScheduleError,
                                 ScheduleState)


@dataclass(frozen=True)
class RetentionIntent:
    event: AuditRecord

    def __post_init__(self):
        event = self.event
        if (type(event) is not AuditRecord or event.event != 'delete_intent'
                or event.package.schedule_id != event.survivor.schedule_id
                or event.package.file_identity == event.survivor.file_identity):
            raise ScheduleError('Retention intent needs distinct exact candidate/survivor identities')

    @property
    def candidate(self):
        return self.event.package

    @property
    def survivor(self):
        return self.event.survivor

    @property
    def revision(self):
        return self.event.revision


@dataclass(frozen=True)
class RetentionPlan:
    candidates: tuple[PackageRecord, ...]
    survivor: PackageRecord | None
    stop_reason: str | None


def pending_intent(state):
    """Decode the existing strict bounded state audit into one unresolved intent."""
    if type(state) is not ScheduleState:
        raise ScheduleError('Retention requires strict schedule state')
    pending = None
    for event in state.audit:
        if event.event == 'delete_intent':
            if pending is not None:
                raise ScheduleError('Multiple unresolved retention intents')
            pending = RetentionIntent(event)
        elif event.event == 'deleted':
            if (pending is None or event.operation_id != pending.event.operation_id
                    or event.revision != pending.revision or event.package != pending.candidate
                    or event.survivor != pending.survivor):
                raise ScheduleError('Deletion completion does not match its exact intent')
            pending = None
    if pending is not None:
        if (pending.revision != state.locator.revision
                or pending.candidate not in state.packages
                or pending.survivor not in state.packages):
            raise ScheduleError('Pending retention intent differs from current ledger/configuration')
    return pending


def select_retention(state, *, held_packages=()):
    """Oldest-first ledger selection; holds are conservative caller observations.

    Selection is permitted only after a newly registered verified backup. It is
    not permission to delete: current policy, holds and inspected native package
    facts must be checked again by the future executor at each boundary.
    """
    if pending_intent(state) is not None:
        return RetentionPlan((), state.last_success, 'pending_intent')
    if (not isinstance(held_packages, (tuple, list))
            or any(type(p) is not PackageRecord or p not in state.packages for p in held_packages)):
        raise ScheduleError('Unknown package hold')
    policy = state.policy
    packages = state.packages
    survivor = packages[-1] if packages else None
    over = lambda count, size: ((policy.keep_count is not None and count > policy.keep_count)
                               or (policy.byte_limit is not None and size > policy.byte_limit))
    if not policy.enabled:
        return RetentionPlan((), survivor, 'schedule_disabled')
    if state.status.cleanup_pending or state.status.outcome != 'verified' or state.last_success != survivor:
        return RetentionPlan((), survivor, 'not_new_verified_success')
    if not over(len(packages), sum(p.size for p in packages)):
        return RetentionPlan((), survivor, None)
    if not policy.retention_enabled:
        return RetentionPlan((), survivor, 'retention_disabled_storage_limit')
    count, size, candidates = len(packages), sum(p.size for p in packages), []
    for package in packages[:-1]:
        if not over(count, size):
            break
        if package in held_packages:
            continue
        candidates.append(package)
        count, size = count - 1, size - package.size
    reason = 'protected_storage_limit' if over(count, size) else None
    return RetentionPlan(tuple(candidates), survivor, reason)


def record_storage_stop(state, *, operation_id, utc, held_packages=()):
    """State for durable warning when configured caps cannot safely be met."""
    plan = select_retention(state, held_packages=held_packages)
    if plan.stop_reason not in {'retention_disabled_storage_limit', 'protected_storage_limit'}:
        raise ScheduleError('No storage-limit stop to record')
    event = AuditRecord(state.audit[-1].sequence + 1 if state.audit else 1,
                        operation_id, state.locator.revision, utc, 'cleanup_warning',
                        error_code=plan.stop_reason)
    return replace(state, audit=(*state.audit, event),
                   status=replace(state.status, outcome='cleanup_warning'))


def begin_intent(state, candidate, survivor, *, operation_id, utc, held_packages=()):
    """Return state to durably CAS-save BEFORE any future unlink; preserve success."""
    plan = select_retention(state, held_packages=held_packages)
    if not plan.candidates or candidate != plan.candidates[0] or survivor != plan.survivor:
        raise ScheduleError('Candidate/survivor is not current safe retention selection')
    event = AuditRecord(state.audit[-1].sequence + 1 if state.audit else 1,
                        operation_id, state.locator.revision, utc, 'delete_intent', candidate, survivor)
    RetentionIntent(event)
    return replace(state, audit=(*state.audit, event),
                   status=replace(state.status, outcome='uncertain'))


@dataclass(frozen=True)
class IntentObservation:
    candidate: str
    survivor_exact: bool
    canceled: bool
    action: str = 'stop_explicit_reconciliation'


def reconcile_intent(state, *, candidate_facts, survivor_facts, canceled=False):
    """Classify supplied actual inspection facts, never unlink or replay intent.

    None means observed absence; a PackageRecord means observed verified facts.
    Absence after durable intent is post-unlink uncertainty, including cancellation;
    it never asserts rollback or silently removes the ledger entry. A recreated
    same-name file with different identity/digest is always changed.
    """
    intent = pending_intent(state)
    if intent is None:
        raise ScheduleError('No pending retention intent')
    if type(canceled) is not bool or any(p is not None and type(p) is not PackageRecord
                                       for p in (candidate_facts, survivor_facts)):
        raise ScheduleError('Invalid retention inspection observation')
    candidate = ('absent_post_intent' if candidate_facts is None else
                 'exact_present' if candidate_facts == intent.candidate else 'changed_or_recreated')
    observation = IntentObservation(candidate, survivor_facts == intent.survivor, canceled)
    return replace(state, status=replace(state.status, outcome='uncertain')), observation

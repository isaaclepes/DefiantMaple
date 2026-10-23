"""Generated durable state only; no recovery children or unlink executor."""
from dataclasses import replace
import json
import unittest

from defiantmaple.recovery_storage import private_local_parent
from defiantmaple.scheduled_snapshots import (AuditRecord, LockedDirectory, PackageRecord,
    PhaseStatus, Policy, ScheduleError, ScheduleState, decode_document, encode_document)
from defiantmaple.snapshot_retention import (RetentionIntent, begin_intent, pending_intent,
    record_storage_stop, reconcile_intent, select_retention)
from test_scheduled_snapshots import GeneratedFixture

OPERATION = '00000000-0000-4000-8000-000000000099'


class RetentionTests(GeneratedFixture):
    def package(self, sequence, size=700000):
        operation = f'00000000-0000-4000-8000-{sequence:012d}'
        return PackageRecord(self.locator.schedule_id, sequence, operation,
            f'snapshot-{self.locator.schedule_id}-{sequence}-{operation}.dmbackup',
            (1, sequence), size, str(sequence % 10) * 64, 10000 + sequence)

    def state_with(self, count=3, **policy):
        packages = tuple(self.package(n) for n in range(1, count + 1))
        return ScheduleState(self.locator,
            Policy(enabled=True, retention_enabled=True, keep_count=1, **policy),
            PhaseStatus(10000 + count, 10000 + count, 'verified'), count + 1,
            packages, (), packages[-1])

    def intent(self, state=None):
        state = state or self.state_with()
        return begin_intent(state, state.packages[0], state.packages[-1],
                            operation_id=OPERATION, utc=20000)

    def test_oldest_ledger_only_and_protect_newest_under_count_and_bytes(self):
        state = self.state_with(byte_limit=2**20)
        plan = select_retention(state)
        self.assertEqual(plan.candidates, state.packages[:-1])
        self.assertEqual(plan.survivor, state.last_success)
        self.assertIsNone(plan.stop_reason)
        self.assertEqual(select_retention(replace(state, policy=replace(state.policy, keep_count=2, byte_limit=None))).candidates,
                         state.packages[:1])

    def test_real_package_hold_observations_never_selected(self):
        state = self.state_with()
        plan = select_retention(state, held_packages=state.packages[:2])
        self.assertEqual(plan.candidates, ())
        self.assertEqual(plan.stop_reason, 'protected_storage_limit')
        with self.assertRaises(ScheduleError):
            select_retention(state, held_packages=(self.package(7),))
        with self.assertRaises(ScheduleError):
            begin_intent(state, state.packages[0], state.last_success,
                         operation_id=OPERATION, utc=20000, held_packages=state.packages[:1])

    def test_disabled_retention_and_oversize_singleton_stop_preserve_success(self):
        state = self.state_with()
        disabled = replace(state, policy=replace(state.policy, retention_enabled=False))
        self.assertEqual(select_retention(disabled).candidates, ())
        stopped = record_storage_stop(disabled, operation_id=OPERATION, utc=20000)
        self.assertEqual(stopped.last_success, state.last_success)
        self.assertEqual(stopped.packages, state.packages)
        self.assertEqual(stopped.status.outcome, 'cleanup_warning')
        singleton = self.state_with(1, byte_limit=2**20)
        large = replace(singleton.last_success, size=2**20 + 1)
        singleton = replace(singleton, packages=(large,), last_success=large)
        self.assertEqual(select_retention(singleton).stop_reason, 'protected_storage_limit')
        self.assertEqual(select_retention(singleton).candidates, ())

    def test_only_new_registered_success_can_plan_not_failure_cancel_reopen(self):
        state = self.state_with()
        for outcome in ('failed', 'canceled', 'reconciled', 'uncertain', 'cleanup_warning'):
            changed = replace(state, status=replace(state.status, outcome=outcome))
            self.assertEqual(select_retention(changed).candidates, ())
        self.assertEqual(select_retention(replace(state, status=replace(state.status, cleanup_pending=True))).candidates, ())
        self.assertEqual(select_retention(replace(state, policy=replace(state.policy, enabled=False))).candidates, ())

    def test_intent_durable_roundtrip_binds_revision_and_exact_both_packages(self):
        try:
            with private_local_parent(self.managed / 'capability-probe'):
                pass
        except ValueError as exc:
            if str(exc) in {
                    'Recovery publication has no reviewed native adapter on this platform',
                    'Recovery requires a verified durable local filesystem'}:
                self.skipTest('Durable retention persistence requires the reviewed local adapter; ' + str(exc))
            raise
        state = self.state_with()
        pending = self.intent(state)
        intent = pending_intent(pending)
        self.assertEqual(intent.revision, state.locator.revision)
        self.assertEqual(intent.candidate, state.packages[0])
        self.assertEqual(intent.survivor, state.last_success)
        self.assertEqual(pending.last_success, state.last_success)
        self.assertEqual(pending.status.outcome, 'uncertain')
        with LockedDirectory(self.managed, 'schedule.lock') as store:
            version = store.write('schedule.json', pending, None)
            actual, read_version = store.read('schedule.json')
            self.assertEqual(read_version, version)
            self.assertEqual(actual, pending)
        self.assertEqual(pending_intent(actual), intent)
        self.assertEqual(select_retention(actual).stop_reason, 'pending_intent')
        with self.assertRaises(ScheduleError):
            self.intent(actual)
        raw = json.loads(encode_document(pending))
        raw['audit'][0]['survivor']['file_identity'] = list(intent.candidate.file_identity)
        # The strict retention layer additionally refuses physically aliased survivors.
        with self.assertRaises(ScheduleError):
            pending_intent(decode_document(json.dumps(raw).encode()))

    def test_restart_absent_exact_changed_never_replays_and_preserves_success(self):
        state = self.intent()
        intent = pending_intent(state)
        for facts, expected in ((None, 'absent_post_intent'),
                (intent.candidate, 'exact_present'),
                (replace(intent.candidate, file_identity=(2, 99)), 'changed_or_recreated'),
                (replace(intent.candidate, sha256='f' * 64), 'changed_or_recreated')):
            for canceled in (False, True):
                result, observation = reconcile_intent(state, candidate_facts=facts,
                    survivor_facts=intent.survivor, canceled=canceled)
                self.assertEqual(observation.candidate, expected)
                self.assertTrue(observation.survivor_exact)
                self.assertEqual(observation.action, 'stop_explicit_reconciliation')
                self.assertEqual(result.packages, state.packages)
                self.assertEqual(result.last_success, state.last_success)
                self.assertEqual(result.audit, state.audit)
                self.assertEqual(result.status.outcome, 'uncertain')
        _, observation = reconcile_intent(state, candidate_facts=None, survivor_facts=None)
        self.assertFalse(observation.survivor_exact)

    def test_stale_revision_foreign_and_multiple_intents_fail_closed(self):
        state = self.intent()
        with self.assertRaises(ScheduleError):
            pending_intent(replace(state, locator=replace(state.locator, revision=2)))
        with self.assertRaises(ScheduleError):
            pending_intent(replace(state, audit=(*state.audit, replace(state.audit[0], sequence=2))))
        with self.assertRaises(ScheduleError):
            RetentionIntent(replace(state.audit[0], survivor=replace(state.last_success,
                file_identity=state.packages[0].file_identity)))
        wrong = AuditRecord(2, OPERATION, state.locator.revision, 20001, 'deleted',
                            state.packages[1], state.last_success)
        with self.assertRaises(ScheduleError):
            pending_intent(replace(state, audit=(*state.audit, wrong)))


if __name__ == '__main__':
    unittest.main()

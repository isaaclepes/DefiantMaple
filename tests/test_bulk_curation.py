"""Generated catalog outcomes: frozen batch previews, atomic writes and durable undo."""
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from defiantmaple import catalog, curation as api, metadata


class BulkCurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'generated.sqlite3'
        catalog.initialize(self.db)
        with catalog.connect(self.db) as db:
            for identifier, rating, favorite in [('alpha', None, 0), ('beta', 4, 1), ('gamma', 2, 0)]:
                db.execute('INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,rating,favorite) '
                           'VALUES(?,?,?,?,?,?,?)', (identifier, f'/generated/{identifier}.png', 'image/png',
                                                   f'hash-{identifier}', 1, rating, favorite))

    def snapshot(self, path=None):
        with closing(sqlite3.connect(path or self.db)) as db:
            return tuple(db.iterdump())

    def state(self, identifier):
        return api.get_curation(self.db, identifier)

    def plan(self, ids=('alpha', 'beta'), *, rating=5, favorite=api.KEEP):
        return api.preview_curation_batch(self.db, api.capture_curation(self.db, ids),
                                         api.CurationChanges(rating, favorite))

    def test_independent_keep_clear_values_preview_immutability_noop_and_reopen_undo(self):
        before = self.snapshot()
        plan = self.plan(rating=api.KEEP, favorite=True)
        self.assertEqual(plan.changed_count, 1)
        self.assertEqual([(e.after_rating, e.after_favorite) for e in plan.effects], [(None, True), (4, True)])
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(FrozenInstanceError):
            plan.effects[0].target.revision = 99
        result = api.apply_curation_batch(self.db, plan)
        self.assertEqual((result['target_count'], result['changed_count']), (2, 1))
        self.assertEqual(self.state('beta')['revision'], 0)
        self.assertEqual(api.list_curation_edits(self.db, 'alpha'), [])
        catalog.initialize(self.db, create=False)
        group = api.get_curation_batch(self.db, result['batch_id'])
        self.assertEqual([member['asset_id'] for member in group['members']], ['alpha', 'beta'])
        self.assertTrue(group['eligible'])
        api.undo_curation_batch(self.db, result['batch_id'])
        self.assertEqual((self.state('alpha')['rating'], self.state('alpha')['favorite']), (None, False))
        self.assertEqual(self.state('beta')['revision'], 0)
        undone = self.snapshot()
        with self.assertRaises(api.CurationConflict): api.undo_curation_batch(self.db, result['batch_id'])
        self.assertEqual(self.snapshot(), undone)
        noop = self.plan(rating=api.KEEP, favorite=api.KEEP)
        self.assertFalse(api.apply_curation_batch(self.db, noop)['changed'])
        self.assertEqual(self.snapshot(), undone)
        clear = self.plan(rating=None, favorite=False)
        api.apply_curation_batch(self.db, clear)
        self.assertEqual((self.state('beta')['rating'], self.state('beta')['favorite']), (None, False))

    def test_invalid_empty_duplicate_excess_and_forged_inputs_leave_catalog_unchanged(self):
        before = self.snapshot()
        for ids in ([], ['alpha', 'alpha'], ['missing'], [False], list(range(257)), ['alpha'] * 257, 'alpha'):
            with self.subTest(ids=repr(ids)[:40]), self.assertRaises(ValueError):
                api.capture_curation(self.db, ids)
        for rating in (True, 0, 6, 3.0, '3'):
            with self.assertRaises(ValueError): api.CurationChanges(rating=rating)
        for favorite in (None, 0, 1, 'yes'):
            with self.assertRaises(ValueError): api.CurationChanges(favorite=favorite)
        for revision in (True, -1, '0', 0.5):
            with self.assertRaises(ValueError): api.CapturedTarget('alpha', revision)
        for targets in ((), [], ('alpha',), (api.CapturedTarget('alpha', 0),) * 2):
            with self.assertRaises(ValueError): api.preview_curation_batch(self.db, targets, api.CurationChanges())
        plan = self.plan()
        forged = replace(plan, effects=(replace(plan.effects[0], after_rating=1), plan.effects[1]))
        with self.assertRaises(api.CurationConflict): api.apply_curation_batch(self.db, forged)
        with self.assertRaises(ValueError): api.apply_curation_batch(self.db, None)
        for limit in (True, 0, 101, '50'):
            with self.assertRaises(ValueError): api.list_curation_batches(self.db, limit=limit)
        self.assertEqual(self.snapshot(), before)

    def test_maximum_bound_is_atomic_and_history_limit_is_deterministic(self):
        with catalog.connect(self.db) as db:
            for index in range(256):
                db.execute('INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) VALUES(?,?,?,?,?)',
                           (f'bounded-{index}', f'/generated/bounded-{index}.png', 'image/png', 'hash', 1))
        ids = tuple(f'bounded-{index}' for index in range(256))
        result = api.apply_curation_batch(self.db, self.plan(ids, favorite=True))
        self.assertEqual((result['target_count'], result['changed_count']), (256, 256))
        self.assertEqual(len(api.get_curation_batch(self.db, result['batch_id'])['members']), 256)
        api.undo_curation_batch(self.db, result['batch_id'])
        self.assertTrue(all(not self.state(identifier)['favorite'] for identifier in ids))
        latest = api.apply_curation_batch(self.db, self.plan(('gamma',), rating=3))
        self.assertEqual(api.list_curation_batches(self.db, limit=1)[0]['batch_id'], latest['batch_id'])

    def test_any_target_stale_apply_and_undo_including_unchanged_content_path_metadata_aba(self):
        for field, alternative in [('sha256', 'new-hash'), ('current_path', '/generated/renamed.png'),
                                    ('workflow_state', 'reviewed'), ('rating', 1), ('favorite', 0)]:
            with self.subTest(field=field):
                plan = self.plan(rating=4, favorite=api.KEEP)  # beta is unchanged but still guarded.
                with catalog.connect(self.db) as db:
                    old = db.execute(f'SELECT {field} FROM assets WHERE asset_id="beta"').fetchone()[0]
                    db.execute(f'UPDATE assets SET {field}=? WHERE asset_id="beta"', (alternative,))
                    db.execute(f'UPDATE assets SET {field}=? WHERE asset_id="beta"', (old,))
                before = self.snapshot()
                with self.assertRaises(api.CurationConflict): api.apply_curation_batch(self.db, plan)
                self.assertEqual(self.snapshot(), before)
                result = api.apply_curation_batch(self.db, self.plan(rating=4))
                if result['batch_id'] is None:
                    result = api.apply_curation_batch(self.db, self.plan(rating=None))
                with catalog.connect(self.db) as db:
                    old = db.execute(f'SELECT {field} FROM assets WHERE asset_id="beta"').fetchone()[0]
                    db.execute(f'UPDATE assets SET {field}=? WHERE asset_id="beta"', (alternative,))
                    db.execute(f'UPDATE assets SET {field}=? WHERE asset_id="beta"', (old,))
                before = self.snapshot()
                with self.assertRaises(api.CurationConflict): api.undo_curation_batch(self.db, result['batch_id'])
                self.assertEqual(self.snapshot(), before)
        tag = metadata.create_tag(self.db, 'Generated tag')
        result = api.apply_curation_batch(self.db, self.plan(rating=5))
        metadata.assign_tag(self.db, 'beta', tag['tag_id'])
        metadata.unassign_tag(self.db, 'beta', tag['tag_id'])
        before = self.snapshot()
        with self.assertRaises(api.CurationConflict): api.undo_curation_batch(self.db, result['batch_id'])
        self.assertEqual(self.snapshot(), before)

    def test_missing_target_and_catalog_failure_refuse_all_members(self):
        plan = self.plan()
        with catalog.connect(self.db) as db: db.execute('DELETE FROM assets WHERE asset_id="beta"')
        before = self.snapshot()
        with self.assertRaises(ValueError): api.apply_curation_batch(self.db, plan)
        self.assertEqual(self.snapshot(), before)

    def test_fault_after_first_apply_or_undo_effect_rolls_back_assets_and_journal(self):
        plan = self.plan(favorite=True)
        with catalog.connect(self.db) as db:
            db.execute("CREATE TRIGGER generated_apply_failure BEFORE INSERT ON curation_batch_items "
                       "WHEN NEW.position=1 BEGIN SELECT RAISE(ABORT,'generated journal failure'); END")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'generated journal failure'): api.apply_curation_batch(self.db, plan)
        self.assertEqual(self.snapshot(), before)
        with catalog.connect(self.db) as db: db.execute('DROP TRIGGER generated_apply_failure')
        result = api.apply_curation_batch(self.db, plan)
        with catalog.connect(self.db) as db:
            db.execute("CREATE TRIGGER generated_undo_failure BEFORE UPDATE OF rating ON assets "
                       "WHEN NEW.asset_id='beta' AND NEW.rating=4 "
                       "BEGIN SELECT RAISE(ABORT,'generated undo failure'); END")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'generated undo failure'): api.undo_curation_batch(self.db, result['batch_id'])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(api.get_curation_batch(self.db, result['batch_id'])['undone'])

    def test_competing_groups_have_one_winner_and_no_partial_journal(self):
        plans = [self.plan(rating=rating) for rating in (3, 5)]
        barrier = threading.Barrier(2)
        outcomes = []
        def writer(plan):
            barrier.wait()
            try: outcomes.append(api.apply_curation_batch(self.db, plan))
            except api.CurationConflict as exc: outcomes.append(exc)
        threads = [threading.Thread(target=writer, args=(plan,)) for plan in plans]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(sum(isinstance(outcome, dict) for outcome in outcomes), 1)
        self.assertEqual(self.state('alpha')['rating'], self.state('beta')['rating'])
        self.assertEqual(len(api.list_curation_batches(self.db)), 1)

    def test_single_history_never_becomes_group_history_and_explicit_single_undo_invalidates_group(self):
        single = api.set_curation(self.db, 'beta', rating=4, favorite=False, expected_revision=0)
        result = api.apply_curation_batch(self.db, self.plan(rating=4))  # beta unchanged.
        self.assertTrue(api.get_curation_batch(self.db, result['batch_id'])['eligible'])
        api.undo_curation(self.db, single['edit_id'])
        self.assertFalse(api.get_curation_batch(self.db, result['batch_id'])['eligible'])
        before = self.snapshot()
        with self.assertRaises(api.CurationConflict): api.undo_curation_batch(self.db, result['batch_id'])
        with self.assertRaises(ValueError): api.undo_curation(self.db, result['batch_id'])
        self.assertEqual(self.snapshot(), before)
        changed_single = api.set_curation(self.db, 'alpha', rating=3, favorite=False,
                                         expected_revision=self.state('alpha')['revision'])
        group = api.apply_curation_batch(self.db, self.plan(rating=5))
        with self.assertRaises(api.CurationConflict): api.undo_curation(self.db, changed_single['edit_id'])
        later = api.set_curation(self.db, 'alpha', rating=1, favorite=True, expected_revision=self.state('alpha')['revision'])
        api.undo_curation(self.db, later['edit_id'])
        self.assertEqual(self.state('alpha')['rating'], 5)
        self.assertFalse(api.get_curation_batch(self.db, group['batch_id'])['eligible'])

    def test_real_v5_migration_preserves_single_journal_and_failed_v6_upgrade_original_backup(self):
        old = self.root / 'v5.sqlite3'
        with closing(sqlite3.connect(old)) as db:
            db.executescript(catalog.SCHEMA_V5)
            db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) VALUES('legacy','/generated/legacy.png','image/png','hash',1)")
            db.execute("UPDATE assets SET rating=3,favorite=1 WHERE asset_id='legacy'")
            db.execute("INSERT INTO curation_edits(edit_id,asset_id,before_rating,before_favorite,after_rating,after_favorite,expected_revision) "
                       "VALUES('single','legacy',NULL,0,3,1,1)")
            db.commit()
        before = self.snapshot(old)
        real = catalog._migrate_five_to_six
        def fail(db):
            real(db)
            db.execute("UPDATE assets SET rating=5")
            raise OSError('generated v6 DDL fault')
        with patch.object(catalog, '_migrate_five_to_six', side_effect=fail):
            with self.assertRaises(catalog.CatalogMigrationError) as failure: catalog.initialize(old, create=False)
        self.assertEqual(self.snapshot(old), before)
        self.assertEqual(self.snapshot(Path(failure.exception.backup_path)), before)
        result = catalog.initialize(old, create=False)
        self.assertEqual((result['previous_version'], result['schema_version']), (5, 6))
        self.assertEqual(self.snapshot(Path(result['backup_path'])), before)
        self.assertEqual(api.get_curation(old, 'legacy')['rating'], 3)
        self.assertEqual(api.list_curation_edits(old, 'legacy')[0]['edit_id'], 'single')
        self.assertEqual(api.list_curation_batches(old), [])
        api.undo_curation(old, 'single')
        self.assertEqual(api.get_curation(old, 'legacy')['rating'], None)

    def test_v6_group_declaration_authentication_and_incomplete_history_refusal(self):
        batch = api.apply_curation_batch(self.db, self.plan())
        with catalog.connect(self.db) as db:
            db.execute('DELETE FROM curation_batch_items WHERE batch_id=? AND asset_id=?',
                       (batch['batch_id'], 'beta'))
        before = self.snapshot()
        for operation in (api.get_curation_batch, api.undo_curation_batch):
            with self.assertRaisesRegex(ValueError, 'journal is incomplete'):
                operation(self.db, batch['batch_id'])
            self.assertEqual(self.snapshot(), before)
        with catalog.connect(self.db) as db:
            db.execute('DROP TABLE curation_batch_items')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'tables/triggers'): catalog.initialize(self.db, create=False)
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

"""Generated files/catalogs and a read-only argv handler; no installed associations."""
from contextlib import closing
from dataclasses import FrozenInstanceError
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from defiantmaple import catalog, external_actions as api


def _late_ready(*args):
    channel = args[-1]
    time.sleep(.5)
    channel.send({"kind": "ready"})
    if channel.poll(1):
        channel.recv()
    channel.close()


class _MutatingReadyChannel:
    def __init__(self, channel, database):
        self.channel, self.database = channel, database

    def send(self, value):
        if value.get('kind') == 'ready':
            with catalog.connect(self.database) as db:
                db.execute("UPDATE assets SET workflow_state='reviewed'")
        self.channel.send(value)

    def __getattr__(self, name):
        return getattr(self.channel, name)


def _race_helper(*args):
    api._external_helper(*args[:-1], _MutatingReadyChannel(args[-1], args[0]))


class _DelayedPermitChannel:
    def __init__(self, channel):
        self.channel = channel
    def recv(self):
        permit = self.channel.recv()
        time.sleep(2.5)
        return permit
    def __getattr__(self, name):
        return getattr(self.channel, name)


def _delayed_permit_helper(*args):
    api._external_helper(*args[:-1], _DelayedPermitChannel(args[-1]))


class _UnreapableDouble:
    """Policy double only; does not simulate kernel/network interruption."""
    pid = 123
    def __init__(self, *, target, args):
        self.channel = args[-1]
        self.closed = False
    def start(self):
        self.channel.send({"kind": "result", "status": "refused", "message": "generated refusal"})
    def is_alive(self): return True
    def join(self, timeout): pass
    def terminate(self): pass
    def kill(self): pass
    def close(self): self.closed = True


class ExternalActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='generated-external-test-')
        self.addCleanup(self.temp.cleanup)
        # Match the catalog's canonical indexed paths (e.g. macOS /var aliases).
        self.root = Path(self.temp.name).resolve(strict=True)
        self.art = self.root / 'generated-source'
        self.art.mkdir()
        self.media = self.art / "- fictional $(`literal`) ; ' café %.png"
        self.media.write_bytes(b'\x89PNG\r\n\x1a\ngenerated fictional bytes')
        self.database = self.root / 'catalog.sqlite3'
        catalog.initialize(self.database)
        self.asset_id = catalog.index_file(self.database, self.media)
        self.stub = self.root / 'read_only_handler.py'
        self.log = self.root / 'literal-argv.json'
        self.stub.write_text("import json, pathlib, sys\npathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]), encoding='utf-8')\n", encoding='utf-8')
        self.command = api.CommandSpec(sys.executable, (str(self.stub), str(self.log), 'fixed literal $(`never shell`)'))

    def target(self):
        with catalog.connect(self.database) as db:
            row = db.execute('SELECT * FROM assets WHERE asset_id=?', (self.asset_id,)).fetchone()
        return api.capture_target(dict(row))

    def snapshot(self):
        with closing(sqlite3.connect(self.database)) as db:
            return tuple(db.iterdump())

    def run_action(self, *, target=None, action=api.OpenAction.FILE, **kwargs):
        return api.execute_external_action(self.database, target or self.target(), action, self.command, **kwargs)

    def wait_log(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.log.exists():
                try: return json.loads(self.log.read_text(encoding='utf-8'))
                except json.JSONDecodeError: pass
            time.sleep(.01)
        self.fail('Generated read-only handler did not record its dispatch')

    def source_backed(self, health='paused', disposition='indexed'):
        info = self.media.stat()
        with catalog.connect(self.database) as db:
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy,health) VALUES('source','Generated',?,'inbox',?)",
                       (str(self.art), health))
            db.execute("UPDATE assets SET source_id='source' WHERE asset_id=?", (self.asset_id,))
            db.execute('INSERT INTO source_entries(current_path,source_id,byte_size,modified_ns,device,inode,stable_since_ns,observed_at_ns,preexisting,disposition,asset_id) '
                       'VALUES(?,?,?,?,?,?,?,?,1,?,?)', (str(self.media), 'source', info.st_size, info.st_mtime_ns,
                        str(info.st_dev), str(info.st_ino), info.st_mtime_ns, info.st_mtime_ns, disposition, self.asset_id))

    def test_permitted_acknowledgement_timeout_is_uncertain_without_late_dispatch(self):
        context = multiprocessing.get_context("spawn")
        def factory(**kwargs):
            return context.Process(target=_delayed_permit_helper, args=kwargs["args"])
        before = self.snapshot()
        result = self.run_action(limits=api.ActionLimits(2.0), process_factory=factory)
        self.assertEqual(result.status, "uncertain")
        self.assertTrue(result.permit_sent)
        self.assertFalse(result.dispatched)
        self.assertTrue(result.cleanup_complete)
        time.sleep(2.55)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(multiprocessing.active_children(), [])

    def test_cleanup_failure_retains_ownership_instead_of_returning_clean_result(self):
        doubles = []
        def factory(**kwargs):
            process = _UnreapableDouble(**kwargs)
            doubles.append(process)
            return process
        with self.assertRaises(RuntimeError) as raised:
            self.run_action(process_factory=factory)
        self.assertIs(raised.exception.process, doubles[0])
        self.assertFalse(doubles[0].closed)
        self.assertFalse(self.log.exists())

    def test_literal_adversarial_file_and_folder_dispatch_preserves_catalog_and_original(self):
        before = self.snapshot()
        source = (self.media.read_bytes(), self.media.stat().st_mtime_ns)
        target = self.target()
        with self.assertRaises(FrozenInstanceError): target.path = '/different.png'
        result = self.run_action(target=target)
        self.assertEqual(result.status, 'requested')
        self.assertTrue(result.permit_sent and result.dispatched and result.cleanup_complete)
        self.assertEqual(self.wait_log(), ['fixed literal $(`never shell`)', str(self.media)])
        self.log.unlink()
        result = self.run_action(action=api.OpenAction.FOLDER)
        self.assertEqual(result.status, 'requested')
        self.assertEqual(self.wait_log(), ['fixed literal $(`never shell`)', str(self.art)])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((self.media.read_bytes(), self.media.stat().st_mtime_ns), source)
        self.assertFalse((self.root / 'never shell').exists())

    def test_probe_only_real_spawn_ready_never_grants_dispatch(self):
        before = self.snapshot()
        result = self.run_action(probe_only=True)
        self.assertEqual(result.status, 'probe_ready')
        self.assertFalse(result.permit_sent or result.dispatched)
        self.assertTrue(result.cleanup_complete)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.snapshot(), before)

    def test_catalog_revision_path_content_aba_and_unknown_identity_refuse_without_dispatch(self):
        for field, value in [('workflow_state', 'reviewed'), ('current_path', str(self.art / 'changed.png')),
                             ('sha256', 'a' * 64), ('rating', 3)]:
            with self.subTest(field=field):
                target = self.target()
                with catalog.connect(self.database) as db:
                    original = db.execute(f'SELECT {field} FROM assets WHERE asset_id=?', (self.asset_id,)).fetchone()[0]
                    db.execute(f'UPDATE assets SET {field}=? WHERE asset_id=?', (value, self.asset_id))
                    db.execute(f'UPDATE assets SET {field}=? WHERE asset_id=?', (original, self.asset_id))
                before = self.snapshot()
                result = self.run_action(target=target)
                self.assertEqual(result.status, 'refused')
                self.assertFalse(result.dispatched or self.log.exists())
                self.assertEqual(self.snapshot(), before)

    def test_unscanned_content_missing_nonregular_and_symlink_changes_refuse(self):
        target = self.target()
        original = self.media.read_bytes()
        self.media.write_bytes(original[:-1] + b'x')
        self.assertEqual(self.run_action(target=target).status, 'refused')
        self.media.unlink()
        self.assertEqual(self.run_action(target=target).status, 'refused')
        self.media.mkdir()
        self.assertEqual(self.run_action(target=target).status, 'refused')
        self.media.rmdir()
        other = self.art / 'identical.png'
        other.write_bytes(original)
        try:
            self.media.symlink_to(other)
        except OSError as exc:
            self.skipTest(f'Symlink creation unavailable on this test host: {exc}')
        result = self.run_action(target=target)
        self.assertEqual(result.status, 'refused')
        self.assertIn('symlink', result.message)
        self.assertFalse(self.log.exists())

    def test_observed_source_states_exact_entry_and_paused_standalone_contract(self):
        self.source_backed()
        target = self.target()
        for health in ('paused', 'watching'):
            with catalog.connect(self.database) as db: db.execute('UPDATE sources SET health=?', (health,))
            self.assertEqual(self.run_action(target=target, probe_only=True).status, 'probe_ready')
        for health in ('scanning', 'offline', 'permission_denied', 'error'):
            with catalog.connect(self.database) as db: db.execute('UPDATE sources SET health=?', (health,))
            before = self.snapshot()
            result = self.run_action(target=target)
            self.assertEqual(result.status, 'refused')
            self.assertIn('explicit scan', result.message)
            self.assertEqual(self.snapshot(), before)
        with catalog.connect(self.database) as db:
            db.execute("UPDATE sources SET health='paused'")
            db.execute("UPDATE source_entries SET disposition='missing'")
        result = self.run_action(target=self.target())
        self.assertEqual(result.status, 'refused')
        self.assertIn('missing', result.message)
        self.assertFalse(self.log.exists())
        with catalog.connect(self.database) as db: db.execute('DELETE FROM source_entries')
        self.assertEqual(self.run_action().status, 'refused')

    def test_final_catalog_recheck_refuses_writer_race_after_ready(self):
        def factory(**kwargs):
            return multiprocessing.get_context('spawn').Process(target=_race_helper, args=kwargs['args'])
        result = self.run_action(process_factory=factory)
        self.assertEqual(result.status, 'refused')
        self.assertTrue(result.permit_sent)
        self.assertFalse(result.dispatched or self.log.exists())

    def test_late_ready_timeout_and_cancel_have_no_permit_or_late_dispatch_and_reap(self):
        children = {child.pid for child in multiprocessing.active_children()}
        def factory(**kwargs):
            return multiprocessing.get_context('spawn').Process(target=_late_ready, args=kwargs['args'])
        result = self.run_action(limits=api.ActionLimits(.15), process_factory=factory)
        self.assertEqual(result.status, 'timeout')
        self.assertFalse(result.permit_sent or result.dispatched)
        cancelled = threading.Event()
        timer = threading.Timer(.15, cancelled.set)
        timer.start()
        try:
            result = self.run_action(cancel_event=cancelled, process_factory=factory)
        finally:
            timer.join()
        self.assertEqual(result.status, 'cancelled')
        self.assertFalse(result.permit_sent or result.dispatched or self.log.exists())
        self.assertEqual({child.pid for child in multiprocessing.active_children()}, children)

    def test_missing_tool_byte_bound_and_known_dispatch_rejection(self):
        target = self.target()
        result = api.execute_external_action(self.database, target, api.OpenAction.FILE,
                    api.CommandSpec(str(self.root / 'missing-tool')))
        self.assertEqual(result.status, 'refused')
        result = self.run_action(limits=api.ActionLimits(max_source_bytes=1))
        self.assertEqual(result.status, 'refused')
        self.assertFalse(result.dispatched or self.log.exists())
        with patch.object(api.subprocess, 'Popen', side_effect=PermissionError('generated denial')):
            with self.assertRaises(api.DispatchRejected): api._dispatch(self.command, str(self.media))
        with patch.object(api, '_default_association', return_value=None) as association:
            api._dispatch(api.CommandSpec(), str(self.media))
        association.assert_called_once_with(str(self.media))

    def test_structured_argv_no_shell_and_invalid_values_are_refused_lexically(self):
        with patch.object(api.subprocess, 'Popen') as popen:
            api._dispatch(self.command, str(self.media))
        argv = popen.call_args.args[0]
        self.assertEqual(argv, [sys.executable, *self.command.fixed_args, str(self.media)])
        self.assertIs(popen.call_args.kwargs['shell'], False)
        for executable, args in [('relative', ()), (str(self.root / 'tool.cmd'), ()), (None, ('extra',)),
                                 (sys.executable, ['text']), (sys.executable, ('a\0b',)),
                                 (sys.executable, tuple('x' for _ in range(33)))]:
            with self.subTest(executable=executable), self.assertRaises(ValueError): api.CommandSpec(executable, args)
        for timeout in (True, 0, -1, float('nan'), float('inf'), 31):
            with self.assertRaises(ValueError): api.ActionLimits(timeout)
        # Database fixture setup is outside the GUI capture/no-I/O boundary.
        with catalog.connect(self.database) as db:
            asset = dict(db.execute('SELECT * FROM assets WHERE asset_id=?', (self.asset_id,)).fetchone())
        expected = api.capture_target(asset)
        with patch.object(api.Path, 'stat', side_effect=AssertionError('GUI stat')), \
                patch.object(api.Path, 'resolve', side_effect=AssertionError('GUI resolve')), \
                patch.object(api.Path, 'open', side_effect=AssertionError('GUI open')):
            target = api.capture_target(asset)
            self.assertEqual(target, expected)
            with self.assertRaises(FrozenInstanceError): target.revision = 99

    def test_local_settings_atomic_roundtrip_bound_and_source_location_refusal(self):
        settings_path = self.root / 'local-settings' / 'external.json'
        before = self.snapshot()
        settings = api.ExternalSettings(self.command, api.CommandSpec())
        self.assertEqual(api.load_external_settings(self.database, settings_path), api.ExternalSettings())
        api.save_external_settings(self.database, settings_path, settings)
        self.assertEqual(api.load_external_settings(self.database, settings_path), settings)
        self.assertEqual(api.execute_settings_task(self.database, settings_path), settings)
        self.source_backed()
        before = self.snapshot()
        for forbidden in (self.database, self.art / 'settings.json'):
            with self.assertRaises(ValueError): api.save_external_settings(self.database, forbidden, settings)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.art / 'settings.json').exists())
        self.assertEqual(list(settings_path.parent.glob('*.tmp')), [])


if __name__ == '__main__':
    multiprocessing.freeze_support()
    unittest.main()

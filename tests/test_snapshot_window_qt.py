"""Generated window wiring with a fake scheduling backend; no recovery Process."""
from pathlib import Path
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

try:
    from PySide6.QtCore import QObject, Signal, QThread
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None

if QApplication is not None:
    from prototypes.qt import app as gallery_app
    from prototypes.qt.scheduled_snapshots_qt import ScheduleView
    from prototypes.qt.tests.gallery_wait import wait_for_startup_validation, close_window_and_wait, _wait
from defiantmaple.catalog import initialize


@unittest.skipIf(QApplication is None, 'PySide6 is not installed')
class SnapshotWindowTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Match the admitted owner's canonical path, including Windows short
        # names and redirected temporary-directory components.
        self.root = Path(self.temp.name).resolve(strict=True)
        self.database = self.root / 'generated.sqlite3'
        initialize(self.database)
        self.owner = Mock()
        self.owner.path = self.database
        self.owner.reap_owned_processes.return_value = 0
        self.windows = []
        class Controller(QObject):
            changed = Signal(object)
            idleChanged = Signal(bool)
            def __init__(inner, config, parent):
                super().__init__(parent)
                inner.view = ScheduleView('unconfigured')
                inner.idle = True
                inner.closing = False
                inner.checks = 0
                inner.close_calls = 0
                inner.cancel_calls = 0
            def attach_manual_registry(inner, registry): inner.registry = registry
            def check(inner):
                inner.checks += 1
                inner.changed.emit(inner.view)
            def begin_close(inner):
                inner.close_calls += 1
                inner.closing = True
                inner.registry.begin_close()
            def cancel_operation(inner): inner.cancel_calls += 1
            def disable(inner): pass
            def snapshot_now(inner): pass
            def resume_after_close_refusal(inner):
                inner.closing = False
                inner.check()
        self.controller_class = Controller

    def tearDown(self):
        for window in self.windows:
            if window.snapshot_controller is not None:
                window.snapshot_controller.idle = True
            close_window_and_wait(window, self.app)

    def window(self, owner):
        with patch.object(gallery_app, 'current_session', return_value=owner), \
             patch.object(gallery_app, 'SnapshotConfiguration') as configuration, \
             patch.object(gallery_app, 'SnapshotController', self.controller_class):
            window = gallery_app.GalleryWindow(self.database,
                cache_root=self.root / 'cache', private_root=self.root / 'private',
                schedule_application_data_root=self.root / 'schedule-profile')
            self.windows.append(window)
            self.assertIsNone(window.snapshot_controller)
            configuration.assert_not_called()
            window.show()
            wait_for_startup_validation(window)
            self.wait_initialization(window)
            if owner is not None:
                configuration.assert_called_once_with(owner, self.root / 'schedule-profile',
                                                       cache_roots=(self.root / 'cache',),
                                                       locator_profile='custom')
            else:
                configuration.assert_not_called()
        return window

    def wait_initialization(self, window):
        _wait(window.snapshotInitializationFinished,
              lambda: window._snapshot_initialization is None,
              description='snapshot initialization thread cleanup', window=window)

    def initialization_window(self):
        # Start initialization explicitly after the original startup gate, so
        # failure injection targets only the snapshot job.
        with patch.object(gallery_app, 'current_session', return_value=self.owner), \
             patch.object(gallery_app.GalleryWindow, '_start_snapshot_controller'):
            window = gallery_app.GalleryWindow(self.database,
                cache_root=self.root / 'cache', private_root=self.root / 'private',
                schedule_application_data_root=self.root / 'schedule-profile')
            self.windows.append(window)
            window.show()
            wait_for_startup_validation(window)
        return window

    def test_canonical_owner_matches_normalized_window_database(self):
        # A lexical alias exercises the constructor's real normalization on all
        # platforms without requiring privileged Windows symlink creation.
        parent = self.root / 'alias-parent'
        parent.mkdir()
        alias = parent / '..' / self.database.name
        canonical = self.database
        self.database = alias
        try:
            window = self.window(self.owner)
        finally:
            self.database = canonical
        self.assertEqual(window.database, self.owner.path)
        self.assertIsNotNone(window.snapshot_controller)

    def test_original_configuration_and_cache_normalization_run_off_gui(self):
        from defiantmaple import snapshot_configuration
        original = snapshot_configuration._cache_roots
        seen = []
        def guarded(roots):
            self.assertIsNot(QThread.currentThread(), self.app.thread())
            seen.append(threading.get_ident())
            return original(roots)
        window = self.initialization_window()
        with patch.object(snapshot_configuration, '_cache_roots', guarded), \
             patch.object(gallery_app, 'SnapshotController', self.controller_class):
            window._start_snapshot_controller()
            self.wait_initialization(window)
        self.assertEqual(len(seen), 1)
        self.assertIsNotNone(window.snapshot_controller)
        self.owner.retain.assert_called_once()
        self.owner.release.assert_called_once()
        self.assertFalse((self.root / 'schedule-profile').exists())

    def test_never_started_failure_releases_owner_and_manual_gate(self):
        window = self.initialization_window()
        with patch.object(gallery_app._SnapshotInitialization, 'start', side_effect=RuntimeError('start refused')):
            window._start_snapshot_controller()
        self.assertIsNone(window._snapshot_initialization)
        self.assertIsNone(window.manual_registry.admission_gate)
        self.owner.release.assert_called_once()
        self.assertTrue(window.open_recovery().backup_button.isEnabled())

    def test_constructor_failure_restores_manual_availability(self):
        window = self.initialization_window()
        with patch.object(gallery_app, 'SnapshotConfiguration', side_effect=ValueError('bad cache')):
            window._start_snapshot_controller()
            self.wait_initialization(window)
        self.assertIsNone(window.snapshot_controller)
        self.assertIsNone(window.manual_registry.admission_gate)
        self.assertTrue(window.open_recovery().backup_button.isEnabled())
        self.owner.release.assert_called_once()

    def test_live_start_error_retains_owner_until_actual_finished(self):
        self.blocked_initialization(close=False, start_error=True)

    def test_close_waits_for_constructor_and_prevents_late_controller(self):
        self.blocked_initialization(close=True, start_error=False)

    def test_stale_epoch_prevents_late_controller(self):
        self.blocked_initialization(close=False, start_error=False, stale=True)

    def blocked_initialization(self, *, close, start_error, stale=False):
        window = self.initialization_window()
        entered, release = threading.Event(), threading.Event()
        original_start = gallery_app._SnapshotInitialization.start
        def constructor(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise AssertionError('test constructor release timed out')
            return object()
        def starts_then_raises(job):
            original_start(job)
            if not entered.wait(5):
                raise AssertionError('constructor did not start')
            raise RuntimeError('started then failed')
        with patch.object(gallery_app, 'SnapshotConfiguration', constructor), \
             patch.object(gallery_app, 'SnapshotController', self.controller_class):
            try:
                if start_error:
                    with patch.object(gallery_app._SnapshotInitialization, 'start', starts_then_raises):
                        window._start_snapshot_controller()
                else:
                    window._start_snapshot_controller()
                    self.assertTrue(entered.wait(5))
                self.assertIsNotNone(window._snapshot_initialization)
                self.owner.release.assert_not_called()
                self.assertIsNotNone(window.manual_registry.admission_gate)
                if stale:
                    window._recovery_state_epoch += 1
                if close:
                    self.assertFalse(window.close())
                    self.owner.release_coordinator.assert_not_called()
            finally:
                release.set()
                self.wait_initialization(window)
        self.assertIsNone(window.snapshot_controller)
        self.assertIsNone(window.manual_registry.admission_gate)
        self.owner.release.assert_called_once()

    def test_unadmitted_window_does_not_lookup_profile_or_block_original_manual(self):
        window = self.window(None)
        self.assertIsNone(window.snapshot_controller)
        self.assertFalse(window.snapshot_button.isEnabled())
        dialog = window.open_recovery()
        self.assertIsNone(dialog.registry)
        self.assertTrue(dialog.backup_button.isEnabled())
        self.assertFalse((self.root / 'schedule-profile').exists())

    def test_admitted_window_owns_controller_registry_and_hiding_settings_does_not_stop(self):
        window = self.window(self.owner)
        controller = window.snapshot_controller
        self.assertIs(controller.parent(), window)
        self.assertIs(window.manual_registry.parent(), window)
        self.assertEqual(controller.checks, 1)
        dialog = window.open_recovery()
        self.assertIs(dialog.registry, window.manual_registry)
        settings = window.open_snapshot_settings()
        self.assertIs(settings.parent(), window)
        settings.close()
        self.assertEqual(controller.close_calls, 0)
        self.assertEqual(controller.cancel_calls, 0)
        self.assertIs(window.snapshot_settings, settings)
        self.assertFalse((self.root / 'schedule-profile').exists())

    def test_scheduler_and_name_preview_coexist_without_catalog_or_source_writes(self):
        from PIL import Image
        from defiantmaple import metadata
        from defiantmaple.catalog import connect, index_file
        from prototypes.qt.tests.gallery_wait import (wait_for_initial_generation,
            wait_for_rank, wait_for_selected_asset, wait_for_gateway_condition)
        image = self.root / 'fictional.png'
        Image.new('RGB', (16, 16), (30, 80, 120)).save(image)
        asset_id = index_file(self.database, image)
        tag = metadata.create_tag(self.database, 'Fictional landscape')
        metadata.assign_tag(self.database, asset_id, tag['tag_id'])
        location = metadata.create_entity(self.database, 'Location', 'Fictional Location')
        metadata.assign_entity(self.database, asset_id, location['entity_id'])
        def files():
            return {p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                    for p in (self.database, image)}
        before = files()
        with connect(self.database) as db:
            before_dump = tuple(db.iterdump())
        window = self.window(self.owner)
        controller = window.snapshot_controller
        wait_for_initial_generation(window, expected_count=1)
        row = wait_for_rank(window, asset_id)
        window.gallery.setCurrentIndex(window.model.index(row))
        wait_for_selected_asset(window, asset_id, row=row)
        observed = []
        def inspect_preview(dialog):
            try:
                self.assertEqual(dialog.asset_id, asset_id)
                self.assertEqual(dialog.projection, {})
                dialog.fields['tags'].click()
                self.assertEqual(dialog.projection, {'tags': ['Fictional landscape']})
                self.assertNotIn('Fictional Location', dialog.values.toPlainText())
                settings = window.open_snapshot_settings()
                self.assertIs(settings.controller, controller)
                settings.close()
                self.assertIs(window.snapshot_controller, controller)
                self.assertIs(controller.registry, window.manual_registry)
                self.assertEqual((controller.close_calls, controller.cancel_calls), (0, 0))
                observed.append('scheduler-and-captured-redacted-preview')
                return 0
            finally:
                dialog.close()
        def inspect_editor(editor):
            try:
                wait_for_gateway_condition(window, lambda: editor.preview_button.isEnabled(),
                                           description='merged metadata preview readiness')
                with patch.object(gallery_app.MetadataNamePreview, 'exec', inspect_preview):
                    editor.preview_button.click()
                return 0
            finally:
                editor.close()
        with patch.object(gallery_app.MetadataEditor, 'exec', inspect_editor):
            window.metadata_button.click()
        self.assertEqual(observed, ['scheduler-and-captured-redacted-preview'])
        with connect(self.database) as db:
            self.assertEqual(tuple(db.iterdump()), before_dump)
        self.assertEqual(files(), before)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux locator profile provenance')
    def test_default_and_explicit_xdg_profile_origin_reaches_background_configuration(self):
        home = self.root / 'home'
        home.mkdir(mode=0o700)
        xdg = self.root / 'xdg'
        xdg.mkdir(mode=0o700)
        for xdg_value, expected_root, expected_profile in (
                (None, home / '.local/share/DefiantMaple', 'implicit_linux_default'),
                (str(xdg), xdg / 'DefiantMaple', 'explicit_xdg')):
            with self.subTest(profile=expected_profile), patch.dict(os.environ, {'HOME': str(home)}), \
                 patch.object(gallery_app, 'current_session', return_value=self.owner), \
                 patch.object(gallery_app, 'SnapshotConfiguration') as configuration, \
                 patch.object(gallery_app, 'SnapshotController', self.controller_class):
                if xdg_value is None:
                    os.environ.pop('XDG_DATA_HOME', None)
                else:
                    os.environ['XDG_DATA_HOME'] = xdg_value
                window = gallery_app.GalleryWindow(self.database, cache_root=self.root / 'cache')
                self.windows.append(window)
                window.show()
                wait_for_startup_validation(window)
                self.wait_initialization(window)
                configuration.assert_called_once_with(self.owner, expected_root,
                    cache_roots=(self.root / 'cache',), locator_profile=expected_profile)
                self.assertFalse((expected_root / 'scheduled-snapshots-v1').exists())

    def test_window_close_retains_coordinator_until_actual_controller_idle_signal(self):
        window = self.window(self.owner)
        controller = window.snapshot_controller
        controller.idle = False
        self.assertFalse(window.close())
        self.assertTrue(controller.closing)
        self.owner.release_coordinator.assert_not_called()
        controller.idle = True
        controller.idleChanged.emit(True)
        close_window_and_wait(window, self.app)
        self.owner.release_coordinator.assert_called_once()

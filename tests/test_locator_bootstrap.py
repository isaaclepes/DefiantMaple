"""Focused generated-profile regressions for explicit schedule locator bootstrap."""
import os
from pathlib import Path
import stat
from unittest.mock import patch

from defiantmaple.admission import admission_session
from defiantmaple.recovery_storage import private_local_parent
from defiantmaple.scheduled_snapshots import Policy, StateUncertainError
from defiantmaple.snapshot_configuration import SnapshotConfiguration
from test_scheduled_snapshots import GeneratedFixture


def mode(path):
    return stat.S_IMODE(path.lstat().st_mode)


class LocatorBootstrapTests(GeneratedFixture):
    def setUp(self):
        super().setUp()
        try:
            with private_local_parent(self.root / "capability-probe"):
                pass
        except ValueError as exc:
            if str(exc) in {"Recovery publication has no reviewed native adapter on this platform",
                            "Recovery requires a verified durable local filesystem"}:
                self.skipTest(str(exc))
            raise

    def configure(self, app_data, profile="custom"):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config = SnapshotConfiguration(owner, app_data, cache_roots=(), utc=lambda: 10000,
                                           locator_profile=profile)
            return config.configure(Policy(enabled=True), managed_directory=self.root / "new-managed")

    def test_explicit_xdg_owned_0755_parent_preserved_and_locator_private(self):
        xdg = self.root / "xdg"
        xdg.mkdir(mode=0o700)
        app = xdg / "DefiantMaple"
        app.mkdir(mode=0o755)
        app.chmod(0o755)
        before = app.stat()
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(xdg)}):
            with admission_session(self.database, _registry_path=self.registry) as owner:
                config = SnapshotConfiguration(owner, app, cache_roots=(), utc=lambda: 10000,
                                               locator_profile="explicit_xdg")
                self.assertEqual(config.discover().status, "unconfigured")
                self.assertFalse(config.root.exists())
                config.configure(Policy(enabled=True), managed_directory=self.root / "new-managed")
        self.assertEqual((app.stat().st_dev, app.stat().st_ino, mode(app)),
                         (before.st_dev, before.st_ino, 0o755))
        self.assertEqual(mode(app / "scheduled-snapshots-v1"), 0o700)
        with self.assertRaises(ValueError):
            with private_local_parent(app / "direct-publication"):
                pass

    def test_implicit_default_creates_only_known_missing_suffix(self):
        home = self.root / "home"
        home.mkdir(mode=0o700)
        app = home / ".local/share/DefiantMaple"
        with patch.dict(os.environ, {"HOME": str(home)}):
            self.configure(app, "implicit_linux_default")
        for path in (home / ".local", home / ".local/share", app,
                     app / "scheduled-snapshots-v1"):
            self.assertEqual(mode(path), 0o700)

    def test_implicit_default_keeps_existing_0755_profile_components(self):
        home = self.root / "home"
        home.mkdir(mode=0o700)
        local = home / ".local"
        local.mkdir(mode=0o755)
        local.chmod(0o755)
        share = local / "share"
        share.mkdir(mode=0o755)
        share.chmod(0o755)
        with patch.dict(os.environ, {"HOME": str(home)}):
            self.configure(share / "DefiantMaple", "implicit_linux_default")
        self.assertEqual((mode(local), mode(share)), (0o755, 0o755))
        self.assertEqual(mode(share / "DefiantMaple/scheduled-snapshots-v1"), 0o700)

    def test_explicit_xdg_existing_0755_base_creates_app_component(self):
        xdg = self.root / "xdg"
        xdg.mkdir(mode=0o755)
        xdg.chmod(0o755)
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(xdg)}):
            self.configure(xdg / "DefiantMaple", "explicit_xdg")
        self.assertEqual(mode(xdg), 0o755)
        self.assertEqual(mode(xdg / "DefiantMaple"), 0o700)

    def test_missing_explicit_and_custom_bases_refuse_without_creation(self):
        xdg = self.root / "missing-xdg"
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(xdg)}):
            with self.assertRaisesRegex(ValueError, "base must already exist"):
                self.configure(xdg / "DefiantMaple", "explicit_xdg")
        custom = self.root / "missing-custom"
        with self.assertRaisesRegex(ValueError, "base must already exist"):
            self.configure(custom)
        self.assertFalse(xdg.exists())
        self.assertFalse(custom.exists())

    def test_symlink_writable_parent_and_unsafe_existing_locator_refuse(self):
        xdg = self.root / "xdg"
        xdg.mkdir(mode=0o700)
        app = xdg / "DefiantMaple"
        target = self.root / "target"
        target.mkdir(mode=0o700)
        app.symlink_to(target, target_is_directory=True)
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(xdg)}):
            with self.assertRaises((ValueError, OSError)):
                self.configure(app, "explicit_xdg")
        self.assertFalse((target / "scheduled-snapshots-v1").exists())
        app.unlink()
        app.mkdir(mode=0o775)
        app.chmod(0o775)
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(xdg)}):
            with self.assertRaises(ValueError):
                self.configure(app, "explicit_xdg")
        self.assertFalse((app / "scheduled-snapshots-v1").exists())
        app.chmod(0o700)
        locator = app / "scheduled-snapshots-v1"
        locator.mkdir(mode=0o755)
        locator.chmod(0o755)
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(xdg)}):
            with self.assertRaises(ValueError):
                self.configure(app, "explicit_xdg")
        self.assertEqual(mode(locator), 0o755)

    def test_child_and_parent_fsync_failure_leave_uncertain_unpublished(self):
        for fail_call in (1, 2):
            with self.subTest(fail_call=fail_call):
                app = self.root / f"app-{fail_call}"
                app.mkdir(mode=0o755)
                app.chmod(0o755)
                calls = 0
                real_fsync = os.fsync
                def fail_once(fd):
                    nonlocal calls
                    calls += 1
                    if calls == fail_call:
                        raise OSError("generated fsync failure")
                    return real_fsync(fd)
                with patch("defiantmaple.locator_bootstrap.os.fsync", side_effect=fail_once):
                    with self.assertRaises(StateUncertainError):
                        self.configure(app)
                locator = app / "scheduled-snapshots-v1"
                self.assertEqual(mode(locator), 0o700)
                self.assertEqual(list(locator.iterdir()), [])
                self.assertFalse((self.root / "new-managed").exists())

    def test_retry_reestablishes_existing_locator_durability_before_publish(self):
        app = self.root / "app-data"
        app.mkdir(mode=0o755)
        app.chmod(0o755)
        real_fsync = os.fsync
        first = 0
        def fail_first_parent(fd):
            nonlocal first
            first += 1
            if first == 2:
                raise OSError("generated parent fsync failure")
            return real_fsync(fd)
        with patch("defiantmaple.locator_bootstrap.os.fsync", side_effect=fail_first_parent):
            with self.assertRaises(StateUncertainError):
                self.configure(app)
        locator = app / "scheduled-snapshots-v1"
        self.assertEqual(mode(locator), 0o700)
        self.assertEqual(list(locator.iterdir()), [])
        retry_calls = 0
        def fail_retry_barrier(fd):
            nonlocal retry_calls
            retry_calls += 1
            raise OSError("generated retry barrier failure")
        with patch("defiantmaple.locator_bootstrap.os.fsync", side_effect=fail_retry_barrier):
            with self.assertRaises(StateUncertainError):
                self.configure(app)
        self.assertEqual(retry_calls, 1)
        self.assertEqual(list(locator.iterdir()), [])
        self.assertFalse((self.root / "new-managed").exists())
        self.configure(app)
        self.assertTrue((locator / next(p.name for p in locator.iterdir()
                                          if p.name.endswith(".json"))).is_file())

    def test_parent_replacement_after_child_creation_refuses_publication(self):
        xdg = self.root / "xdg"
        xdg.mkdir(mode=0o700)
        app = xdg / "DefiantMaple"
        app.mkdir(mode=0o755)
        app.chmod(0o755)
        displaced = xdg / "displaced-app"
        from defiantmaple import locator_bootstrap
        original = locator_bootstrap._revalidate
        def replace_after_create(chain, created_paths):
            if created_paths and not displaced.exists():
                app.rename(displaced)
                app.mkdir(mode=0o700)
            return original(chain, created_paths)
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(xdg)}):
            with patch("defiantmaple.locator_bootstrap._revalidate", side_effect=replace_after_create):
                with self.assertRaises(StateUncertainError):
                    self.configure(app, "explicit_xdg")
        self.assertFalse((app / "scheduled-snapshots-v1").exists())
        self.assertTrue((displaced / "scheduled-snapshots-v1").is_dir())
        self.assertFalse((self.root / "new-managed").exists())

    def test_storage_policy_refusal_is_not_bypassed_by_bootstrap(self):
        app = self.root / "app-data"
        app.mkdir(mode=0o755)
        app.chmod(0o755)
        # Policy double tests the refusal branch; real backing qualification is
        # covered only by the platform/native fixture gate.
        with patch("defiantmaple.locator_bootstrap._local_backing", return_value=False):
            with self.assertRaisesRegex(ValueError, "verified durable local filesystem"):
                self.configure(app)
        self.assertFalse((app / "scheduled-snapshots-v1").exists())

"""Recovery-format checks using disposable Alfred and Bartender data."""

from contextlib import closing, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import plistlib
import sqlite3
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from lib.localbackup import archive, config, restore, scheduler
from lib.localbackup.apps import alfred, bartender
from lib.localbackup.common import BackupError
from lib.localbackup.cli import main, parser


class LocalBackupTests(unittest.TestCase):
    def test_alfred_archives_preserve_restore_layout_and_recent_sqlite_data(self):
        with tempfile.TemporaryDirectory(prefix="localbackup-test-") as temporary:
            home = Path(temporary)
            source = home / "Library/Application Support/Alfred"
            prefs = source / "Alfred.alfredpreferences"
            data = source / "Workflow Data/com.example.workflow"
            prefs.mkdir(parents=True)
            data.mkdir(parents=True)
            (prefs / "info.plist").write_bytes(plistlib.dumps({"name": "Test Workflow"}))
            database = data / "settings.db"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("CREATE TABLE settings (value TEXT)")
                connection.execute("INSERT INTO settings VALUES ('latest')")
                connection.commit()

                first = alfred.backup(home=home, machine="Test-Mac", keep=1)
                second = alfred.backup(home=home, machine="Test-Mac", keep=1)
            self.assertEqual([a["kind"] for a in second], ["preferences", "workflow_data"])
            self.assertEqual(len(list((home / ".backups/apps/customization/alfred/preferences").glob("*.zip"))), 1)
            self.assertEqual(len(list((home / ".backups/apps/customization/alfred/workflow-data").glob("*.zip"))), 1)

            with ZipFile(second[0]["path"]) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("Alfred.alfredpreferences/info.plist", archive.namelist())
            with ZipFile(second[1]["path"]) as archive:
                self.assertIsNone(archive.testzip())
                root = "Alfred Workflow Data Backup/"
                readme = archive.read(root + "README.txt").decode()
                self.assertIn("HOW TO RESTORE", readme)
                with tempfile.TemporaryDirectory(prefix="localbackup-db-test-") as extracted:
                    copied = Path(extracted) / "settings.db"
                    copied.write_bytes(
                        archive.read(root + "Workflow Data/com.example.workflow/settings.db")
                    )
                    with closing(sqlite3.connect(copied)) as restored:
                        self.assertEqual(
                            restored.execute("SELECT value FROM settings").fetchone()[0],
                            "latest",
                        )
            self.assertEqual(stat.S_IMODE(Path(second[1]["path"]).stat().st_mode), 0o600)
            self.assertNotEqual(first[0]["path"], second[0]["path"])

    def test_bartender_archive_contains_importable_preferences_and_database(self):
        with tempfile.TemporaryDirectory(prefix="localbackup-test-") as temporary:
            home = Path(temporary)
            app_info = home / "Bartender.app/Contents/Info.plist"
            app_info.parent.mkdir(parents=True)
            app_info.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "7.0.4"}))
            data_dir = (
                home / "Library/Group Containers" / bartender.GROUP_CONTAINER
                / "Library/Application Support"
            )
            data_dir.mkdir(parents=True)
            database = data_dir / "default.store"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE layout (name TEXT)")
                connection.execute("INSERT INTO layout VALUES ('Compact')")
                connection.commit()

            archives = bartender.backup(
                home=home,
                app_info=app_info,
                preferences_bytes=plistlib.dumps({"Layout": "Compact"}),
            )
            self.assertEqual(len(archives), 1)
            with ZipFile(archives[0]["path"]) as archive:
                self.assertIsNone(archive.testzip())
                root = "Bartender 7 Backup/"
                self.assertIn("HOW TO RESTORE", archive.read(root + "README.txt").decode())
                self.assertEqual(
                    plistlib.loads(archive.read(root + "Preferences/" + bartender.DOMAIN + ".plist"))["Layout"],
                    "Compact",
                )
                self.assertTrue(
                    any(name.endswith("/default.store") for name in archive.namelist())
                )

    def test_cli_lists_available_modules_as_json(self):
        output = StringIO()
        with redirect_stdout(output):
            status = main(["list", "--json"])
        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue().strip(), '{"apps": ["alfred", "bartender"]}')

    def test_app_commands_only_accept_their_own_options(self):
        for app, available, unavailable in (
            ("alfred", "--preferences", "--archive"),
            ("bartender", "--archive", "--preferences"),
        ):
            with self.subTest(app=app):
                output = StringIO()
                with redirect_stdout(output), self.assertRaises(SystemExit) as help_exit:
                    parser().parse_args(["restore", app, "--help"])
                self.assertEqual(help_exit.exception.code, 0)
                self.assertIn(available, output.getvalue())
                self.assertNotIn(unavailable, output.getvalue())
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as invalid:
                    parser().parse_args(["restore", app, unavailable, "/tmp/archive"])
                self.assertEqual(invalid.exception.code, 2)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as invalid:
            parser().parse_args(["now", "bartender", "--preferences-source", "/tmp/prefs"])
        self.assertEqual(invalid.exception.code, 2)

    def test_toml_schedule_validation_and_launch_agent_calendar(self):
        with tempfile.TemporaryDirectory(prefix="localbackup-config-") as temporary:
            path = Path(temporary) / "config.toml"
            path.write_text(config.example().replace('frequency = "weekly"', 'frequency = "daily"', 1))
            settings = config.load(path)
            self.assertEqual(settings["alfred"].schedule.calendar(), {"Hour": 3, "Minute": 0})
            self.assertEqual(
                settings["bartender"].schedule.calendar(),
                {"Hour": 3, "Minute": 15, "Weekday": 1},
            )
            plist = scheduler.agent("alfred", settings["alfred"], Path("/tmp/localbackup"), path, "/usr/bin/python3")
            self.assertEqual(plist["StartCalendarInterval"], {"Hour": 3, "Minute": 0})
            self.assertEqual(plist["ProgramArguments"][2:4], ["--config", str(path)])
            path.write_text(config.example() + "\n[unknown]\nkeep = 1\n")
            with self.assertRaises(BackupError):
                config.load(path)

    def test_single_root_moves_both_app_archives_and_rejects_escape(self):
        with tempfile.TemporaryDirectory(prefix="localbackup-root-") as temporary:
            path = Path(temporary) / "config.toml"
            root = Path(temporary) / "new-base"
            path.write_text(config.example().replace(
                'root_dir = "~/.backups"',
                f'root_dir = "{root}"',
            ))
            settings = config.load(path)
            self.assertEqual(settings["alfred"].output_dir, root / "apps/customization/alfred/preferences")
            self.assertEqual(settings["bartender"].output_dir, root / "apps/customization/bartender")
            path.write_text(path.read_text().replace(
                'subdir = "apps/customization/bartender"', 'subdir = "../elsewhere"',
            ))
            with self.assertRaisesRegex(BackupError, "stay inside"):
                config.load(path)

    def test_start_and_stop_only_the_owned_launch_agent(self):
        with tempfile.TemporaryDirectory(prefix="localbackup-agent-") as temporary:
            home = Path(temporary)
            launcher = home / "localbackup"
            launcher.write_text("#!/bin/sh\n")
            config_path = home / "config.toml"
            settings = config.AppConfig(
                output_dir=home / "archives", keep=12,
                schedule=config.Schedule("weekly", "03:15", "monday"),
            )
            with (
                patch("pathlib.Path.home", return_value=home),
                patch("lib.localbackup.scheduler._loaded", side_effect=[False, True, True]),
                patch("lib.localbackup.scheduler._launchctl") as launchctl,
            ):
                started = scheduler.start("bartender", settings, launcher, config_path)
                path = scheduler.plist_path("bartender", home)
                self.assertTrue(path.is_file())
                self.assertEqual(plistlib.loads(path.read_bytes())["StartCalendarInterval"]["Weekday"], 1)
                self.assertTrue(started["loaded"])
                stopped = scheduler.stop("bartender")
                self.assertFalse(stopped["loaded"])
                self.assertFalse(path.exists())
                self.assertEqual(launchctl.call_count, 2)

    def test_alfred_restore_previews_then_preserves_old_settings(self):
        with tempfile.TemporaryDirectory(prefix="localbackup-restore-") as temporary:
            home = Path(temporary)
            base = home / "Library/Application Support/Alfred"
            target = base / "Alfred.alfredpreferences"
            target.mkdir(parents=True)
            (target / "old.txt").write_text("old")
            archive_path = home / "prefs.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("Alfred.alfredpreferences/new.txt", "new")
                link = ZipInfo("Alfred.alfredpreferences/python")
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(link, "/opt/homebrew/bin/python3")
            settings = config.load()["alfred"]
            with patch("lib.localbackup.restore._app_running", return_value=False):
                preview = restore.restore_alfred(settings, preferences=archive_path, workflow_data=None, apply=False, home=home)
                self.assertFalse(preview["apply"])
                self.assertTrue((target / "old.txt").exists())
                applied = restore.restore_alfred(settings, preferences=archive_path, workflow_data=None, apply=True, home=home)
            self.assertEqual((target / "new.txt").read_text(), "new")
            self.assertTrue((target / "python").is_symlink())
            self.assertEqual(Path(applied["previous_copies"][0]).joinpath("old.txt").read_text(), "old")

    def test_alfred_zip_restore_preserves_executable_files(self):
        with tempfile.TemporaryDirectory(prefix="localbackup-zip-") as temporary:
            home = Path(temporary)
            base = home / "Library/Application Support/Alfred"
            preferences = base / "Alfred.alfredpreferences"
            preferences.mkdir(parents=True)
            (base / "Workflow Data").mkdir()
            script = preferences / "run.sh"
            script.write_text("#!/bin/sh\necho original\n")
            script.chmod(0o755)
            archives = alfred.backup(home=home, machine="Test-Mac")
            archive = Path(archives[0]["path"])
            self.assertEqual(archive.suffix, ".zip")
            script.write_text("changed")
            script.chmod(0o644)
            settings = config.AppConfig(
                output_dir=home / "archives", keep=12,
                schedule=config.Schedule("off", "03:00", "monday"),
            )
            with patch("lib.localbackup.restore._app_running", return_value=False):
                result = restore.restore_alfred(
                    settings, preferences=archive, workflow_data=None, apply=True, home=home,
                )
            self.assertIn("echo original", script.read_text())
            self.assertEqual(stat.S_IMODE(script.stat().st_mode), 0o755)
            self.assertEqual(
                (Path(result["previous_copies"][0]) / "run.sh").read_text(), "changed",
            )

    def test_restore_rejects_archive_traversal(self):
        with tempfile.TemporaryDirectory(prefix="localbackup-restore-") as temporary:
            home = Path(temporary)
            archive_path = home / "bad.zip"
            with ZipFile(archive_path, "w") as zip_file:
                zip_file.writestr("Alfred.alfredpreferences/../../outside", "x")
            with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
                archive.validate_zip(archive_path, alfred.PREFERENCES_ROOT)
            with self.assertRaises(BackupError):
                restore.restore_alfred(
                    config.load()["alfred"], preferences=archive_path,
                    workflow_data=None, apply=False, home=home,
                )
            self.assertFalse((home / "outside").exists())

    def test_old_tgz_archives_are_not_listed_or_restored(self):
        with tempfile.TemporaryDirectory(prefix="localbackup-archive-") as temporary:
            home = Path(temporary)
            archive_dir = home / "preferences"
            archive_dir.mkdir()
            old = archive_dir / "Alfred Backup old.tgz"
            old.write_bytes(b"old")
            settings = config.AppConfig(
                output_dir=archive_dir, keep=12,
                schedule=config.Schedule("off", "03:00", "monday"),
            )
            self.assertEqual(restore.archives("alfred", settings), [])
            with self.assertRaisesRegex(BackupError, "regular .zip"):
                restore.restore_alfred(
                    settings, preferences=old, workflow_data=None, apply=False, home=home,
                )

    def test_bartender_restore_applies_database_and_keeps_previous_copy(self):
        with tempfile.TemporaryDirectory(prefix="localbackup-restore-") as temporary:
            home = Path(temporary)
            directory = (
                home / "Library/Group Containers" / bartender.GROUP_CONTAINER
                / "Library/Application Support"
            )
            directory.mkdir(parents=True)
            target = directory / "default.store"
            with closing(sqlite3.connect(target)) as database:
                database.execute("CREATE TABLE layout (value TEXT)")
                database.execute("INSERT INTO layout VALUES ('old')")
                database.commit()
            new_database = home / "new.store"
            with closing(sqlite3.connect(new_database)) as database:
                database.execute("CREATE TABLE layout (value TEXT)")
                database.execute("INSERT INTO layout VALUES ('new')")
                database.commit()
            archive_path = home / "Bartender 7 Settings test.zip"
            root = "Bartender 7 Backup/"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr(root + "Preferences/" + bartender.DOMAIN + ".plist", plistlib.dumps({"Layout": "new"}))
                archive.write(
                    new_database,
                    root + "Group Containers/" + bartender.GROUP_CONTAINER
                    + "/Library/Application Support/default.store",
                )
            settings = config.AppConfig(
                output_dir=home / "backups", keep=12,
                schedule=config.Schedule("off", "03:00", "monday"),
            )
            old_preferences = plistlib.dumps({"Layout": "old"})
            def fake_defaults(argv, **kwargs):
                if argv[1] == "export":
                    return subprocess.CompletedProcess(argv, 0, stdout=old_preferences)
                return subprocess.CompletedProcess(argv, 0)
            with (
                patch("lib.localbackup.restore._app_running", return_value=False),
                patch("lib.localbackup.restore.subprocess.run", side_effect=fake_defaults) as defaults,
            ):
                result = restore.restore_bartender(settings, archive=archive_path, apply=True, home=home)
            with closing(sqlite3.connect(target)) as database:
                self.assertEqual(database.execute("SELECT value FROM layout").fetchone()[0], "new")
            with closing(sqlite3.connect(Path(result["previous_copy"]) / "default.store")) as database:
                self.assertEqual(database.execute("SELECT value FROM layout").fetchone()[0], "old")
            self.assertEqual(defaults.call_count, 2)


if __name__ == "__main__":
    unittest.main()

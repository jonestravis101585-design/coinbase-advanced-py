import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values

from examples.coinbase_agent import setup
from scripts import start_coinbase_agent as bootstrap
from tests.constants import TEST_API_KEY, TEST_API_SECRET


class LocalSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = self.directory / "repository"
        self.root.mkdir()
        self.key_file = self.directory / "coinbase key.json"
        self.key_file.write_text(
            json.dumps({"name": TEST_API_KEY, "privateKey": TEST_API_SECRET}),
            encoding="utf-8",
        )

    def test_validates_key_format_locally_without_changing_the_file(self):
        original = self.key_file.read_bytes()
        with patch(
            "requests.sessions.Session.request",
            side_effect=AssertionError("No network during setup"),
        ):
            self.assertEqual(
                setup.validate_key_file(f'"{self.key_file}"', root=self.root),
                self.key_file,
            )
        self.assertEqual(self.key_file.read_bytes(), original)

    def test_rejects_keys_inside_repository_and_malformed_key_files(self):
        with self.assertRaisesRegex(setup.SetupError, "outside the repository"):
            setup.validate_key_file(str(self.root / "key.json"), root=self.root)
        for text in ('{"privateKey":"secret-test-value"}', "[]", "not JSON"):
            self.key_file.write_text(text, encoding="utf-8")
            with self.subTest(text=text):
                with self.assertRaises(setup.SetupError) as caught:
                    setup.validate_key_file(str(self.key_file), root=self.root)
                self.assertNotIn("secret-test-value", str(caught.exception))

    def test_settings_preserve_windows_paths_unicode_and_literal_dollar_values(self):
        path = self.root / ".env"
        key_file = Path("C:/Users/André/keys ${LITERAL}/coinbase.json")
        setup.write_settings(path, key_file, "sk-test-${LITERAL}", "gpt-5-mini")
        values = dotenv_values(path, interpolate=False)
        self.assertEqual(values["COINBASE_KEY_FILE"], str(key_file))
        self.assertEqual(values["OPENAI_API_KEY"], "sk-test-${LITERAL}")
        self.assertEqual(values["COINBASE_API_SECRET"], "")
        self.assertNotIn(TEST_API_SECRET, path.read_text(encoding="utf-8"))
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_failed_atomic_replace_preserves_existing_settings_and_cleans_temporary_file(
        self,
    ):
        path = self.root / ".env"
        path.write_text("original settings", encoding="utf-8")
        with patch("examples.coinbase_agent.setup.os.replace", side_effect=OSError):
            with self.assertRaises(OSError):
                setup.write_settings(path, self.key_file, "sk-test-key", "gpt-5-mini")
        self.assertEqual(path.read_text(encoding="utf-8"), "original settings")
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_multiline_secret_cannot_inject_more_environment_settings(self):
        path = self.root / ".env"
        with self.assertRaises(setup.SetupError):
            setup.write_settings(
                path, self.key_file, "sk-test\nCOINBASE_KEY_FILE=changed", "gpt-5-mini"
            )
        self.assertFalse(path.exists())

    def test_wizard_keeps_existing_configuration_unless_replacement_is_explicit(self):
        path = self.root / ".env"
        path.write_text("original settings", encoding="utf-8")
        with patch("builtins.input", return_value=""), patch.object(
            setup, "choose_key_file"
        ) as chooser, redirect_stdout(io.StringIO()):
            self.assertFalse(setup.run_setup(path))
        chooser.assert_not_called()
        self.assertEqual(path.read_text(encoding="utf-8"), "original settings")

    def test_wizard_saves_without_echoing_keys_or_claiming_connection(self):
        path = self.root / ".env"
        output = io.StringIO()
        with patch.object(
            setup, "choose_key_file", return_value=str(self.key_file)
        ), patch("getpass.getpass", return_value="sk-test-hidden"), patch(
            "builtins.input", return_value=""
        ), patch(
            "requests.sessions.Session.request",
            side_effect=AssertionError("No network during setup"),
        ), redirect_stdout(
            output
        ):
            self.assertTrue(setup.run_setup(path))
        self.assertNotIn("sk-test-hidden", output.getvalue())
        self.assertNotIn(TEST_API_SECRET, output.getvalue())
        self.assertIn("no connection has been verified", output.getvalue())
        self.assertEqual(dotenv_values(path)["OPENAI_API_KEY"], "sk-test-hidden")

    def test_cancelled_file_picker_saves_nothing(self):
        path = self.root / ".env"
        with patch.object(setup, "choose_key_file", return_value=""), redirect_stdout(
            io.StringIO()
        ):
            self.assertFalse(setup.run_setup(path))
        self.assertFalse(path.exists())

    def test_menu_launches_only_the_selected_mode_without_shell_interpolation(self):
        with patch(
            "builtins.input", side_effect=["not a number", "3", "4", "0"]
        ), patch.object(setup.subprocess, "run") as run, redirect_stdout(io.StringIO()):
            setup.run_menu()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args_list[0].args[0],
            [sys.executable, "-m", "examples.coinbase_agent", "--read-only"],
        )
        self.assertEqual(
            run.call_args_list[1].args[0],
            [sys.executable, "-m", "examples.coinbase_agent"],
        )
        self.assertNotIn("shell", run.call_args.kwargs)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="agent test folder ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        requirements = self.root / "examples/coinbase_agent/requirements.txt"
        requirements.parent.mkdir(parents=True)
        requirements.write_text("-e .\n", encoding="utf-8")
        (self.root / "requirements.txt").write_text("requests\n", encoding="utf-8")
        self.python = (
            self.root
            / ".venv"
            / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        )
        self.marker = self.root / ".venv/.coinbase-agent-requirements.sha256"

    def prepare_environment(self):
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        self.marker.write_text(
            bootstrap.requirements_digest(self.root), encoding="utf-8"
        )

    def test_first_launch_creates_environment_installs_then_opens_menu(self):
        def simulated_run(command, **kwargs):
            if "venv" in command:
                self.python.parent.mkdir(parents=True)
                self.python.touch()
            return subprocess.CompletedProcess(command, 0)

        with patch.object(
            bootstrap.subprocess, "run", side_effect=simulated_run
        ) as run, redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap.launch([], root=self.root), 0)
        self.assertEqual(run.call_count, 3)
        self.assertIn("venv", run.call_args_list[0].args[0])
        self.assertIn("pip", run.call_args_list[1].args[0])
        self.assertEqual(run.call_args_list[2].args[0][-1], "--menu")
        self.assertEqual(
            self.marker.read_text(encoding="utf-8"),
            bootstrap.requirements_digest(self.root),
        )

    def test_next_launch_skips_install_and_preserves_arguments(self):
        self.prepare_environment()
        with patch.object(
            bootstrap.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
        ) as run:
            self.assertEqual(
                bootstrap.launch(["--read-only", "--list-tools"], root=self.root), 0
            )
        run.assert_called_once_with(
            [
                str(self.python),
                "-m",
                "examples.coinbase_agent",
                "--read-only",
                "--list-tools",
            ],
            cwd=self.root,
        )

    def test_failed_install_does_not_mark_environment_as_installed(self):
        self.prepare_environment()
        self.marker.unlink()
        with patch.object(
            bootstrap.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, "pip"),
        ), redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                bootstrap.launch([], root=self.root)
        self.assertFalse(self.marker.exists())

    def test_changed_sdk_requirements_trigger_install(self):
        self.prepare_environment()
        (self.root / "requirements.txt").write_text("requests>=2\n", encoding="utf-8")
        with patch.object(
            bootstrap.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
        ) as run, redirect_stdout(io.StringIO()):
            bootstrap.launch(["--list-tools"], root=self.root)
        self.assertEqual(run.call_count, 2)
        self.assertIn("pip", run.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()

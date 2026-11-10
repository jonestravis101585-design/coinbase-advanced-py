"""Local setup wizard. Credentials are never sent to a network service here."""

import getpass
import json
import os
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

from coinbase import jwt_generator

ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = Path(__file__).with_name(".env")


class SetupError(ValueError):
    """An actionable setup error that contains no credential values."""


def validate_key_file(raw_path, root=ROOT):
    path = (
        Path(os.path.expandvars(raw_path.strip().strip("\"'"))).expanduser().resolve()
    )
    if path.is_relative_to(root.resolve()):
        raise SetupError(
            "Move the downloaded Coinbase key JSON outside the repository, then select it again."
        )
    try:
        key = json.loads(path.read_text(encoding="utf-8-sig"))
        name = key.get("name") or key.get("id")
        secret = key.get("privateKey")
        if not isinstance(name, str) or not name.strip() or not isinstance(secret, str):
            raise ValueError("missing key fields")
        # Sign locally to check the private key's format. Never print or save the JWT.
        jwt_generator.build_rest_jwt(
            "GET api.coinbase.com/api/v3/brokerage/accounts", name, secret
        )
    except Exception:
        raise SetupError(
            "That file is not a readable Coinbase API key JSON with a valid private key. Download the key JSON from Coinbase and try again."
        ) from None
    return path


def choose_key_file():
    print(
        "Select the Coinbase API key JSON you downloaded. Keep it outside this repository."
    )
    try:
        import tkinter
        from tkinter import filedialog

        window = tkinter.Tk()
        try:
            window.withdraw()
            return filedialog.askopenfilename(
                parent=window,
                title="Select your Coinbase API key JSON",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
        finally:
            window.destroy()
    except (ImportError, RuntimeError):
        pass
    except Exception:
        # A desktop or Tcl/Tk may be unavailable; a console path is sufficient.
        pass
    return input("Full path to the Coinbase key JSON (blank cancels): ").strip()


def write_settings(path, key_file, openai_key, model):
    values = {
        "OPENAI_API_KEY": openai_key,
        "OPENAI_MODEL": model,
        "COINBASE_KEY_FILE": str(key_file),
        "COINBASE_API_KEY": "",
        "COINBASE_API_SECRET": "",
    }
    if any(
        not isinstance(value, str) or any(ord(char) < 32 for char in value)
        for value in values.values()
    ):
        raise SetupError("Settings must be single-line text. No settings were saved.")
    if not openai_key.strip() or not model.strip():
        raise SetupError(
            "An OpenAI API key and model name are required. No settings were saved."
        )
    contents = (
        "# Private local settings. Do not share or commit this file.\n"
        + "".join(
            f"{name}={json.dumps(value, ensure_ascii=False)}\n"
            for name, value in values.items()
        )
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".env.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as output:
            temporary = Path(output.name)
            os.chmod(temporary, 0o600)
            output.write(contents)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_setup(settings_path=SETTINGS_PATH):
    print("\nCoinbase Account Agent: local setup")
    print("Your keys stay on this computer. This wizard makes no API calls.")
    try:
        if settings_path.exists():
            if (
                input(
                    "Local settings already exist. Replace them? Type REPLACE to continue: "
                ).strip()
                != "REPLACE"
            ):
                print("Existing settings kept.")
                return False
        selected = choose_key_file()
        if not selected:
            print("Setup cancelled. No settings changed.")
            return False
        key_file = validate_key_file(selected)
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            openai_key = getpass.getpass(
                "Paste your OpenAI API key (input is hidden): "
            ).strip()
        model = input("OpenAI model [gpt-5-mini]: ").strip() or "gpt-5-mini"
        write_settings(settings_path, key_file, openai_key, model)
        print("Local settings saved. Choose 'Check Coinbase connection' next.")
        print("No trades were submitted and no connection has been verified yet.")
        return True
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled. No settings changed.")
    except getpass.GetPassWarning:
        print(
            "Hidden key entry is unavailable in this terminal. Run the Windows launcher in a normal console."
        )
    except SetupError as error:
        print(str(error))
    except OSError:
        print(
            "The settings file could not be saved. Check folder permissions. No API calls were made."
        )
    return False


def run_menu():
    actions = {
        "2": ["--check-connection"],
        "3": ["--read-only"],
        "4": [],
        "5": ["--list-tools"],
    }
    while True:
        print("\nCoinbase Account Agent")
        print("1. Set up API keys on this computer")
        print("2. Check Coinbase connection")
        print("3. Start read-only chat")
        print("4. Start full agent (account changes require approval)")
        print("5. List available tools")
        print("0. Exit")
        try:
            selection = input("Choose an option: ").strip()
            if selection == "0":
                return
            if selection == "1":
                run_setup()
            elif selection in actions:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "examples.coinbase_agent",
                        *actions[selection],
                    ],
                    cwd=ROOT,
                )
            else:
                print("Choose one of the numbers shown above.")
        except (EOFError, KeyboardInterrupt):
            print(
                "\nClosed. Previously submitted orders can remain active on Coinbase."
            )
            return

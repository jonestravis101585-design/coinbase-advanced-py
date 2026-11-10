"""Create a project-local Python environment and open the account agent menu."""

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def requirements_digest(root):
    digest = hashlib.sha256()
    for relative in ("requirements.txt", "examples/coinbase_agent/requirements.txt"):
        digest.update(relative.encode("utf-8"))
        digest.update((root / relative).read_bytes())
    return digest.hexdigest()


def launch(arguments, root=ROOT):
    if sys.version_info < (3, 10):
        print(
            "Python 3.10 or newer is required. Install Python 3.12 or newer and try again."
        )
        return 1

    environment = root / ".venv"
    python = environment / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    if not python.is_file():
        print("Creating the agent's local Python environment...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "venv", str(environment)], cwd=root, check=True
        )

    marker = environment / ".coinbase-agent-requirements.sha256"
    digest = requirements_digest(root)
    if not marker.is_file() or marker.read_text(encoding="utf-8") != digest:
        print(
            "Installing the agent's dependencies. This needs internet access and may take a few minutes.",
            flush=True,
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "-r",
                "examples/coinbase_agent/requirements.txt",
            ],
            cwd=root,
            check=True,
        )
        marker.write_text(digest, encoding="utf-8")

    return subprocess.run(
        [str(python), "-m", "examples.coinbase_agent", *(arguments or ["--menu"])],
        cwd=root,
    ).returncode


def main():
    try:
        return launch(sys.argv[1:])
    except (OSError, subprocess.CalledProcessError):
        print(
            "The launcher could not finish. Review the installation error above, check Python and your internet connection, and run it again."
        )
        return 1
    except KeyboardInterrupt:
        print(
            "\nStopped. Verify account/order state before resubmitting an interrupted action."
        )
        return 130


if __name__ == "__main__":
    sys.exit(main())

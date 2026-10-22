"""Local Home Assistant development instance."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIRECTORY = ROOT.parent / "home-assistant-dev"
DEFAULT_CREDENTIALS = ROOT / ".local/ha-dev-credentials.json"
IMAGE = "ghcr.io/home-assistant/home-assistant:2026.10.2"


class DevelopmentError(Exception):
    """Development setup failure."""


def read_credentials(path: Path) -> dict[str, str]:
    """Load the private admin credentials."""
    try:
        data = json.loads(path.read_text())
        credentials = {key: data[key] for key in ("name", "username", "password")}
        if not all(
            isinstance(value, str) and value.strip() for value in credentials.values()
        ):
            raise ValueError  # noqa: TRY301 -- Reuse the sanitized error below.
        path.chmod(0o600)
    except OSError, ValueError, KeyError, TypeError:
        raise DevelopmentError(
            f"Fill name, username, and password in the private credential file: {path}"
        ) from None
    return credentials


def compose_definition(directory: Path, port: int) -> dict:
    """Isolate alternate workspaces with separate Compose projects."""
    project = "ecowitt-atomic-dev"
    if directory != DEFAULT_DIRECTORY.resolve():
        project += "-" + hashlib.sha256(str(directory).encode()).hexdigest()[:8]
    return {
        "name": project,
        "services": {
            "homeassistant": {
                "image": IMAGE,
                "ports": [f"127.0.0.1:{port}:8123"],
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(directory / "config"),
                        "target": "/config",
                    },
                    {
                        "type": "bind",
                        "source": str(ROOT / "custom_components/ecowitt_atomic"),
                        "target": "/config/custom_components/ecowitt_atomic",
                        "read_only": True,
                    },
                ],
            }
        },
    }


def prepare(directory: Path, port: int, *, reset: bool = False) -> None:
    """Refuse to overwrite an unrelated Compose workspace."""
    path = directory / "compose.json"
    expected = compose_definition(directory, port)
    if reset and not path.is_file():
        raise DevelopmentError(
            "No project development instance exists at that directory"
        )
    if path.exists() and json.loads(path.read_text()) != expected:
        raise DevelopmentError(
            f"Existing {path} differs from this project's development setup"
        )
    if (directory / "config").is_symlink():
        raise DevelopmentError("Development configuration must be a real directory")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config").mkdir(exist_ok=True)
    path.write_text(json.dumps(expected, indent=2) + "\n")


def compose(
    directory: Path, *arguments: str, **kwargs: Any
) -> subprocess.CompletedProcess:
    """Run a command against the development Compose project."""
    return subprocess.run(  # noqa: S603 -- Local Docker arguments; no shell.
        ["docker", "compose", "-f", str(directory / "compose.json"), *arguments],  # noqa: S607 -- Docker must be on PATH.
        check=True,
        **kwargs,
    )


def write_configuration(directory: Path) -> None:
    """Write the initial HA configuration if absent."""
    path = directory / "config/configuration.yaml"
    if not path.exists():
        path.write_text(
            "homeassistant:\n  name: Ecowitt Atomic development\n  time_zone: UTC\n"
            "config:\nfrontend:\nhttp:\napi:\nhistory:\nrecorder:\nsystem_log:\n"
        )


def reset_configuration(directory: Path) -> None:
    """Use a container to delete root-owned HA files."""
    cleanup = (
        "import pathlib,shutil; "
        "[(shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()) "
        "for p in pathlib.Path('/config').iterdir()]"
    )
    subprocess.run(  # noqa: S603 -- Local Docker arguments; no shell.
        [  # noqa: S607 -- Docker must be on PATH.
            "docker",
            "run",
            "--rm",
            "--mount",
            f"type=bind,source={directory / 'config'},target=/config",
            "--entrypoint",
            "python",
            IMAGE,
            "-c",
            cleanup,
        ],
        check=True,
    )


def bootstrap_admin(directory: Path, credentials: dict[str, str]) -> None:
    """Send credentials over stdin, not process arguments."""
    result = compose(
        directory,
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--entrypoint",
        "python",
        "--volume",
        f"{ROOT / 'scripts'}:/development-scripts:ro",
        "homeassistant",
        "/development-scripts/ha_bootstrap.py",
        input=json.dumps(credentials),
        capture_output=True,
        text=True,
    )
    try:
        status = json.loads(result.stdout.strip().splitlines()[-1])
    except ValueError, IndexError:
        raise DevelopmentError(
            "HA administrator initialization did not return a result"
        ) from None
    if not status.get("onboarded"):
        raise DevelopmentError(
            "HA administrator initialization did not finish onboarding"
        )
    print(
        "Development HA administrator created."
        if status["created_admin"]
        else "Existing HA administrator retained."
    )


def wait_ready(port: int, timeout: float = 90) -> None:
    """Wait until HA has completed onboarding."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/onboarding", timeout=3
            ) as response:
                steps = json.load(response)
                if (
                    isinstance(steps, list)
                    and steps
                    and all(step.get("done") for step in steps)
                ):
                    return
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return
        except OSError, ValueError:
            pass
        time.sleep(1)
    raise DevelopmentError("Development HA did not become ready before the timeout")


def main() -> None:
    """Run the development command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "reset", "stop", "logs", "restart"])
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--port", type=int, default=18123)
    args = parser.parse_args()
    directory = args.directory.resolve()
    try:
        if args.action in {"start", "reset"}:
            credentials = read_credentials(args.credentials)
            prepare(directory, args.port, reset=args.action == "reset")
            compose(directory, "stop", "homeassistant")
            if args.action == "reset":
                reset_configuration(directory)
            write_configuration(directory)
            bootstrap_admin(directory, credentials)
            compose(directory, "up", "-d")
            wait_ready(args.port)
            print(f"Home Assistant ready: http://127.0.0.1:{args.port}")
        else:
            command = {
                "stop": ["down"],
                "logs": ["logs", "--tail", "100"],
                "restart": ["restart", "homeassistant"],
            }[args.action]
            compose(directory, *command)
    except (DevelopmentError, OSError, subprocess.CalledProcessError) as error:
        if isinstance(error, DevelopmentError):
            print(str(error), file=sys.stderr)
        else:
            print(
                "Development HA command failed; check Docker and the development logs.",
                file=sys.stderr,
            )
        raise SystemExit(1) from None


if __name__ == "__main__":
    os.umask(0o077)
    main()

"""Check the packaging files we can validate before publishing a repository."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components/ecowitt_atomic"


def main() -> None:
    """Keep release metadata and translations consistent."""
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    hacs = json.loads((ROOT / "hacs.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert manifest["domain"] == COMPONENT.name
    assert manifest["version"] == project["project"]["version"]
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "local_polling"
    assert hacs["filename"] == f"{COMPONENT.name}.zip"
    assert hacs["homeassistant"] == "2026.10.2"
    assert json.loads((COMPONENT / "strings.json").read_text()) == json.loads(
        (COMPONENT / "translations/en.json").read_text()
    )
    print("Packaging metadata and translations are consistent.")


if __name__ == "__main__":
    main()

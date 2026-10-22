"""Package the integration for HACS."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    """Write the integration zip."""
    source = ROOT / "custom_components/ecowitt_atomic"
    output = ROOT / "dist/ecowitt_atomic.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            ):
                archive.write(path, path.relative_to(source))
        archive.write(ROOT / "LICENSE", "LICENSE")
    print(output)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_FILE = ROOT / "WIND_FARM_INFO.md"
README_FILE = ROOT / "README.md"
START_MARKER = "<!-- wind-farm-info:start -->"
END_MARKER = "<!-- wind-farm-info:end -->"


def sync_readme() -> None:
    content = SOURCE_FILE.read_text(encoding="utf-8").rstrip() + "\n"
    readme = README_FILE.read_text(encoding="utf-8")

    start = readme.find(START_MARKER)
    end = readme.find(END_MARKER)
    if start == -1 or end == -1:
        raise SystemExit(
            f"Markers {START_MARKER} and {END_MARKER} not found in {README_FILE}."
        )
    if end < start:
        raise SystemExit("End marker appears before start marker in README.md.")

    start += len(START_MARKER)
    new_readme = (
        readme[:start]
        + "\n\n"
        + content
        + "\n"
        + readme[end:]
    )
    README_FILE.write_text(new_readme, encoding="utf-8")
    print(f"Injected {SOURCE_FILE.name} into {README_FILE.name}.")


def check_readme() -> bool:
    content = SOURCE_FILE.read_text(encoding="utf-8").rstrip() + "\n"
    readme = README_FILE.read_text(encoding="utf-8")
    embedded = f"{START_MARKER}\n\n{content}\n{END_MARKER}"
    if embedded in readme:
        print(f"{README_FILE.name} matches {SOURCE_FILE.name}.")
        return True
    print(f"WARNING: {README_FILE.name} is out of sync with {SOURCE_FILE.name}.")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Keep the README wind-farm-info section in sync with WIND_FARM_INFO.md."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("sync", help="Inject WIND_FARM_INFO.md into README.md markers.")
    subparsers.add_parser("check", help="Verify the README section matches WIND_FARM_INFO.md.")
    args = parser.parse_args()

    if args.command == "sync":
        sync_readme()
        return
    if args.command == "check":
        if not check_readme():
            raise SystemExit(1)
        return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

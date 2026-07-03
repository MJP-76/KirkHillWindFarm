from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
MANIFEST_FILE = ROOT / "custom_components" / "kirkhill_wind" / "manifest.json"
PYPROJECT_FILE = ROOT / "pyproject.toml"


def normalize_version(raw: str) -> str:
    value = raw.strip()
    if value.startswith("v"):
        value = value[1:]
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError(
            f"Invalid version '{raw.strip()}'. Expected semantic version like 4.3.0."
        )
    return value


def read_version() -> str:
    return normalize_version(VERSION_FILE.read_text(encoding="utf-8"))


def read_manifest_version() -> str:
    return normalize_version(
        json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))["version"]
    )


def read_pyproject_version() -> str:
    text = PYPROJECT_FILE.read_text(encoding="utf-8")
    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project and stripped.startswith("version"):
            match = re.fullmatch(r'version\s*=\s*"([^"]+)"', stripped)
            if not match:
                raise ValueError("Invalid [project].version format in pyproject.toml.")
            return normalize_version(match.group(1))
    raise ValueError("Could not find [project].version in pyproject.toml.")


def write_manifest_version(version: str) -> None:
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    manifest["version"] = version
    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )


def write_pyproject_version(version: str) -> None:
    lines = PYPROJECT_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    in_project = False
    replaced = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project and stripped.startswith("version"):
            lines[i] = f'version = "{version}"\n'
            replaced = True
            break

    if not replaced:
        raise ValueError("Could not update [project].version in pyproject.toml.")

    PYPROJECT_FILE.write_text("".join(lines), encoding="utf-8")


def check_versions() -> bool:
    source = read_version()
    manifest = read_manifest_version()
    pyproject = read_pyproject_version()

    mismatches: list[str] = []
    if manifest != source:
        mismatches.append(f"manifest.json={manifest} != VERSION={source}")
    if pyproject != source:
        mismatches.append(f"pyproject.toml={pyproject} != VERSION={source}")

    if mismatches:
        print("Version mismatch detected:")
        for mismatch in mismatches:
            print(f"- {mismatch}")
        return False

    print(f"All versions are aligned at {source}.")
    return True


def sync_versions() -> None:
    version = read_version()
    write_manifest_version(version)
    write_pyproject_version(version)
    print(f"Synchronized manifest.json and pyproject.toml to {version}.")


def run_release() -> None:
    version = read_version()
    tag = f"v{version}"

    if not check_versions():
        raise SystemExit("Run `python scripts/version_sync.py sync` before releasing.")

    existing_tag = subprocess.run(
        ["git", "tag", "--list", tag],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if existing_tag:
        raise SystemExit(f"Tag {tag} already exists.")

    subprocess.run(["git", "tag", tag], cwd=ROOT, check=True)
    subprocess.run(
        ["gh", "release", "create", tag, "--title", tag, "--generate-notes"],
        cwd=ROOT,
        check=True,
    )
    print(f"Created tag and release {tag}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Keep release versions synchronized from VERSION."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="Validate all tracked versions match VERSION.")
    subparsers.add_parser("sync", help="Sync manifest.json and pyproject.toml from VERSION.")
    subparsers.add_parser(
        "release",
        help="Create a v-prefixed tag and GitHub release from VERSION.",
    )
    args = parser.parse_args()

    if args.command == "check":
        if not check_versions():
            raise SystemExit(1)
        return
    if args.command == "sync":
        sync_versions()
        return
    if args.command == "release":
        run_release()
        return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

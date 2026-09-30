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
SCADA_CARD_FILE = ROOT / "custom_components" / "kirkhill_wind" / "frontend" / "kirkhill-wind-scada-card.js"
HACS_FILE = ROOT / "hacs.json"
REQUIREMENTS_FILE = ROOT / "requirements.txt"

# Oldest Home Assistant release we advertise support for. Single source of
# truth: `check` fails if hacs.json or requirements.txt disagree, and CI
# installs this exact version and runs the suite against it, so this is a
# tested claim rather than a guess.
#
# This is a policy choice, not a technical limit. The lowest release the code
# actually imports against is TECHNICAL_FLOOR_HA_VERSION below; we advertise a
# newer one on purpose. A floor costs maintenance: every HA API newer than it
# needs either a floor bump or a compatibility shim. At the technical floor
# that was already visible -- helpers/frame gained async_setup in 2025.6, which
# forced a hasattr() guard in tests/conftest.py. A recent floor keeps
# essentially the whole active install base in scope and buys roughly a year of
# runway before this becomes the thing to complain about.
#
# To change it: update MIN_HA_VERSION and MIN_HA_PYTHON together, re-run
# `sync`, and let the min-ha CI job confirm the new floor really passes.
MIN_HA_VERSION = "2026.1.0"

# Lowest Home Assistant release this code can actually import, set by
# homeassistant.components.lovelace.const.LOVELACE_DATA (2025.2.0). Never
# advertise support below this. Lower it only if a refactor drops the Lovelace
# dependency entirely.
TECHNICAL_FLOOR_HA_VERSION = "2025.2.0"

# Python required by MIN_HA_VERSION. Each HA release declares its own
# requires-python, so pinning a too-old Python here makes pip silently
# backtrack to a different, older Home Assistant and the check becomes a lie.
MIN_HA_PYTHON = "3.13"


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


def read_scada_version() -> str:
    text = SCADA_CARD_FILE.read_text(encoding="utf-8")
    match = re.search(
        r'KIRKHILL_WIND_SCADA_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE
    )
    if not match:
        raise ValueError("Could not find KIRKHILL_WIND_SCADA_VERSION in the SCADA card JS.")
    if match.group(1) == "@VERSION@":
        return ""
    return normalize_version(match.group(1))


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


def write_scada_version(version: str) -> None:
    text = SCADA_CARD_FILE.read_text(encoding="utf-8")
    replaced, count = re.subn(
        r'(KIRKHILL_WIND_SCADA_VERSION\s*=\s*)"[^"]*"',
        rf'\g<1>"{version}"',
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(
            "Could not update KIRKHILL_WIND_SCADA_VERSION in the SCADA card JS."
        )
    SCADA_CARD_FILE.write_text(replaced, encoding="utf-8")


def read_hacs_min_ha() -> str:
    return str(json.loads(HACS_FILE.read_text(encoding="utf-8")).get("homeassistant", ""))


def read_requirements_min_ha() -> str:
    """Return the homeassistant version floor declared in requirements.txt."""
    for line in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("homeassistant"):
            match = re.search(r"homeassistant\s*>=\s*([\d.]+)", line)
            if match:
                return match.group(1)
    return ""


def write_hacs_min_ha(version: str) -> None:
    data = json.loads(HACS_FILE.read_text(encoding="utf-8"))
    data["homeassistant"] = version
    HACS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_requirements_min_ha(version: str) -> None:
    lines = REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith("homeassistant"):
            lines[i] = f"homeassistant>={version}\n"
            replaced = True
            break
    if not replaced:
        raise ValueError("Could not find a homeassistant requirement line.")
    REQUIREMENTS_FILE.write_text("".join(lines), encoding="utf-8")


def check_versions() -> bool:
    source = read_version()
    manifest = read_manifest_version()
    pyproject = read_pyproject_version()
    scada = read_scada_version()
    hacs_min = read_hacs_min_ha()
    requirements_min = read_requirements_min_ha()

    mismatches: list[str] = []
    if manifest != source:
        mismatches.append(f"manifest.json={manifest} != VERSION={source}")
    if pyproject != source:
        mismatches.append(f"pyproject.toml={pyproject} != VERSION={source}")
    if scada != source:
        label = scada or "@VERSION@ placeholder"
        mismatches.append(f"scada-card.js={label} != VERSION={source}")
    if hacs_min != MIN_HA_VERSION:
        mismatches.append(
            f"hacs.json homeassistant={hacs_min or '(unset)'} != MIN_HA_VERSION={MIN_HA_VERSION}"
        )
    if requirements_min != MIN_HA_VERSION:
        mismatches.append(
            f"requirements.txt homeassistant>={requirements_min or '(unset)'} "
            f"!= MIN_HA_VERSION={MIN_HA_VERSION}"
        )

    if mismatches:
        print("Version mismatch detected:")
        for mismatch in mismatches:
            print(f"- {mismatch}")
        return False

    print(f"All versions are aligned at {source} (min HA {MIN_HA_VERSION}).")
    return True


def sync_versions() -> None:
    version = read_version()
    write_manifest_version(version)
    write_pyproject_version(version)
    write_scada_version(version)
    write_hacs_min_ha(MIN_HA_VERSION)
    write_requirements_min_ha(MIN_HA_VERSION)
    print(
        f"Synchronized manifest.json, pyproject.toml and scada-card.js to {version}, "
        f"and minimum Home Assistant to {MIN_HA_VERSION}."
    )


def run_release(prerelease: bool, stable: bool) -> None:
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

    cmd = ["gh", "release", "create", tag, "--title", tag, "--generate-notes"]
    # Per project policy, releases are pre-releases by default; only --stable
    # produces a normal release.
    if prerelease and not stable:
        cmd.append("--prerelease")
    elif stable and not prerelease:
        pass
    else:
        # neither flag: default to prerelease
        cmd.append("--prerelease")
    subprocess.run(cmd, cwd=ROOT, check=True)
    print(f"Created tag and release {tag}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Keep release versions synchronized from VERSION."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="Validate all tracked versions match VERSION.")
    subparsers.add_parser("sync", help="Sync manifest.json and pyproject.toml from VERSION.")
    min_ha_parser = subparsers.add_parser(
        "min-ha",
        help="Print the minimum supported Home Assistant version / Python, for CI.",
    )
    min_ha_parser.add_argument(
        "--version",
        action="store_true",
        help="Print only the minimum Home Assistant version.",
    )
    min_ha_parser.add_argument(
        "--python",
        action="store_true",
        help="Print only the Python version required by that Home Assistant release.",
    )
    release_parser = subparsers.add_parser(
        "release",
        help="Create a v-prefixed tag and GitHub release from VERSION.",
    )
    release_parser.add_argument(
        "--prerelease",
        action="store_true",
        help="Mark the release as a pre-release (default).",
    )
    release_parser.add_argument(
        "--stable",
        action="store_true",
        help="Create a stable release (overrides the default pre-release behaviour).",
    )
    args = parser.parse_args()

    if args.command == "check":
        if not check_versions():
            raise SystemExit(1)
        return
    if args.command == "sync":
        sync_versions()
        return
    if args.command == "min-ha":
        if args.version and args.python:
            raise SystemExit("--version and --python are mutually exclusive.")
        if args.version:
            print(MIN_HA_VERSION)
        elif args.python:
            print(MIN_HA_PYTHON)
        else:
            print(f"{MIN_HA_VERSION} {MIN_HA_PYTHON}")
        return
    if args.command == "release":
        if args.prerelease and args.stable:
            raise SystemExit("--prerelease and --stable are mutually exclusive.")
        run_release(prerelease=args.prerelease, stable=args.stable)
        return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

"""Refresh openapi.yaml at the repo root when the upstream dashboard gets a new release.

The dashboard publishes two things this check uses:

- ``https://dashboard.kirkhillcoop.org/api-docs/openapi.yaml`` -- the spec.
- ``https://dashboard.kirkhillcoop.org/api-docs`` -- an HTML page carrying
  ``data-release-id="<UTC timestamp>-<git sha>"``, a build stamp that changes
  exactly when the dashboard is redeployed.

``.github/openapi-release-id`` records the release the committed spec was last
synced against, so a daily run costs one small page fetch while nothing moves.
When the stamp changes, the spec is downloaded and compared with the committed
copy. Only a *content* difference counts: the committed file is byte-identical
to upstream only after a sync, so reformatting alone must not open a PR.

A content difference is then classified for the PR body:

- **New features** -- endpoints, schemas, properties, fields that became
  required, response/parameter components, an ``info.version`` bump.
- **Documentation only** -- descriptions and prose. Still synced (the file
  should track upstream), but labelled so nobody hunts for an endpoint that
  is not there.

This script only writes files locally. Committing, pushing and opening the PR
is the workflow's job (``.github/workflows/openapi-check.yml``), which also runs
``tests/test_openapi_contract.py`` against the refreshed spec and reports the
result in the PR body.

Run ``python scripts/openapi_check.py check --dry-run`` to see what would
change without touching anything.
"""

from __future__ import annotations

import argparse
import re
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = ROOT / "openapi.yaml"
RELEASE_FILE = ROOT / ".github" / "openapi-release-id"
DOCS_URL = "https://dashboard.kirkhillcoop.org/api-docs"
SPEC_URL = f"{DOCS_URL}/openapi.yaml"
RELEASE_RE = re.compile(r'data-release-id="([^"]+)"')
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def http_get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "kirkhill-openapi-check/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as error:
        # A fetch problem must fail the run loudly: silently reporting "no
        # change" on an unreachable API is how drift goes unnoticed.
        raise SystemExit(f"Could not fetch {url}: {error}") from error


def fetch_release_id() -> str:
    match = RELEASE_RE.search(http_get(DOCS_URL))
    if not match:
        raise SystemExit(f"No data-release-id found on {DOCS_URL}; the upstream docs page may have changed shape.")
    return match.group(1)


def read_recorded_release() -> str:
    return RELEASE_FILE.read_text(encoding="utf-8").strip() if RELEASE_FILE.exists() else ""


def parse_spec(text: str, label: str) -> dict:
    try:
        spec = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise SystemExit(f"{label} is not valid YAML: {error}") from error
    if not isinstance(spec, dict) or "paths" not in spec:
        raise SystemExit(f"{label} does not look like an OpenAPI document (no 'paths').")
    return spec


def _components(spec: dict, kind: str) -> dict:
    return (spec.get("components") or {}).get(kind) or {}


def _names(items: set | dict) -> list[str]:
    return sorted(items)


def _tick(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names)


def operations(spec: dict) -> set[str]:
    """Every ``METHOD path`` pair the document defines."""
    found: set[str] = set()
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for key in item:
            if key.lower() in HTTP_METHODS:
                found.add(f"{key.upper()} {path}")
    return found


def describe_features(old: dict, new: dict) -> list[str]:
    """What a reader would call new features, in the order they'd care about."""
    features: list[str] = []

    old_ops, new_ops = operations(old), operations(new)
    features += [f"New endpoint: `{op}`" for op in _names(new_ops - old_ops)]
    features += [f"Removed endpoint: `{op}`" for op in _names(old_ops - new_ops)]

    old_schemas, new_schemas = _components(old, "schemas"), _components(new, "schemas")
    features += [f"New schema: `{name}`" for name in _names(set(new_schemas) - set(old_schemas))]
    features += [f"Removed schema: `{name}`" for name in _names(set(old_schemas) - set(new_schemas))]

    for name in _names(set(old_schemas) & set(new_schemas)):
        old_props = set((old_schemas[name] or {}).get("properties") or {})
        new_props = set((new_schemas[name] or {}).get("properties") or {})
        added, removed = _names(new_props - old_props), _names(old_props - new_props)
        if added:
            features.append(f"`{name}` gained properties: {_tick(added)}")
        if removed:
            features.append(f"`{name}` dropped properties: {_tick(removed)}")
        old_required = set((old_schemas[name] or {}).get("required") or [])
        new_required = set((new_schemas[name] or {}).get("required") or [])
        now_required, no_longer = _names(new_required - old_required), _names(old_required - new_required)
        if now_required:
            # Called out explicitly: a field that became required breaks any
            # fixture or payload pinned to the old shape, which is exactly
            # what tests/test_openapi_contract.py asserts.
            features.append(f"`{name}` now requires: {_tick(now_required)}")
        if no_longer:
            features.append(f"`{name}` no longer requires: {_tick(no_longer)}")

    for kind, label in (("responses", "response"), ("parameters", "parameter")):
        old_items, new_items = _components(old, kind), _components(new, kind)
        features += [f"New {label} component: `{name}`" for name in _names(set(new_items) - set(old_items))]
        features += [f"Removed {label} component: `{name}`" for name in _names(set(old_items) - set(new_items))]

    old_version = (old.get("info") or {}).get("version")
    new_version = (new.get("info") or {}).get("version")
    if old_version != new_version:
        features.append(f"Spec `info.version` bumped: {old_version} -> {new_version}")

    return features


def render_summary(*, new_release: str, old_release: str, features: list[str], old_lines: int, new_lines: int) -> str:
    """PR body up to (but not including) the contract-test section.

    The workflow appends the test result: it can only run the test after this
    script has written the refreshed spec.
    """
    lines = [
        "## Sync `openapi.yaml` from the upstream dashboard",
        "",
        f"- Upstream release: `{new_release}`",
        f"- Previously recorded: `{old_release}`" if old_release else "- Previously recorded: *none*",
        f"- Spec: {SPEC_URL}",
        f"- `openapi.yaml`: {old_lines} -> {new_lines} lines",
        "",
    ]
    if features:
        lines += ["### New features", ""]
        lines += [f"- {feature}" for feature in features]
    else:
        lines += [
            "### Documentation only",
            "",
            "No new endpoints, schemas, properties or response components -- only descriptions changed.",
        ]
    lines += [
        "",
        "### Files in this PR",
        "",
        "- `openapi.yaml` -- refreshed from upstream",
        "- `.github/openapi-release-id` -- records the release this sync came from",
        "",
    ]
    return "\n".join(lines)


def write_outputs(path: Path | None, values: dict[str, str]) -> None:
    """Append ``key=value`` lines for GitHub Actions, if asked to."""
    if path is None:
        return
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def run_check(*, dry_run: bool, summary: Path | None, github_output: Path | None) -> None:
    new_release = fetch_release_id()
    old_release = read_recorded_release()
    print(f"Upstream release: {new_release}")
    print(f"Recorded release: {old_release or '(none recorded)'}")

    # The release id is only a cheap early exit -- it also moves for
    # front-end-only deploys, so the spec content is what decides whether
    # there is anything to sync. The id is recorded only when it is.
    if old_release == new_release:
        print("No new upstream release; nothing to do.")
        write_outputs(github_output, {"changed": "false", "release": new_release})
        return

    new_text = http_get(SPEC_URL)
    new_spec = parse_spec(new_text, "The upstream spec")
    old_text = SPEC_FILE.read_text(encoding="utf-8")
    old_spec = parse_spec(old_text, "openapi.yaml")

    if new_spec == old_spec:
        # Compare parsed documents, not bytes: upstream may reformat without
        # changing meaning, and a formatting-only PR is noise.
        print(f"Release {new_release} changed the build but not the spec content; nothing to sync.")
        write_outputs(github_output, {"changed": "false", "release": new_release})
        return

    features = describe_features(old_spec, new_spec)
    old_lines, new_lines = len(old_text.splitlines()), len(new_text.splitlines())
    kind = "New features" if features else "Documentation-only changes"
    print(f"Spec content changed ({old_lines} -> {new_lines} lines): {kind}")
    for feature in features:
        print(f"- {feature}")

    summary_text = render_summary(
        new_release=new_release,
        old_release=old_release,
        features=features,
        old_lines=old_lines,
        new_lines=new_lines,
    )
    if summary is not None:
        summary.write_text(summary_text, encoding="utf-8")
        print(f"Wrote summary to {summary}")

    if dry_run:
        print("Dry run: openapi.yaml and the release record were left untouched.")
    else:
        SPEC_FILE.write_text(new_text, encoding="utf-8")
        RELEASE_FILE.write_text(f"{new_release}\n", encoding="utf-8")
        print(f"Refreshed {SPEC_FILE} and recorded release {new_release}.")

    write_outputs(
        github_output, {"changed": "true", "features": "true" if features else "false", "release": new_release}
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync openapi.yaml from the upstream dashboard release.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser(
        "check",
        help="Detect a new upstream release and refresh openapi.yaml if its content changed.",
    )
    check_parser.add_argument("--dry-run", action="store_true", help="Report changes without writing any file.")
    check_parser.add_argument("--summary", type=Path, help="Write the PR-body markdown summary to this path.")
    check_parser.add_argument("--github-output", type=Path, help="Append changed/features/release outputs for Actions.")
    args = parser.parse_args()

    if args.command == "check":
        run_check(dry_run=args.dry_run, summary=args.summary, github_output=args.github_output)
        return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

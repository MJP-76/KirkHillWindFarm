"""Refresh openapi.yaml at the repo root when the upstream dashboard gets a new release.

The dashboard publishes two things this check uses:

- ``https://dashboard.kirkhillcoop.org/api-docs/openapi.yaml`` -- the spec.
- ``https://dashboard.kirkhillcoop.org/`` -- an HTML page carrying
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

The dashboard stopped serving the spec anonymously in its 2026-10-23 release:
``/api-docs`` and its spec now need a signed-in session, and an anonymous
request is redirected to the home page or answered
``401 {"message": "Please sign in to view API documentation."}``. When
``KH_DASHBOARD_EMAIL`` and ``KH_DASHBOARD_PASSWORD`` are set, the script signs
in through the dashboard's own JSON endpoint first -- the same route the web
app uses, ``POST /dashboard-api/login`` with an ``X-XSRF-TOKEN`` header taken
from the ``XSRF-TOKEN`` cookie. Without credentials it stays anonymous. Either
way the body is checked before it reaches the YAML parser, so an HTML page or
an auth gate fails with an explicit message instead of a PyYAML scanner error
pointing at a ``<script>`` block.

Run ``python scripts/openapi_check.py check --dry-run`` to see what would
change without touching anything.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = ROOT / "openapi.yaml"
RELEASE_FILE = ROOT / ".github" / "openapi-release-id"
BASE_URL = "https://dashboard.kirkhillcoop.org"
HOME_URL = f"{BASE_URL}/"
DOCS_URL = f"{BASE_URL}/api-docs"
SPEC_URL = f"{DOCS_URL}/openapi.yaml"
LOGIN_URL = f"{BASE_URL}/dashboard-api/login"
EMAIL_ENV = "KH_DASHBOARD_EMAIL"
PASSWORD_ENV = "KH_DASHBOARD_PASSWORD"
RELEASE_RE = re.compile(r'data-release-id="([^"]+)"')
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
SIGN_IN_RE = re.compile(r'Please sign in[^"]*', re.IGNORECASE)


@dataclass(frozen=True)
class HttpResponse:
    """A fetch, after redirects, with enough context to explain a bad body."""

    url: str
    final_url: str
    status: int
    content_type: str
    body: str

    @property
    def looks_like_html(self) -> bool:
        if self.content_type in ("text/html", "application/xhtml+xml"):
            return True
        return self.body.lstrip().startswith("<")


def _open(request: urllib.request.Request, opener: urllib.request.OpenerDirector | None) -> HttpResponse:
    """Perform ``request``. An HTTP error is returned, not raised: the body explains it."""
    open_url = opener.open if opener is not None else urllib.request.urlopen
    try:
        with open_url(request, timeout=30) as response:
            return HttpResponse(
                url=request.full_url,
                final_url=response.geturl(),
                status=response.status,
                content_type=response.headers.get_content_type(),
                body=response.read().decode("utf-8"),
            )
    except urllib.error.HTTPError as error:
        return HttpResponse(
            url=request.full_url,
            final_url=error.geturl(),
            status=error.code,
            content_type=error.headers.get_content_type() if error.headers else "",
            body=error.read().decode("utf-8", errors="replace"),
        )
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as error:
        # A transport problem must fail the run loudly: silently reporting "no
        # change" on an unreachable API is how drift goes unnoticed.
        raise SystemExit(f"Could not fetch {request.full_url}: {error}") from error


def http_get(url: str, opener: urllib.request.OpenerDirector | None = None) -> HttpResponse:
    request = urllib.request.Request(url, headers={"User-Agent": "kirkhill-openapi-check/1.0"})
    return _open(request, opener)


def http_post_json(
    url: str, payload: dict, headers: dict[str, str], opener: urllib.request.OpenerDirector
) -> HttpResponse:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "User-Agent": "kirkhill-openapi-check/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
            **headers,
        },
    )
    return _open(request, opener)


def _cookie_value(jar: http.cookiejar.CookieJar, name: str) -> str:
    for cookie in jar:
        if cookie.name == name:
            return urllib.parse.unquote(cookie.value)
    return ""


def _message(body: str) -> str:
    """The human-readable part of an upstream JSON error, if there is one."""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    message = payload.get("message")
    return message if isinstance(message, str) else ""


def sign_in(opener: urllib.request.OpenerDirector, jar: http.cookiejar.CookieJar) -> bool:
    """Sign in through the dashboard's JSON endpoint. Returns True when it did.

    ``KH_DASHBOARD_EMAIL`` and ``KH_DASHBOARD_PASSWORD`` are read from the
    environment so the workflow can pass repository secrets; nothing is logged
    beyond success or the upstream failure message.
    """
    email = os.environ.get(EMAIL_ENV, "").strip()
    password = os.environ.get(PASSWORD_ENV, "")
    if not email and not password:
        print("No dashboard credentials configured; fetching the spec anonymously.")
        return False
    if not email or not password:
        raise SystemExit(f"Set both {EMAIL_ENV} and {PASSWORD_ENV}, or neither.")

    # The login endpoint needs the XSRF-TOKEN cookie from a prior page load,
    # exactly as the dashboard's own client does.
    home = http_get(HOME_URL, opener)
    token = _cookie_value(jar, "XSRF-TOKEN")
    if not token:
        raise SystemExit(f"Dashboard sign-in failed: {HOME_URL} answered {home.status} but set no XSRF-TOKEN cookie.")

    response = http_post_json(
        LOGIN_URL,
        {"email": email, "password": password, "stay_logged_in": True},
        {"X-XSRF-TOKEN": token},
        opener,
    )
    detail = _message(response.body).rstrip(".") or "no message from the dashboard"
    if response.status != 200:
        raise SystemExit(
            f"Dashboard sign-in failed ({response.status}): {detail}. "
            f"Check the {EMAIL_ENV}/{PASSWORD_ENV} secrets. "
            "If the account uses two-factor authentication, CI cannot complete that step."
        )
    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError:
        payload = {}
    if isinstance(payload, dict) and payload.get("requires_two_factor"):
        raise SystemExit(
            "Dashboard sign-in asked for a two-factor code, which this workflow cannot supply. "
            "Use an account without 2FA for the sync, or fetch the spec manually."
        )
    print("Signed in to the dashboard.")
    return True


def _spec_unavailable(response: HttpResponse, authenticated: bool) -> str:
    """Explain, in one line, why the spec could not be read as YAML."""
    details = f"{SPEC_URL} answered {response.status}"
    if response.content_type:
        details += f" ({response.content_type})"
    if response.final_url != SPEC_URL:
        details += f" after redirecting to {response.final_url}"
    sign_in = SIGN_IN_RE.search(response.body)
    if sign_in:
        details += f' with "{sign_in.group(0)}"'
    if authenticated:
        return (
            f"The signed-in session still could not read the spec: {details}. "
            "The account may have lost access; check the credential, or fetch the spec manually."
        )
    return (
        f"The upstream spec is no longer public: {details}, so there is nothing to parse. "
        f"The dashboard now requires a signed-in session; set {EMAIL_ENV}/{PASSWORD_ENV} "
        "(or provide an anonymous copy) to let the daily sync read it."
    )


def fetch_release_id(opener: urllib.request.OpenerDirector | None = None) -> str:
    response = http_get(HOME_URL, opener)
    match = RELEASE_RE.search(response.body)
    if not match:
        raise SystemExit(
            f"No data-release-id found at {response.final_url} "
            f"(HTTP {response.status}, {response.content_type or 'no content type'}); "
            "the upstream home page may have changed shape."
        )
    return match.group(1)


def fetch_spec_text(opener: urllib.request.OpenerDirector | None = None, *, authenticated: bool = False) -> str:
    """Return the upstream spec, refusing a page that is not YAML.

    Without this guard the redirect to the dashboard home page reached
    ``yaml.safe_load``, which failed inside an inline ``<script>`` block with a
    scanner error that hid the real cause (the auth gate).
    """
    response = http_get(SPEC_URL, opener)
    if response.status != 200 or response.looks_like_html:
        raise SystemExit(_spec_unavailable(response, authenticated))
    return response.body


def read_recorded_release() -> str:
    return RELEASE_FILE.read_text(encoding="utf-8").strip() if RELEASE_FILE.exists() else ""


def parse_spec(text: str, label: str) -> dict:
    if text.lstrip().startswith("<"):
        raise SystemExit(f"{label} is HTML, not YAML: it starts with {text.lstrip()[:40]!r}.")
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
        # Ends on a blank line: the workflow appends the "### Contract test"
        # heading directly after this file, so without it the heading lands
        # glued to the last bullet.
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
    # Sign in first, even when the release id has not moved: a dead credential
    # should be reported on the day it dies, not the next time upstream ships.
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    authenticated = sign_in(opener, jar)

    new_release = fetch_release_id(opener)
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

    new_text = fetch_spec_text(opener, authenticated=authenticated)
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

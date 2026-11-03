"""Tests for the fetch guard in scripts/openapi_check.py.

The dashboard started requiring a signed-in session for ``/api-docs`` and its
spec in its 2026-10-23 release. An anonymous request is redirected to the home
page, which serves the dashboard's HTML; that HTML used to reach
``yaml.safe_load`` and fail on an inline ``<script>`` block, so the daily run
died with a scanner error that named neither the auth gate nor the redirect.
These tests pin the guard: HTML, a redirect away from the spec, and a non-200
status must all be reported as "the spec is no longer public".
"""

from __future__ import annotations

import importlib.util
import sys
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

ROOT = Path(__file__).parent.parent
HOME_URL = "https://dashboard.kirkhillcoop.org/"
SIGN_IN_BODY = '{"message":"Please sign in to view API documentation."}'


def _load_openapi_check():
    """Import scripts/openapi_check.py without requiring it to be a package."""
    spec = importlib.util.spec_from_file_location("openapi_check", ROOT / "scripts" / "openapi_check.py")
    module = importlib.util.module_from_spec(spec)
    # The module must be importable by name for dataclasses to resolve its
    # string annotations (``from __future__ import annotations``).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def checker():
    return _load_openapi_check()


class TestFetchSpecGuard:
    def test_sign_in_gate_is_reported_with_the_upstream_message(self, checker, monkeypatch):
        monkeypatch.setattr(
            checker,
            "http_get",
            lambda url, opener=None: checker.HttpResponse(
                url=url,
                final_url=url,
                status=401,
                content_type="application/json",
                body=SIGN_IN_BODY,
            ),
        )

        with pytest.raises(SystemExit) as excinfo:
            checker.fetch_spec_text()

        message = str(excinfo.value)
        assert "no longer public" in message
        assert "401" in message
        assert "Please sign in to view API documentation." in message

    def test_redirect_to_the_home_page_is_reported_with_the_final_url(self, checker, monkeypatch):
        monkeypatch.setattr(
            checker,
            "http_get",
            lambda url, opener=None: checker.HttpResponse(
                url=url,
                final_url=HOME_URL,
                status=200,
                content_type="text/html",
                body="<!doctype html><html><head><title>Dashboard</title></head></html>",
            ),
        )

        with pytest.raises(SystemExit) as excinfo:
            checker.fetch_spec_text()

        message = str(excinfo.value)
        assert "text/html" in message
        assert f"after redirecting to {HOME_URL}" in message

    def test_html_is_refused_even_when_it_is_labelled_yaml(self, checker, monkeypatch):
        monkeypatch.setattr(
            checker,
            "http_get",
            lambda url, opener=None: checker.HttpResponse(
                url=url,
                final_url=url,
                status=200,
                content_type="application/yaml",
                body="<!doctype html><html></html>",
            ),
        )

        with pytest.raises(SystemExit, match="no longer public"):
            checker.fetch_spec_text()

    def test_yaml_is_returned_unchanged(self, checker, monkeypatch):
        body = "openapi: 3.0.3\npaths: {}\n"
        monkeypatch.setattr(
            checker,
            "http_get",
            lambda url, opener=None: checker.HttpResponse(
                url=url,
                final_url=url,
                status=200,
                content_type="application/yaml",
                body=body,
            ),
        )

        assert checker.fetch_spec_text() == body

    def test_a_signed_in_failure_names_the_session_not_the_public_gate(self, checker, monkeypatch):
        monkeypatch.setattr(
            checker,
            "http_get",
            lambda url, opener=None: checker.HttpResponse(
                url=url,
                final_url=url,
                status=403,
                content_type="text/html",
                body="<html></html>",
            ),
        )

        with pytest.raises(SystemExit) as excinfo:
            checker.fetch_spec_text(authenticated=True)

        message = str(excinfo.value)
        assert "signed-in session still could not read the spec" in message
        assert "403" in message


class TestHttpGet:
    def test_an_http_error_is_returned_as_a_response(self, checker, monkeypatch):
        headers = Message()
        headers["Content-Type"] = "application/json"
        error = HTTPError(checker.SPEC_URL, 401, "Unauthorized", headers, BytesIO(SIGN_IN_BODY.encode()))
        monkeypatch.setattr(
            checker.urllib.request,
            "urlopen",
            lambda request, timeout: (_ for _ in ()).throw(error),
        )

        response = checker.http_get(checker.SPEC_URL)

        assert response.status == 401
        assert response.content_type == "application/json"
        assert response.body == SIGN_IN_BODY

    def test_a_transport_error_still_fails_loudly(self, checker, monkeypatch):
        monkeypatch.setattr(
            checker.urllib.request,
            "urlopen",
            lambda request, timeout: (_ for _ in ()).throw(URLError("unreachable")),
        )

        with pytest.raises(SystemExit, match="Could not fetch"):
            checker.http_get(checker.SPEC_URL)


class TestSignIn:
    def test_no_credentials_stays_anonymous(self, checker, monkeypatch):
        monkeypatch.delenv(checker.EMAIL_ENV, raising=False)
        monkeypatch.delenv(checker.PASSWORD_ENV, raising=False)

        assert checker.sign_in(object(), []) is False

    def test_one_credential_alone_is_rejected(self, checker, monkeypatch):
        monkeypatch.setenv(checker.EMAIL_ENV, "member@example.invalid")
        monkeypatch.delenv(checker.PASSWORD_ENV, raising=False)

        with pytest.raises(SystemExit, match="both"):
            checker.sign_in(object(), [])

    def test_signs_in_with_the_url_decoded_xsrf_cookie(self, checker, monkeypatch):
        monkeypatch.setenv(checker.EMAIL_ENV, "member@example.invalid")
        monkeypatch.setenv(checker.PASSWORD_ENV, "correct horse battery staple")
        jar = [SimpleNamespace(name="XSRF-TOKEN", value="abc%3Ddef")]
        captured = {}

        monkeypatch.setattr(
            checker,
            "http_get",
            lambda url, opener=None: checker.HttpResponse(url, url, 200, "text/html", "<html></html>"),
        )

        def fake_post(url, payload, headers, opener):
            captured.update(url=url, payload=payload, headers=headers)
            return checker.HttpResponse(
                url, url, 200, "application/json", '{"user":{"email":"member@example.invalid"}}'
            )

        monkeypatch.setattr(checker, "http_post_json", fake_post)

        assert checker.sign_in(object(), jar) is True
        assert captured["url"] == checker.LOGIN_URL
        assert captured["headers"] == {"X-XSRF-TOKEN": "abc=def"}
        assert captured["payload"]["email"] == "member@example.invalid"
        assert captured["payload"]["password"] == "correct horse battery staple"

    def test_a_rejected_sign_in_reports_the_message_and_not_the_password(self, checker, monkeypatch):
        monkeypatch.setenv(checker.EMAIL_ENV, "member@example.invalid")
        monkeypatch.setenv(checker.PASSWORD_ENV, "correct horse battery staple")
        jar = [SimpleNamespace(name="XSRF-TOKEN", value="token")]
        body = '{"message":"Please check your email address and password, then try again."}'

        monkeypatch.setattr(
            checker,
            "http_get",
            lambda url, opener=None: checker.HttpResponse(url, url, 200, "text/html", "<html></html>"),
        )
        monkeypatch.setattr(
            checker,
            "http_post_json",
            lambda url, payload, headers, opener: checker.HttpResponse(url, url, 422, "application/json", body),
        )

        with pytest.raises(SystemExit) as excinfo:
            checker.sign_in(object(), jar)

        message = str(excinfo.value)
        assert "422" in message
        assert "Please check your email address and password" in message
        assert "correct horse battery staple" not in message

    def test_a_two_factor_challenge_is_reported(self, checker, monkeypatch):
        monkeypatch.setenv(checker.EMAIL_ENV, "member@example.invalid")
        monkeypatch.setenv(checker.PASSWORD_ENV, "secret")
        jar = [SimpleNamespace(name="XSRF-TOKEN", value="token")]

        monkeypatch.setattr(
            checker,
            "http_get",
            lambda url, opener=None: checker.HttpResponse(url, url, 200, "text/html", "<html></html>"),
        )
        monkeypatch.setattr(
            checker,
            "http_post_json",
            lambda url, payload, headers, opener: checker.HttpResponse(
                url, url, 200, "application/json", '{"requires_two_factor":true,"methods":{"totp":true}}'
            ),
        )

        with pytest.raises(SystemExit, match="two-factor"):
            checker.sign_in(object(), jar)

    def test_a_missing_xsrf_cookie_is_reported(self, checker, monkeypatch):
        monkeypatch.setenv(checker.EMAIL_ENV, "member@example.invalid")
        monkeypatch.setenv(checker.PASSWORD_ENV, "secret")
        monkeypatch.setattr(
            checker,
            "http_get",
            lambda url, opener=None: checker.HttpResponse(url, url, 200, "text/html", "<html></html>"),
        )

        with pytest.raises(SystemExit, match="XSRF-TOKEN"):
            checker.sign_in(object(), [])


class TestReleaseStamp:
    def test_the_stamp_is_still_read_from_the_redirected_home_page(self, checker, monkeypatch):
        monkeypatch.setattr(
            checker,
            "http_get",
            lambda url, opener=None: checker.HttpResponse(
                url=url,
                final_url=HOME_URL,
                status=200,
                content_type="text/html",
                body='<html data-release-id="20261029T001606Z-5be915ce91ed">',
            ),
        )

        assert checker.fetch_release_id() == "20261029T001606Z-5be915ce91ed"


class TestParseSpec:
    def test_html_fails_as_html_not_as_a_yaml_scanner_error(self, checker):
        with pytest.raises(SystemExit) as excinfo:
            checker.parse_spec("<!doctype html>\n<html></html>", "The upstream spec")

        assert "is HTML, not YAML" in str(excinfo.value)

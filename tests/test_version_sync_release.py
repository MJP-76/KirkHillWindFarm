"""Tests for the release command in scripts/version_sync.py.

``run_release`` created the local tag and handed it straight to
``gh release create``, which refuses to publish a release from a tag that only
exists locally ("... has not been pushed ... please push it before
continuing"). The script's own "tag already exists" guard then blocked every
retry, so the release could not be cut at all -- the v4.13.7 attempt had to be
finished by hand. The tag now goes up before the release is created, and a
local tag left behind by a failed attempt is resumed rather than refused.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parent.parent


def _load_version_sync():
    """Import scripts/version_sync.py without requiring it to be a package."""
    spec = importlib.util.spec_from_file_location("version_sync_release", ROOT / "scripts" / "version_sync.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Recorder:
    """Stand in for subprocess.run, recording commands instead of running them.

    Only the two read-only git queries return anything meaningful; everything
    else (tag, push, gh) is recorded and reported as successful.
    """

    def __init__(self, *, local_tag: str = "", remote_tag: str = "") -> None:
        self.calls: list[list[str]] = []
        self._local_tag = local_tag
        self._remote_tag = remote_tag

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        stdout = ""
        if cmd[:3] == ["git", "tag", "--list"]:
            stdout = self._local_tag
        elif cmd[:3] == ["git", "ls-remote", "--tags"]:
            stdout = self._remote_tag
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)


@pytest.fixture
def version_sync():
    return _load_version_sync()


@pytest.fixture
def record(version_sync, monkeypatch):
    """Replace version_sync's subprocess module and return a recorder factory."""

    def _install(**kwargs) -> _Recorder:
        recorder = _Recorder(**kwargs)
        monkeypatch.setattr(version_sync, "subprocess", SimpleNamespace(run=recorder))
        return recorder

    return _install


class TestRunRelease:
    """The tag must exist on origin before gh is asked to publish it."""

    def test_tag_is_pushed_before_the_release_is_created(self, version_sync, record):
        recorder = record()

        version_sync.run_release(prerelease=True, stable=False)

        gh_index = next(i for i, c in enumerate(recorder.calls) if c[0] == "gh")
        push_index = next(i for i, c in enumerate(recorder.calls) if c[:3] == ["git", "push", "origin"])
        assert push_index < gh_index, (
            "gh release create refuses a tag that exists only locally, so the push has to happen first"
        )
        assert "--prerelease" in recorder.calls[gh_index]

    def test_local_tag_from_a_failed_attempt_is_resumed(self, version_sync, record):
        """A tag created by an earlier attempt is pushed, not recreated."""
        recorder = record(local_tag="unused")

        version_sync.run_release(prerelease=True, stable=False)

        tag_creations = [c for c in recorder.calls if c[:2] == ["git", "tag"] and "--list" not in c]
        assert tag_creations == []
        assert any(c[:3] == ["git", "push", "origin"] for c in recorder.calls)
        assert any(c[0] == "gh" for c in recorder.calls)

    def test_release_is_refused_when_the_tag_is_already_on_origin(self, version_sync, record):
        recorder = record(remote_tag="0f5ac9e\trefs/tags/v4.13.7")

        with pytest.raises(SystemExit, match="already exists on origin"):
            version_sync.run_release(prerelease=True, stable=False)

        assert not any(c[0] == "gh" for c in recorder.calls)
        assert not any(c[:3] == ["git", "push", "origin"] for c in recorder.calls)

    def test_stable_release_omits_the_prerelease_flag(self, version_sync, record):
        recorder = record()

        version_sync.run_release(prerelease=False, stable=True)

        gh_call = next(c for c in recorder.calls if c[0] == "gh")
        assert "--prerelease" not in gh_call

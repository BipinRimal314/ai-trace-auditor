"""Tests for the POST /audit/repo route."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "repos"


@pytest.fixture
def client():
    from ai_trace_auditor.web.server import app
    return TestClient(app)


def _fake_clone(fixture_name: str):
    def _fn(url, *, max_bytes, timeout_seconds, tmpdir_root):
        return FIXTURES / fixture_name
    return _fn


def test_post_audit_repo_renders_repo_results(client):
    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=_fake_clone("repo_with_traces"),
    ), patch(
        "ai_trace_auditor.web.audit_service._cleanup_repo_dir"
    ):
        resp = client.post(
            "/audit/repo",
            data={"repo_url": "https://github.com/test/repo_with_traces"},
        )

    assert resp.status_code == 200
    assert "Repository Audit" in resp.text
    assert "repo_with_traces" in resp.text


def test_post_audit_repo_missing_url_returns_400(client):
    resp = client.post("/audit/repo", data={"repo_url": ""})
    assert resp.status_code == 400


def test_post_audit_repo_invalid_url_returns_400(client):
    from ai_trace_auditor.repo.errors import InvalidRepoURL

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=InvalidRepoURL("bad url"),
    ):
        resp = client.post(
            "/audit/repo", data={"repo_url": "https://gitlab.com/x/y"}
        )

    assert resp.status_code == 400


def test_post_audit_repo_not_found_returns_404(client):
    from ai_trace_auditor.repo.errors import RepoNotFound

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=RepoNotFound("404"),
    ):
        resp = client.post(
            "/audit/repo", data={"repo_url": "https://github.com/x/missing"}
        )

    assert resp.status_code == 404


def test_post_audit_repo_too_large_returns_413(client):
    from ai_trace_auditor.repo.errors import RepoTooLarge

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=RepoTooLarge(actual_bytes=100_000_000, limit_bytes=52_428_800),
    ):
        resp = client.post(
            "/audit/repo", data={"repo_url": "https://github.com/x/huge"}
        )

    assert resp.status_code == 413


def test_post_audit_repo_timeout_returns_504(client):
    from ai_trace_auditor.repo.errors import RepoFetchTimeout

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=RepoFetchTimeout(seconds=30),
    ):
        resp = client.post(
            "/audit/repo", data={"repo_url": "https://github.com/x/slow"}
        )

    assert resp.status_code == 504


def test_audit_page_includes_repo_url_field(client):
    resp = client.get("/audit")
    assert resp.status_code == 200
    assert 'name="repo_url"' in resp.text

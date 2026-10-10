import ast
import asyncio
import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.identity import resolve_current_user


ROOT = Path(__file__).resolve().parents[1]


def test_migration_is_additive_and_scoped():
    sql = (ROOT / "backend/migrations/001_phase1b_master_library.sql").read_text(
        encoding="utf-8"
    )

    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()

    expected_tables = [
        "app_users",
        "profiles",
        "summary_variants",
        "education_items",
        "tool_groups",
        "tools",
        "content_items",
        "bullets",
        "bullet_variants",
        "interests",
        "resume_compositions",
        "seed_imports",
    ]

    for table in expected_tables:
        assert f"CREATE TABLE {table}" in sql


def _request_without_credentials() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/library",
            "raw_path": b"/api/library",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
        }
    )


def test_identity_is_fail_closed_outside_local(monkeypatch):
    monkeypatch.setenv("APP_ENV", "studioshare")

    request = _request_without_credentials()

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            resolve_current_user(
                request=request,
                authorization=None,
            )
        )

    assert caught.value.status_code == 401
    assert caught.value.detail == "Authenticated StudioShare identity is required."


def _render_measure_values(source: str) -> set[bool]:
    tree = ast.parse(source)
    values: set[bool] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if not isinstance(node.func, ast.Name):
            continue

        if node.func.id != "render_resume":
            continue

        if len(node.args) >= 2:
            measure_argument = node.args[1]

            if isinstance(measure_argument, ast.Constant) and isinstance(
                measure_argument.value, bool
            ):
                values.add(measure_argument.value)

        for keyword in node.keywords:
            if keyword.arg != "measure":
                continue

            if isinstance(keyword.value, ast.Constant) and isinstance(
                keyword.value.value, bool
            ):
                values.add(keyword.value.value)

    return values


def test_render_contract_remains_canonical():
    source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")

    measure_values = _render_measure_values(source)

    assert True in measure_values, (
        "Browser preview must call render_resume with measurement enabled."
    )
    assert False in measure_values, (
        "PDF export must call render_resume with measurement disabled."
    )

    assert source.count("render_resume(") >= 2

"""Contracts for AI suggestions and Skills quick add that the UI and PDF depend on."""

import json
from pathlib import Path

from app.render import render_resume

ROOT = Path(__file__).resolve().parents[1]
SEED = json.loads((ROOT / "seed/nia-calder-resume.json").read_text(encoding="utf-8"))


def test_preview_chip_never_reaches_the_pdf():
    preview = render_resume(SEED, True)
    pdf = render_resume(SEED, False)
    assert "suggest-chip" in preview and "resume-suggest" in preview
    assert "suggest-chip" not in pdf and "resume-suggest" not in pdf


def test_ai_provenance_is_not_rendered():
    for path in ("backend/app/render.py", "backend/app/templates/resume.html"):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "ai_generated" not in text and "ai_model" not in text


def test_skill_group_names_are_not_hardcoded():
    for path in ("backend/app/skill_groups.py", "frontend/src/AddSkillDialog.tsx"):
        text = (ROOT / path).read_text(encoding="utf-8")
        for name in ("Technical Languages", "Collaboration Tools", '"Platforms"'):
            assert name not in text, f"{name} in {path}"


def test_migration_adds_provenance_with_body_trigger():
    sql = (ROOT / "backend/migrations/024_bullet_variant_ai_provenance.sql").read_text(encoding="utf-8")
    assert "ai_generated boolean NOT NULL DEFAULT false" in sql
    assert "ON DELETE SET NULL" in sql
    assert "UPDATE OF body ON bullet_variants" in sql

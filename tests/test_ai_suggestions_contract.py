"""Contracts for AI suggestions and Skills quick add that the UI and PDF depend on."""

import json
from pathlib import Path

from app.render import render_resume

ROOT = Path(__file__).resolve().parents[1]
SEED = json.loads((ROOT / "seed/nia-calder-resume.json").read_text(encoding="utf-8"))


def test_clickable_highlights_never_reach_the_pdf():
    preview = render_resume(SEED, True)
    pdf = render_resume(SEED, False)
    assert "resume-mark-click" in preview
    assert "resume-mark-click" not in pdf


def test_old_text_block_review_is_retired_from_the_ui():
    sources = "".join(path.read_text(encoding="utf-8") for path in (ROOT / "frontend/src").rglob("*.tsx"))
    assert "AiReviewBody" not in sources and "Review with AI" not in sources
    assert not (ROOT / "frontend/src/JobMatchPanel.tsx").exists()


def test_ats_score_carries_methodology_and_disclaimer():
    from app.ats_score import DISCLAIMER, score_resume

    result = score_resume({"required": [], "preferred": []}, SEED, {"role": "Analyst"}, {}, 1)
    assert result["disclaimer"] == DISCLAIMER
    assert "not a guarantee" in DISCLAIMER and "may differ" in DISCLAIMER
    assert {item["id"] for item in result["methodology"]} == {item["id"] for item in result["components"]}


def test_ai_provenance_is_not_rendered():
    for path in ("backend/app/render.py", "backend/app/templates/resume.html"):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "ai_generated" not in text and "ai_model" not in text


def test_skill_group_names_are_not_hardcoded():
    for path in ("backend/app/skill_groups.py", "frontend/src/AddSkillDialog.tsx", "frontend/src/match/RequirementsTab.tsx"):
        text = (ROOT / path).read_text(encoding="utf-8")
        for name in ("Technical Languages", "Collaboration Tools", '"Platforms"'):
            assert name not in text, f"{name} in {path}"


def test_migration_adds_provenance_with_body_trigger():
    sql = (ROOT / "backend/migrations/024_bullet_variant_ai_provenance.sql").read_text(encoding="utf-8")
    assert "ai_generated boolean NOT NULL DEFAULT false" in sql
    assert "ON DELETE SET NULL" in sql
    assert "UPDATE OF body ON bullet_variants" in sql

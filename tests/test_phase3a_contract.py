
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def test_phase3a_refinement_contract():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "toolbar-rename-form" in app and "saveCompositionMetadata" in app
    assert "Collapse Resume Details" in app or "collapsed" in app
    assert "Always first" not in app
    assert "composition-manager" not in app
    assert '["tools", "Skills"]' in app
    assert "items/order" in app and "item-drag-handle" in app
    assert app.count("+ Add Bullet") == 2
    assert 'mode: "pick-bullet"' in app and "<AddBulletButton />" in app


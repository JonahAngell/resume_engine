from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase1c_migration_is_additive():
    s = (ROOT / "backend/migrations/002_phase1c_editing.sql").read_text(
        encoding="utf-8"
    )
    assert "DROP " not in s.upper() and "TRUNCATE" not in s.upper()
    assert "revision integer" in s


def test_owner_scoped_mutations_and_concurrency():
    s = (ROOT / "backend/app/editing_repository.py").read_text(encoding="utf-8")
    assert s.count("user_id=%s") >= 3
    assert "revision=%s" in s and "revision=revision+1" in s

import re
from collections import Counter
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[1] / "backend/migrations"
# Applied under these names before the rule existed; renaming would re-run them.
GRANDFATHERED = {"020"}


def test_migration_numbers_are_unique_and_well_formed():
    names = sorted(path.name for path in MIGRATIONS.glob("*.sql"))
    assert names
    for name in names:
        assert re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", name), name
    counts = Counter(name[:3] for name in names)
    duplicated = {number for number, count in counts.items() if count > 1}
    assert duplicated <= GRANDFATHERED, f"Use the next unused migration number, not {sorted(duplicated - GRANDFATHERED)}"

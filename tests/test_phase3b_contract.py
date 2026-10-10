from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_phase3b_cards_placements_and_entry_dialog():
 app=(ROOT/'frontend/src/App.tsx').read_text(encoding="utf-8")
 assert 'entry-card' in app and 'bullet-row' in app and 'AddEntryDialog' in app
 assert app.count('+ Add Bullet') == 1
 assert 'aria-disabled="true"' in app and 'Adding bullets is coming soon.' in app
def test_phase3b_routes_and_migration():
 main=(ROOT/'backend/app/main.py').read_text(encoding="utf-8"); repo=(ROOT/'backend/app/phase2j_repository.py').read_text(encoding="utf-8")
 assert main.index('bullet-placements/order') < main.index('bullet-placements/{placement_id}')
 assert '/api/compositions/{cid}/items' in main and '/api/compositions/{cid}/entries/create' in main
 assert 'variant_name' in repo and 'active_variant_count' in repo
 assert (ROOT/'backend/migrations/013_phase3b_placement_backfill.sql').exists()

-- Backfill normalized selections only for idempotently imported seed compositions.
-- This preserves existing custom compositions instead of guessing their selections.
INSERT INTO
  composition_items (composition_id, section, item_id, sort_order)
SELECT
  si.composition_id,
  'education',
  e.id,
  e.sort_order
FROM
  seed_imports si
  JOIN education_items e ON e.user_id = si.user_id
ON CONFLICT (composition_id, section, item_id) DO NOTHING;

INSERT INTO
  composition_items (composition_id, section, item_id, sort_order)
SELECT
  si.composition_id,
  'personal_interests',
  i.id,
  i.sort_order
FROM
  seed_imports si
  JOIN interests i ON i.user_id = si.user_id
ON CONFLICT (composition_id, section, item_id) DO NOTHING;

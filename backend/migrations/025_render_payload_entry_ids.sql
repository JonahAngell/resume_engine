-- Backfill library ids onto render_payload entries that lack them (seeded
-- compositions stored the raw seed JSON). Placements are applied by entry id,
-- so id-less entries never received placement changes. Entries are matched to
-- the composition's selected library items by content, with position as a
-- tie-breaker; entries with no content match are left untouched.
CREATE OR REPLACE FUNCTION pg_temp.backfill_section_ids(payload jsonb, cid_in uuid, sec text)
RETURNS jsonb LANGUAGE sql AS $$
  SELECT COALESCE(
    jsonb_agg(
      CASE
        WHEN e.entry ? 'id' AND e.entry->>'id' IS NOT NULL THEN e.entry
        WHEN m.item_id IS NULL THEN e.entry
        ELSE jsonb_set(e.entry, '{id}', to_jsonb(m.item_id::text), true)
      END
      ORDER BY e.n
    ),
    '[]'::jsonb
  )
  FROM jsonb_array_elements(payload->sec) WITH ORDINALITY e(entry, n)
  LEFT JOIN LATERAL (
    SELECT ci.item_id
    FROM composition_items ci
    LEFT JOIN content_items x ON sec IN ('projects', 'work_experience', 'leadership') AND x.id = ci.item_id
    LEFT JOIN education_items ed ON sec = 'education' AND ed.id = ci.item_id
    LEFT JOIN tool_groups tg ON sec = 'tool_groups' AND tg.id = ci.item_id
    WHERE ci.composition_id = cid_in
      AND ci.section = sec
      AND CASE sec
        WHEN 'projects' THEN x.id IS NOT NULL AND x.name IS NOT DISTINCT FROM e.entry->>'name'
        WHEN 'work_experience' THEN x.id IS NOT NULL AND x.organization IS NOT DISTINCT FROM e.entry->>'organization'
          AND x.title IS NOT DISTINCT FROM e.entry->>'title'
        WHEN 'leadership' THEN x.id IS NOT NULL AND x.organization IS NOT DISTINCT FROM e.entry->>'organization'
          AND x.title IS NOT DISTINCT FROM e.entry->>'title'
        WHEN 'education' THEN ed.id IS NOT NULL AND ed.institution IS NOT DISTINCT FROM e.entry->>'institution'
        WHEN 'tool_groups' THEN tg.id IS NOT NULL AND tg.name IS NOT DISTINCT FROM e.entry->>'name'
        ELSE false
      END
    ORDER BY abs(ci.sort_order - (e.n - 1)), ci.sort_order, ci.id
    LIMIT 1
  ) m ON true
$$;

UPDATE resume_compositions c
SET render_payload = c.render_payload
  || jsonb_build_object(
    'projects', pg_temp.backfill_section_ids(c.render_payload, c.id, 'projects'),
    'work_experience', pg_temp.backfill_section_ids(c.render_payload, c.id, 'work_experience'),
    'leadership', pg_temp.backfill_section_ids(c.render_payload, c.id, 'leadership'),
    'education', pg_temp.backfill_section_ids(c.render_payload, c.id, 'education'),
    'tool_groups', pg_temp.backfill_section_ids(c.render_payload, c.id, 'tool_groups')
  )
WHERE EXISTS (
  SELECT 1
  FROM unnest(ARRAY['projects', 'work_experience', 'leadership', 'education', 'tool_groups']) s(section)
  CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(c.render_payload->s.section) = 'array' THEN c.render_payload->s.section ELSE '[]'::jsonb END
  ) e(entry)
  WHERE e.entry->>'id' IS NULL
);

-- Interest placements are applied to personal_interest_items, which seeded
-- payloads never had. Rebuild it from the composition's selected interests.
UPDATE resume_compositions c
SET render_payload = jsonb_set(
  c.render_payload,
  '{personal_interest_items}',
  (
    SELECT jsonb_agg(jsonb_build_object('id', i.id::text, 'body', i.body, 'bullets', '[]'::jsonb) ORDER BY ci.sort_order, ci.id)
    FROM composition_items ci
    JOIN interests i ON i.id = ci.item_id
    WHERE ci.composition_id = c.id AND ci.section = 'personal_interests'
  ),
  true
)
WHERE COALESCE(jsonb_array_length(c.render_payload->'personal_interest_items'), 0) = 0
  AND EXISTS (
    SELECT 1 FROM composition_items ci
    WHERE ci.composition_id = c.id AND ci.section = 'personal_interests'
  );

-- Backfill only seed-imported composition rows that are visibly present in that composition payload.
INSERT INTO
  composition_items (composition_id, section, item_id, sort_order)
SELECT
  si.composition_id,
  'tool_groups',
  g.id,
  g.sort_order
FROM
  seed_imports si
  JOIN resume_compositions c ON c.id = si.composition_id
  AND c.user_id = si.user_id
  JOIN tool_groups g ON g.user_id = si.user_id
WHERE
  EXISTS (
    SELECT
      1
    FROM
      jsonb_array_elements(
        COALESCE(c.render_payload -> 'tool_groups', '[]'::jsonb)
      ) shown
    WHERE
      shown ->> 'name' = g.name
  )
ON CONFLICT (composition_id, section, item_id) DO NOTHING;

INSERT INTO
  composition_items (composition_id, section, item_id, sort_order)
SELECT
  si.composition_id,
  CASE x.kind
    WHEN 'project' THEN 'projects'
    WHEN 'employment' THEN 'work_experience'
    ELSE 'leadership'
  END,
  x.id,
  x.sort_order
FROM
  seed_imports si
  JOIN resume_compositions c ON c.id = si.composition_id
  AND c.user_id = si.user_id
  JOIN content_items x ON x.user_id = si.user_id
WHERE
  (
    x.kind = 'project'
    AND EXISTS (
      SELECT
        1
      FROM
        jsonb_array_elements(
          COALESCE(c.render_payload -> 'projects', '[]'::jsonb)
        ) shown
      WHERE
        shown ->> 'name' = x.name
        AND shown ->> 'date' = x.date_label
    )
  )
  OR (
    x.kind = 'employment'
    AND EXISTS (
      SELECT
        1
      FROM
        jsonb_array_elements(
          COALESCE(
            c.render_payload -> 'work_experience',
            '[]'::jsonb
          )
        ) shown
      WHERE
        shown ->> 'organization' = x.organization
        AND shown ->> 'title' = x.title
        AND shown ->> 'date' = x.date_label
    )
  )
  OR (
    x.kind = 'leadership'
    AND EXISTS (
      SELECT
        1
      FROM
        jsonb_array_elements(
          COALESCE(c.render_payload -> 'leadership', '[]'::jsonb)
        ) shown
      WHERE
        shown ->> 'organization' = x.organization
        AND shown ->> 'title' = x.title
        AND shown ->> 'date' = x.date_label
    )
  )
ON CONFLICT (composition_id, section, item_id) DO NOTHING;

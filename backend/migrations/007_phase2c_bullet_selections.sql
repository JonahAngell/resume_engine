-- Backfill only deterministic seed composition selections whose rendered parent and bullet wording match.
WITH
  visible AS (
    SELECT
      si.composition_id,
      si.user_id,
      x.id parent_id,
      b.id bullet_id,
      v.id variant_id,
      b.sort_order,
      CASE x.kind
        WHEN 'project' THEN 'projects'
        WHEN 'employment' THEN 'work_experience'
        ELSE 'leadership'
      END section,
      CASE
        WHEN x.kind = 'project' THEN x.name
        ELSE x.organization
      END parent_name,
      CASE
        WHEN x.kind = 'project' THEN x.subtitle
        ELSE x.title
      END parent_secondary,
      x.date_label,
      v.body
    FROM
      seed_imports si
      JOIN content_items x ON x.user_id = si.user_id
      JOIN bullets b ON b.parent_id = x.id
      AND b.user_id = si.user_id
      JOIN bullet_variants v ON v.bullet_id = b.id
      AND v.user_id = si.user_id
      AND v.is_default
      AND v.archived_at IS NULL
  ),
  exact_matches AS (
    SELECT
      visible.*
    FROM
      visible
      JOIN resume_compositions c ON c.id = visible.composition_id
      AND c.user_id = visible.user_id
    WHERE
      EXISTS (
        SELECT
          1
        FROM
          jsonb_array_elements(
            COALESCE(c.render_payload -> visible.section, '[]'::jsonb)
          ) item,
          jsonb_array_elements_text(COALESCE(item -> 'bullets', '[]'::jsonb)) wording
        WHERE
          item ->> 'date' = visible.date_label
          AND (
            item ->> 'name' = visible.parent_name
            OR item ->> 'organization' = visible.parent_name
          )
          AND (
            item ->> 'subtitle' = visible.parent_secondary
            OR item ->> 'title' = visible.parent_secondary
          )
          AND wording = visible.body
      )
  )
INSERT INTO
  composition_bullets (composition_id, bullet_id, variant_id, sort_order)
SELECT
  composition_id,
  bullet_id,
  variant_id,
  sort_order
FROM
  exact_matches
ON CONFLICT (composition_id, bullet_id) DO NOTHING;

CREATE INDEX IF NOT EXISTS composition_bullets_variant_lookup ON composition_bullets (variant_id, composition_id);

CREATE INDEX IF NOT EXISTS bullet_variants_bullet_order ON bullet_variants (bullet_id, sort_order, id);

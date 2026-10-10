-- Phase 3b additive placement backfill. Existing rendered wording is preserved.
INSERT INTO
  composition_bullets (
    composition_id,
    bullet_id,
    variant_id,
    destination_section,
    destination_parent_type,
    destination_parent_id,
    sort_order,
    wording_snapshot,
    snapshot_source_updated_at
  )
SELECT
  ci.composition_id,
  b.id,
  v.id,
  ci.section,
  'content_item',
  ci.item_id,
  b.sort_order,
  rendered.wording,
  v.updated_at
FROM
  composition_items ci
  JOIN resume_compositions c ON c.id = ci.composition_id
  JOIN content_items x ON x.id = ci.item_id
  JOIN bullets b ON b.parent_id = x.id
  AND b.user_id = x.user_id
  JOIN LATERAL (
    SELECT
      id,
      body,
      updated_at
    FROM
      bullet_variants
    WHERE
      bullet_id = b.id
      AND archived_at IS NULL
    ORDER BY
      is_default DESC,
      sort_order,
      id
    LIMIT
      1
  ) v ON TRUE
  JOIN LATERAL (
    SELECT
      COALESCE(
        c.render_payload -> ci.section -> (ci.sort_order) -> 'bullets' ->> b.sort_order,
        v.body
      ) wording
  ) rendered ON TRUE
WHERE
  ci.section IN ('projects', 'work_experience', 'leadership')
  AND NOT EXISTS (
    SELECT
      1
    FROM
      composition_bullets cb
    WHERE
      cb.composition_id = ci.composition_id
      AND cb.destination_parent_id = ci.item_id
  )
ON CONFLICT DO NOTHING;

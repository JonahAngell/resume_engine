-- Phase 2J: canonical reusable bullets and resume-specific placements.
-- Additive and non-destructive. Existing identifiers and render payloads remain valid.
ALTER TABLE bullets
ALTER COLUMN parent_id
DROP NOT NULL,
ADD COLUMN IF NOT EXISTS section text NOT NULL DEFAULT 'experience',
ADD COLUMN IF NOT EXISTS parent_context text;

UPDATE bullets b
SET
  section = CASE ci.kind
    WHEN 'project' THEN 'projects'
    WHEN 'employment' THEN 'experience'
    ELSE 'leadership'
  END
FROM
  content_items ci
WHERE
  ci.id = b.parent_id;

ALTER TABLE bullets
ADD CONSTRAINT bullets_section_check CHECK (
  section IN (
    'experience',
    'projects',
    'education',
    'leadership',
    'skills',
    'interests',
    'custom'
  )
);

ALTER TABLE composition_bullets
ADD COLUMN IF NOT EXISTS destination_section text,
ADD COLUMN IF NOT EXISTS destination_parent_type text,
ADD COLUMN IF NOT EXISTS destination_parent_id uuid,
ADD COLUMN IF NOT EXISTS wording_snapshot text,
ADD COLUMN IF NOT EXISTS snapshot_source_updated_at timestamptz,
ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE composition_bullets
ADD CONSTRAINT composition_bullets_destination_section_check CHECK (
  destination_section IS NULL
  OR destination_section IN (
    'projects',
    'work_experience',
    'education',
    'leadership',
    'tool_groups',
    'personal_interests',
    'custom_sections'
  )
),
ADD CONSTRAINT composition_bullets_destination_type_check CHECK (
  destination_parent_type IS NULL
  OR destination_parent_type IN (
    'content_item',
    'education_item',
    'tool_group',
    'interest',
    'custom_entry'
  )
);

-- Existing composition selections are deterministic because the historical bullet parent is explicit.
UPDATE composition_bullets cb
SET
  destination_section = CASE ci.kind
    WHEN 'project' THEN 'projects'
    WHEN 'employment' THEN 'work_experience'
    ELSE 'leadership'
  END,
  destination_parent_type = 'content_item',
  destination_parent_id = b.parent_id,
  wording_snapshot = v.body,
  snapshot_source_updated_at = v.updated_at,
  updated_at = now()
FROM
  bullets b
  JOIN content_items ci ON ci.id = b.parent_id
  AND ci.user_id = b.user_id
  JOIN bullet_variants v ON v.bullet_id = b.id
  AND v.user_id = b.user_id
WHERE
  cb.bullet_id = b.id
  AND v.id = cb.variant_id
  AND cb.destination_parent_id IS NULL;

CREATE INDEX IF NOT EXISTS composition_bullets_destination_order ON composition_bullets (
  composition_id,
  destination_section,
  destination_parent_type,
  destination_parent_id,
  sort_order,
  id
);

CREATE INDEX IF NOT EXISTS composition_bullets_usage_lookup ON composition_bullets (bullet_id, composition_id);

CREATE INDEX IF NOT EXISTS composition_bullets_variant_usage_lookup ON composition_bullets (variant_id, composition_id);

CREATE OR REPLACE FUNCTION phase2j_destination_user (parent_type text, parent_id uuid) RETURNS uuid LANGUAGE plpgsql STABLE AS $$
DECLARE result uuid;
BEGIN
  IF parent_type='content_item' THEN SELECT user_id INTO result FROM content_items WHERE id=parent_id;
  ELSIF parent_type='education_item' THEN SELECT user_id INTO result FROM education_items WHERE id=parent_id;
  ELSIF parent_type='tool_group' THEN SELECT user_id INTO result FROM tool_groups WHERE id=parent_id;
  ELSIF parent_type='interest' THEN SELECT user_id INTO result FROM interests WHERE id=parent_id;
  ELSIF parent_type='custom_entry' THEN SELECT user_id INTO result FROM custom_section_entries WHERE id=parent_id;
  END IF;
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION enforce_phase2j_placement_ownership () RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE composition_user uuid; bullet_user uuid; variant_user uuid; destination_user uuid;
BEGIN
  SELECT user_id INTO composition_user FROM resume_compositions WHERE id=NEW.composition_id;
  SELECT user_id INTO bullet_user FROM bullets WHERE id=NEW.bullet_id;
  SELECT user_id INTO variant_user FROM bullet_variants WHERE id=NEW.variant_id AND bullet_id=NEW.bullet_id;
  destination_user := phase2j_destination_user(NEW.destination_parent_type, NEW.destination_parent_id);
  IF composition_user IS NULL OR bullet_user IS NULL OR variant_user IS NULL OR destination_user IS NULL
     OR composition_user<>bullet_user OR composition_user<>variant_user OR composition_user<>destination_user THEN
    RAISE EXCEPTION 'composition bullet ownership mismatch' USING ERRCODE='23503';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS composition_bullets_owner_guard ON composition_bullets;

CREATE TRIGGER composition_bullets_owner_guard
BEFORE INSERT OR UPDATE ON composition_bullets FOR EACH ROW
EXECUTE FUNCTION enforce_phase2j_placement_ownership ();

-- Exactly one active default remains enforced by the existing partial unique index.
-- Repair legacy bullets with active variants but no active default deterministically.
WITH
  ranked AS (
    SELECT
      id,
      bullet_id,
      row_number() OVER (
        PARTITION BY
          bullet_id
        ORDER BY
          sort_order,
          id
      ) rn
    FROM
      bullet_variants
    WHERE
      archived_at IS NULL
  ),
  missing AS (
    SELECT
      r.id
    FROM
      ranked r
    WHERE
      r.rn = 1
      AND NOT EXISTS (
        SELECT
          1
        FROM
          bullet_variants d
        WHERE
          d.bullet_id = r.bullet_id
          AND d.archived_at IS NULL
          AND d.is_default
      )
  )
UPDATE bullet_variants
SET
  is_default = TRUE,
  updated_at = now()
WHERE
  id IN (
    SELECT
      id
    FROM
      missing
  );

CREATE OR REPLACE FUNCTION enrich_composition_revision_snapshot () RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE composition resume_compositions%ROWTYPE;
BEGIN
  SELECT * INTO composition FROM resume_compositions WHERE id=NEW.composition_id;
  IF composition.id IS NULL OR composition.user_id<>NEW.user_id THEN
    RAISE EXCEPTION 'ownership mismatch' USING ERRCODE='23503';
  END IF;
  NEW.snapshot=COALESCE(NEW.snapshot,'{}'::jsonb) || jsonb_build_object(
    'name',composition.name,'description',composition.description,
    'display_title',composition.display_title,'target_company',composition.target_company,
    'target_role',composition.target_role,
    'bullet_placements',COALESCE((SELECT jsonb_agg(jsonb_build_object(
      'id',cb.id,'bullet_id',cb.bullet_id,'variant_id',cb.variant_id,
      'destination_section',cb.destination_section,'destination_parent_type',cb.destination_parent_type,
      'destination_parent_id',cb.destination_parent_id,'sort_order',cb.sort_order,
      'wording_snapshot',cb.wording_snapshot,'snapshot_source_updated_at',cb.snapshot_source_updated_at
    ) ORDER BY cb.destination_section,cb.destination_parent_id,cb.sort_order,cb.id)
    FROM composition_bullets cb WHERE cb.composition_id=NEW.composition_id),'[]'::jsonb)
  );
  RETURN NEW;
END $$;

-- Enrich existing snapshots with the deterministic relationship state available at migration time.
UPDATE composition_revisions r
SET
  snapshot = r.snapshot || jsonb_build_object(
    'bullet_placements',
    COALESCE(
      (
        SELECT
          jsonb_agg(
            jsonb_build_object(
              'id',
              cb.id,
              'bullet_id',
              cb.bullet_id,
              'variant_id',
              cb.variant_id,
              'destination_section',
              cb.destination_section,
              'destination_parent_type',
              cb.destination_parent_type,
              'destination_parent_id',
              cb.destination_parent_id,
              'sort_order',
              cb.sort_order,
              'wording_snapshot',
              cb.wording_snapshot,
              'snapshot_source_updated_at',
              cb.snapshot_source_updated_at
            )
            ORDER BY
              cb.destination_section,
              cb.destination_parent_id,
              cb.sort_order,
              cb.id
          )
        FROM
          composition_bullets cb
        WHERE
          cb.composition_id = r.composition_id
      ),
      '[]'::jsonb
    )
  );

-- Permit canonical Library bullets without descriptive parent context while retaining ownership checks.
CREATE OR REPLACE FUNCTION enforce_matching_user_ownership () RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_user uuid;
BEGIN
  IF TG_TABLE_NAME='tools' THEN SELECT user_id INTO expected_user FROM tool_groups WHERE id=NEW.group_id;
  ELSIF TG_TABLE_NAME='bullets' THEN
    IF NEW.parent_id IS NULL THEN expected_user:=NEW.user_id;
    ELSE SELECT user_id INTO expected_user FROM content_items WHERE id=NEW.parent_id;
    END IF;
  ELSIF TG_TABLE_NAME='bullet_variants' THEN SELECT user_id INTO expected_user FROM bullets WHERE id=NEW.bullet_id;
  ELSIF TG_TABLE_NAME='seed_imports' THEN SELECT user_id INTO expected_user FROM resume_compositions WHERE id=NEW.composition_id;
  END IF;
  IF expected_user IS NULL OR expected_user<>NEW.user_id THEN RAISE EXCEPTION 'ownership mismatch' USING ERRCODE='23503'; END IF;
  RETURN NEW;
END $$;

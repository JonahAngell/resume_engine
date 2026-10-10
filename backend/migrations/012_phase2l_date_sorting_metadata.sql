-- Phase 2L: additive composition preferences and structured custom-entry dates.
ALTER TABLE resume_compositions
ADD COLUMN preferred_page_length integer NOT NULL DEFAULT 1 CHECK (preferred_page_length IN (1, 2, 3)),
ADD COLUMN date_format text NOT NULL DEFAULT 'long' CHECK (
  date_format IN ('year', 'numeric', 'short', 'long')
),
ADD COLUMN section_sort_modes jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE resume_compositions
ADD CONSTRAINT resume_compositions_name_trimmed CHECK (btrim(name) <> ''),
ADD CONSTRAINT resume_compositions_name_length CHECK (length(name) <= 120);

ALTER TABLE custom_section_entries
ADD COLUMN start_year integer CHECK (start_year BETWEEN 1900 AND 2200),
ADD COLUMN start_month integer CHECK (start_month BETWEEN 1 AND 12),
ADD COLUMN end_year integer CHECK (end_year BETWEEN 1900 AND 2200),
ADD COLUMN end_month integer CHECK (end_month BETWEEN 1 AND 12),
ADD COLUMN is_current boolean NOT NULL DEFAULT FALSE;

ALTER TABLE content_items
ADD CONSTRAINT content_items_month_requires_year CHECK (
  (
    start_month IS NULL
    OR start_year IS NOT NULL
  )
  AND (
    end_month IS NULL
    OR end_year IS NOT NULL
  )
);

ALTER TABLE content_items
ADD CONSTRAINT content_items_current_has_no_end CHECK (
  NOT is_current
  OR (
    end_year IS NULL
    AND end_month IS NULL
  )
);

ALTER TABLE custom_section_entries
ADD CONSTRAINT custom_entries_month_requires_year CHECK (
  (
    start_month IS NULL
    OR start_year IS NOT NULL
  )
  AND (
    end_month IS NULL
    OR end_year IS NOT NULL
  )
);

ALTER TABLE custom_section_entries
ADD CONSTRAINT custom_entries_current_has_no_end CHECK (
  NOT is_current
  OR (
    end_year IS NULL
    AND end_month IS NULL
  )
);

CREATE INDEX resume_compositions_home_search ON resume_compositions (
  user_id,
  archived_at,
  lower(name),
  lower(display_title),
  lower(target_company),
  lower(target_role)
);

UPDATE composition_revisions r
SET
  snapshot = r.snapshot || jsonb_build_object(
    'preferred_page_length',
    c.preferred_page_length,
    'date_format',
    c.date_format,
    'section_sort_modes',
    c.section_sort_modes
  )
FROM
  resume_compositions c
WHERE
  c.id = r.composition_id;

CREATE OR REPLACE FUNCTION enrich_composition_revision_snapshot () RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c resume_compositions%ROWTYPE;
BEGIN
 SELECT * INTO c FROM resume_compositions WHERE id=NEW.composition_id;
 IF c.id IS NULL OR c.user_id<>NEW.user_id THEN RAISE EXCEPTION 'ownership mismatch' USING ERRCODE='23503'; END IF;
 NEW.snapshot=COALESCE(NEW.snapshot,'{}'::jsonb)||jsonb_build_object('name',c.name,'description',c.description,'display_title',c.display_title,'target_company',c.target_company,'target_role',c.target_role,'preferred_page_length',c.preferred_page_length,'date_format',c.date_format,'section_sort_modes',c.section_sort_modes,'bullet_placements',COALESCE((SELECT jsonb_agg(to_jsonb(cb) ORDER BY cb.destination_section,cb.destination_parent_id,cb.sort_order,cb.id) FROM composition_bullets cb WHERE cb.composition_id=NEW.composition_id),'[]'::jsonb));
 RETURN NEW;
END $$;

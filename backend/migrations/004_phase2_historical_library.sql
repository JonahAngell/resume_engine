ALTER TABLE education_items
ADD COLUMN college_school text;

ALTER TABLE education_items
ADD COLUMN degree_type text;

ALTER TABLE education_items
ADD COLUMN degree_major text;

ALTER TABLE education_items
ADD COLUMN graduation_year integer;

ALTER TABLE education_items
ADD COLUMN graduation_month integer CHECK (graduation_month BETWEEN 1 AND 12);

ALTER TABLE education_items
ADD COLUMN display_date text;

UPDATE education_items
SET
  degree_major = degree,
  display_date = graduation_date
WHERE
  degree_major IS NULL;

ALTER TABLE content_items
ADD COLUMN start_year integer;

ALTER TABLE content_items
ADD COLUMN start_month integer CHECK (start_month BETWEEN 1 AND 12);

ALTER TABLE content_items
ADD COLUMN end_year integer;

ALTER TABLE content_items
ADD COLUMN end_month integer CHECK (end_month BETWEEN 1 AND 12);

ALTER TABLE content_items
ADD COLUMN is_current boolean NOT NULL DEFAULT FALSE;

ALTER TABLE content_items
ADD COLUMN tags TEXT[] NOT NULL DEFAULT '{}';

ALTER TABLE summary_variants
ADD COLUMN tags TEXT[] NOT NULL DEFAULT '{}';

ALTER TABLE resume_compositions
ADD COLUMN description text NOT NULL DEFAULT '';

ALTER TABLE resume_compositions
ADD COLUMN tags TEXT[] NOT NULL DEFAULT '{}';

ALTER TABLE resume_compositions
ADD COLUMN interest_layout text NOT NULL DEFAULT 'compact' CHECK (interest_layout IN ('compact', 'lines'));

ALTER TABLE resume_compositions
ADD COLUMN section_order jsonb NOT NULL DEFAULT '["summary","education","tools","projects","work_experience","leadership","personal_interests"]'::jsonb;

CREATE TABLE custom_sections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  title text NOT NULL,
  layout text NOT NULL DEFAULT 'list' CHECK (
    layout IN ('list', 'compact', 'dated', 'experience')
  ),
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, title)
);

CREATE TABLE custom_section_entries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  section_id uuid NOT NULL REFERENCES custom_sections (id),
  primary_text text NOT NULL,
  secondary_text text,
  location text,
  date_label text,
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE composition_custom_sections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  composition_id uuid NOT NULL REFERENCES resume_compositions (id),
  section_id uuid NOT NULL REFERENCES custom_sections (id),
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  UNIQUE (composition_id, section_id)
);

CREATE TABLE composition_revisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  composition_id uuid NOT NULL REFERENCES resume_compositions (id),
  user_id uuid NOT NULL REFERENCES app_users (id),
  revision integer NOT NULL,
  source text NOT NULL DEFAULT 'autosave',
  note text,
  snapshot jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (composition_id, revision)
);

CREATE INDEX composition_revisions_lookup ON composition_revisions (composition_id, revision DESC);

CREATE INDEX summary_search ON summary_variants (user_id, lower(name));

CREATE INDEX content_search ON content_items (
  user_id,
  kind,
  lower(COALESCE(name, organization, ''))
);

CREATE INDEX custom_sections_order ON custom_sections (user_id, sort_order);

CREATE OR REPLACE FUNCTION enforce_phase2_ownership () RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE expected uuid; BEGIN
 IF TG_TABLE_NAME='custom_section_entries' THEN SELECT user_id INTO expected FROM custom_sections WHERE id=NEW.section_id;
 ELSIF TG_TABLE_NAME='composition_custom_sections' THEN SELECT c.user_id INTO expected FROM resume_compositions c JOIN custom_sections s ON s.id=NEW.section_id AND s.user_id=c.user_id WHERE c.id=NEW.composition_id;
 ELSIF TG_TABLE_NAME='composition_revisions' THEN SELECT user_id INTO expected FROM resume_compositions WHERE id=NEW.composition_id;
 END IF;
 IF expected IS NULL OR (TG_TABLE_NAME<>'composition_custom_sections' AND expected<>NEW.user_id) THEN RAISE EXCEPTION 'ownership mismatch' USING ERRCODE='23503'; END IF; RETURN NEW; END $$;

CREATE TRIGGER custom_entry_owner_guard
BEFORE INSERT OR UPDATE ON custom_section_entries FOR EACH ROW
EXECUTE FUNCTION enforce_phase2_ownership ();

CREATE TRIGGER composition_custom_owner_guard
BEFORE INSERT OR UPDATE ON composition_custom_sections FOR EACH ROW
EXECUTE FUNCTION enforce_phase2_ownership ();

CREATE TRIGGER composition_revision_owner_guard
BEFORE INSERT OR UPDATE ON composition_revisions FOR EACH ROW
EXECUTE FUNCTION enforce_phase2_ownership ();

INSERT INTO
  composition_revisions (
    composition_id,
    user_id,
    revision,
    source,
    snapshot
  )
SELECT
  id,
  user_id,
  revision,
  'migration',
  jsonb_build_object(
    'name',
    name,
    'description',
    description,
    'resume',
    render_payload,
    'interest_layout',
    interest_layout,
    'section_order',
    section_order
  )
FROM
  resume_compositions
ON CONFLICT DO NOTHING;

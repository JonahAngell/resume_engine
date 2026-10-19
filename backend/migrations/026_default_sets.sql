-- Defaults sets replace starter resumes. A library record or bullet can belong to
-- many sets, and each membership names the wording (variant) that set uses.
CREATE TABLE default_sets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  name text NOT NULL CHECK (btrim(name) <> ''),
  description text NOT NULL DEFAULT '',
  is_default boolean NOT NULL DEFAULT false,
  sort_order integer NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX one_default_set_per_user ON default_sets (user_id)
WHERE
  is_default
  AND archived_at IS NULL;

CREATE UNIQUE INDEX default_set_names ON default_sets (user_id, lower(name))
WHERE
  archived_at IS NULL;

CREATE TABLE default_set_members (
  set_id uuid NOT NULL REFERENCES default_sets (id) ON DELETE CASCADE,
  item_type text NOT NULL CHECK (
    item_type IN (
      'content_item',
      'education_item',
      'tool_group',
      'interest',
      'custom_section',
      'summary',
      'profile',
      'bullet'
    )
  ),
  item_id uuid NOT NULL,
  variant_id uuid,
  sort_order integer NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (set_id, item_type, item_id)
);

CREATE INDEX default_set_members_item ON default_set_members (item_type, item_id);

CREATE OR REPLACE FUNCTION enforce_default_set_member_ownership () RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE su uuid; iu uuid; vu uuid;
BEGIN
  SELECT user_id INTO su FROM default_sets WHERE id=NEW.set_id;
  IF NEW.item_type='content_item' THEN
    SELECT user_id INTO iu FROM content_items WHERE id=NEW.item_id;
    IF NEW.variant_id IS NOT NULL THEN
      SELECT user_id INTO vu FROM content_item_variants WHERE id=NEW.variant_id AND content_item_id=NEW.item_id;
    END IF;
  ELSIF NEW.item_type='education_item' THEN
    SELECT user_id INTO iu FROM education_items WHERE id=NEW.item_id;
    IF NEW.variant_id IS NOT NULL THEN
      SELECT user_id INTO vu FROM education_item_variants WHERE id=NEW.variant_id AND education_item_id=NEW.item_id;
    END IF;
  ELSIF NEW.item_type='tool_group' THEN
    SELECT user_id INTO iu FROM tool_groups WHERE id=NEW.item_id;
  ELSIF NEW.item_type='interest' THEN
    SELECT user_id INTO iu FROM interests WHERE id=NEW.item_id;
  ELSIF NEW.item_type='custom_section' THEN
    SELECT user_id INTO iu FROM custom_sections WHERE id=NEW.item_id;
  ELSIF NEW.item_type='summary' THEN
    SELECT user_id INTO iu FROM summary_variants WHERE id=NEW.item_id;
  ELSIF NEW.item_type='profile' THEN
    SELECT user_id INTO iu FROM profiles WHERE id=NEW.item_id;
    IF NEW.variant_id IS NOT NULL THEN
      SELECT user_id INTO vu FROM profile_field_variants WHERE id=NEW.variant_id AND profile_id=NEW.item_id;
    END IF;
  ELSIF NEW.item_type='bullet' THEN
    SELECT user_id INTO iu FROM bullets WHERE id=NEW.item_id;
    IF NEW.variant_id IS NOT NULL THEN
      SELECT user_id INTO vu FROM bullet_variants WHERE id=NEW.variant_id AND bullet_id=NEW.item_id;
    END IF;
  END IF;
  IF su IS NULL OR iu IS NULL OR su<>iu
     OR (NEW.variant_id IS NOT NULL AND (vu IS NULL OR vu<>su)) THEN
    RAISE EXCEPTION 'default set ownership mismatch' USING ERRCODE='23503';
  END IF;
  IF NEW.item_type IN ('tool_group','interest','custom_section','summary') AND NEW.variant_id IS NOT NULL THEN
    RAISE EXCEPTION 'record has no variants' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER default_set_members_owner_guard
BEFORE INSERT OR UPDATE ON default_set_members FOR EACH ROW
EXECUTE FUNCTION enforce_default_set_member_ownership ();

-- Convert each active starter resume into a defaults set with the same contents.
CREATE TEMP TABLE starter_sets AS
SELECT
  c.id composition_id,
  gen_random_uuid() set_id,
  c.user_id,
  c.name,
  c.description,
  c.is_default_starter,
  row_number() OVER (PARTITION BY c.user_id ORDER BY c.created_at, c.id) - 1 sort_order,
  c.summary_variant_id,
  c.profile_id,
  c.profile_variant_id
FROM
  resume_compositions c
WHERE
  c.is_starter
  AND c.archived_at IS NULL;

INSERT INTO default_sets (id, user_id, name, description, is_default, sort_order)
SELECT set_id, user_id, name, COALESCE(description, ''), is_default_starter, sort_order
FROM starter_sets;

INSERT INTO default_set_members (set_id, item_type, item_id, variant_id, sort_order)
SELECT
  s.set_id,
  CASE i.section
    WHEN 'education' THEN 'education_item'
    WHEN 'tool_groups' THEN 'tool_group'
    WHEN 'personal_interests' THEN 'interest'
    ELSE 'content_item'
  END,
  i.item_id,
  CASE WHEN i.section IN ('education', 'projects', 'work_experience', 'leadership') THEN i.variant_id END,
  i.sort_order
FROM
  starter_sets s
  JOIN composition_items i ON i.composition_id = s.composition_id
ON CONFLICT DO NOTHING;

INSERT INTO default_set_members (set_id, item_type, item_id, variant_id, sort_order)
SELECT s.set_id, 'custom_section', x.section_id, NULL, x.sort_order
FROM starter_sets s JOIN composition_custom_sections x ON x.composition_id = s.composition_id
ON CONFLICT DO NOTHING;

INSERT INTO default_set_members (set_id, item_type, item_id, variant_id, sort_order)
SELECT s.set_id, 'bullet', b.bullet_id, b.variant_id, b.sort_order
FROM starter_sets s JOIN composition_bullets b ON b.composition_id = s.composition_id
ON CONFLICT DO NOTHING;

INSERT INTO default_set_members (set_id, item_type, item_id, variant_id, sort_order)
SELECT set_id, 'summary', summary_variant_id, NULL, 0
FROM starter_sets WHERE summary_variant_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO default_set_members (set_id, item_type, item_id, variant_id, sort_order)
SELECT set_id, 'profile', profile_id, profile_variant_id, 0
FROM starter_sets WHERE profile_id IS NOT NULL
ON CONFLICT DO NOTHING;

UPDATE resume_compositions
SET archived_at = now(), is_default_starter = false, updated_at = now()
WHERE id IN (SELECT composition_id FROM starter_sets);

DROP TABLE starter_sets;

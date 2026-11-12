-- Skill groups and interests get variants, like entries and bullets.
-- A skill group variant has its own label and its own pick and order of the
-- group's tools; an interest variant is another wording. A resume points at
-- the variant it uses through composition_items.variant_id.
CREATE TABLE tool_group_variants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  tool_group_id uuid NOT NULL REFERENCES tool_groups (id),
  name text NOT NULL CHECK (btrim(name) <> ''),
  group_name text NOT NULL CHECK (btrim(group_name) <> ''),
  tool_ids uuid[] NOT NULL DEFAULT '{}',
  is_default boolean NOT NULL DEFAULT false,
  sort_order integer NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tool_group_id, name)
);

CREATE UNIQUE INDEX one_default_tool_group_variant ON tool_group_variants (tool_group_id)
WHERE
  is_default
  AND archived_at IS NULL;

CREATE TABLE interest_variants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  interest_id uuid NOT NULL REFERENCES interests (id),
  name text NOT NULL CHECK (btrim(name) <> ''),
  body text NOT NULL CHECK (btrim(body) <> ''),
  is_default boolean NOT NULL DEFAULT false,
  sort_order integer NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (interest_id, name)
);

CREATE UNIQUE INDEX one_default_interest_variant ON interest_variants (interest_id)
WHERE
  is_default
  AND archived_at IS NULL;

-- Defaults sets may now name a skill group or interest variant.
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
    IF NEW.variant_id IS NOT NULL THEN
      SELECT user_id INTO vu FROM tool_group_variants WHERE id=NEW.variant_id AND tool_group_id=NEW.item_id;
    END IF;
  ELSIF NEW.item_type='interest' THEN
    SELECT user_id INTO iu FROM interests WHERE id=NEW.item_id;
    IF NEW.variant_id IS NOT NULL THEN
      SELECT user_id INTO vu FROM interest_variants WHERE id=NEW.variant_id AND interest_id=NEW.item_id;
    END IF;
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
  IF NEW.item_type IN ('custom_section','summary') AND NEW.variant_id IS NOT NULL THEN
    RAISE EXCEPTION 'record has no variants' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;

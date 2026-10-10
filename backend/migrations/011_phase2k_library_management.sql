-- Phase 2K normalized tags, additive and non-destructive.
CREATE TABLE library_tags (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  display_name text NOT NULL CHECK (btrim(display_name) <> ''),
  normalized_name text NOT NULL CHECK (btrim(normalized_name) <> ''),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, normalized_name)
);

CREATE TABLE library_bullet_tags (
  bullet_id uuid NOT NULL REFERENCES bullets (id),
  tag_id uuid NOT NULL REFERENCES library_tags (id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (bullet_id, tag_id)
);

CREATE INDEX library_tags_user_search ON library_tags (user_id, normalized_name, id);

CREATE INDEX library_bullet_tags_tag_lookup ON library_bullet_tags (tag_id, bullet_id);

CREATE INDEX library_bullet_tags_bullet_lookup ON library_bullet_tags (bullet_id, tag_id);

CREATE OR REPLACE FUNCTION enforce_library_bullet_tag_ownership () RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE bu uuid;tu uuid;BEGIN SELECT user_id INTO bu FROM bullets WHERE id=NEW.bullet_id;SELECT user_id INTO tu FROM library_tags WHERE id=NEW.tag_id;IF bu IS NULL OR tu IS NULL OR bu<>tu THEN RAISE EXCEPTION 'library tag ownership mismatch' USING ERRCODE='23503';END IF;RETURN NEW;END $$;

CREATE TRIGGER library_bullet_tags_owner_guard
BEFORE INSERT OR UPDATE ON library_bullet_tags FOR EACH ROW
EXECUTE FUNCTION enforce_library_bullet_tag_ownership ();

WITH
  vals AS (
    SELECT
      ci.user_id,
      b.id bullet_id,
      btrim(x) display_name,
      lower(btrim(x)) normalized_name
    FROM
      content_items ci
      JOIN bullets b ON b.parent_id = ci.id
      AND b.user_id = ci.user_id
      CROSS JOIN LATERAL unnest(ci.tags) x
    WHERE
      btrim(x) <> ''
  ),
  chosen AS (
    SELECT DISTINCT
      ON (user_id, normalized_name) user_id,
      normalized_name,
      display_name
    FROM
      vals
    ORDER BY
      user_id,
      normalized_name,
      display_name COLLATE "C"
  )
INSERT INTO
  library_tags (user_id, normalized_name, display_name)
SELECT
  user_id,
  normalized_name,
  display_name
FROM
  chosen
ON CONFLICT (user_id, normalized_name) DO NOTHING;

WITH
  vals AS (
    SELECT
      ci.user_id,
      b.id bullet_id,
      lower(btrim(x)) normalized_name
    FROM
      content_items ci
      JOIN bullets b ON b.parent_id = ci.id
      AND b.user_id = ci.user_id
      CROSS JOIN LATERAL unnest(ci.tags) x
    WHERE
      btrim(x) <> ''
  )
INSERT INTO
  library_bullet_tags (bullet_id, tag_id)
SELECT DISTINCT
  v.bullet_id,
  t.id
FROM
  vals v
  JOIN library_tags t ON t.user_id = v.user_id
  AND t.normalized_name = v.normalized_name
ON CONFLICT DO NOTHING;

-- Copy a non-empty display title into the resume name when the stored name is
-- still a generated default. The display_title column stays in place.
DO $$
DECLARE
  rec record;
  base_title text;
  candidate text;
  suffix integer;
  taken boolean;
  new_revision integer;
BEGIN
  FOR rec IN
    SELECT id, user_id, name, btrim(display_title) AS title
    FROM resume_compositions
    WHERE btrim(display_title) <> ''
      AND name ~ '^.*''s Resume [(][0-9]{2}/[0-9]{2}/[0-9]{4}[)]( [(][0-9]+[)])?$'
    ORDER BY user_id, created_at, id
  LOOP
    base_title := left(rec.title, 120);
    candidate := base_title;
    suffix := 2;
    LOOP
      SELECT EXISTS (
        SELECT 1
        FROM resume_compositions
        WHERE user_id = rec.user_id
          AND name = candidate
          AND id <> rec.id
      ) INTO taken;
      EXIT WHEN NOT taken;
      candidate := left(base_title, 120 - char_length(' (' || suffix::text || ')'))
        || ' (' || suffix::text || ')';
      suffix := suffix + 1;
      IF suffix > 10000 THEN
        RAISE EXCEPTION 'could not assign a unique resume name for %', rec.id;
      END IF;
    END LOOP;
    IF candidate IS DISTINCT FROM rec.name THEN
      UPDATE resume_compositions
      SET
        name = candidate,
        revision = revision + 1,
        updated_at = now()
      WHERE id = rec.id
      RETURNING revision INTO new_revision;
      INSERT INTO composition_revisions (composition_id, user_id, revision, source, snapshot)
      VALUES (rec.id, rec.user_id, new_revision, 'metadata', '{}'::jsonb);
    END IF;
  END LOOP;
END $$;

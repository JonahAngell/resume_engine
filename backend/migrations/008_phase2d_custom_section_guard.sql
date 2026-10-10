-- Correct the Phase 2 ownership function for composition_custom_sections,
-- which intentionally has no user_id column.
CREATE OR REPLACE FUNCTION enforce_phase2_ownership () RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  expected uuid;
BEGIN
  IF TG_TABLE_NAME = 'custom_section_entries' THEN
    SELECT user_id
    INTO expected
    FROM custom_sections
    WHERE id = NEW.section_id;

    IF expected IS NULL OR expected <> NEW.user_id THEN
      RAISE EXCEPTION 'ownership mismatch'
        USING ERRCODE = '23503';
    END IF;

  ELSIF TG_TABLE_NAME = 'composition_custom_sections' THEN
    SELECT composition.user_id
    INTO expected
    FROM resume_compositions composition
    JOIN custom_sections section
      ON section.id = NEW.section_id
     AND section.user_id = composition.user_id
    WHERE composition.id = NEW.composition_id;

    IF expected IS NULL THEN
      RAISE EXCEPTION 'ownership mismatch'
        USING ERRCODE = '23503';
    END IF;

  ELSIF TG_TABLE_NAME = 'composition_revisions' THEN
    SELECT user_id
    INTO expected
    FROM resume_compositions
    WHERE id = NEW.composition_id;

    IF expected IS NULL OR expected <> NEW.user_id THEN
      RAISE EXCEPTION 'ownership mismatch'
        USING ERRCODE = '23503';
    END IF;

  ELSE
    RAISE EXCEPTION 'unsupported ownership trigger table'
      USING ERRCODE = '23503';
  END IF;

  RETURN NEW;
END;
$$;

-- AI provenance on bullet wording. ai_generated means the body is still the
-- model's text unchanged. Model and job stay as history after an edit.
ALTER TABLE bullet_variants
ADD COLUMN ai_generated boolean NOT NULL DEFAULT false,
ADD COLUMN ai_model text,
ADD COLUMN ai_job_id uuid REFERENCES job_descriptions (id) ON DELETE SET NULL;

-- A body change clears the flag unless the same statement sets it on purpose.
-- Renames do not touch body, so they keep it.
CREATE OR REPLACE FUNCTION clear_ai_generated_on_body_change () RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.body IS DISTINCT FROM OLD.body AND NEW.ai_generated IS NOT DISTINCT FROM OLD.ai_generated THEN
    NEW.ai_generated := false;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER bullet_variants_clear_ai_generated BEFORE
UPDATE OF body ON bullet_variants FOR EACH ROW
EXECUTE FUNCTION clear_ai_generated_on_body_change ();

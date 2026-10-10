-- Phase 2G: additive resume metadata and revision-snapshot enrichment.
ALTER TABLE resume_compositions
ADD COLUMN display_title text NOT NULL DEFAULT '',
ADD COLUMN target_company text NOT NULL DEFAULT '',
ADD COLUMN target_role text NOT NULL DEFAULT '';

ALTER TABLE resume_compositions
ADD CONSTRAINT resume_compositions_display_title_length CHECK (length(display_title) <= 200),
ADD CONSTRAINT resume_compositions_target_company_length CHECK (length(target_company) <= 200),
ADD CONSTRAINT resume_compositions_target_role_length CHECK (length(target_role) <= 200);

UPDATE composition_revisions revision
SET
  snapshot = revision.snapshot || jsonb_build_object(
    'name',
    COALESCE(revision.snapshot ->> 'name', composition.name),
    'description',
    COALESCE(
      revision.snapshot ->> 'description',
      composition.description
    ),
    'display_title',
    COALESCE(
      revision.snapshot ->> 'display_title',
      composition.display_title
    ),
    'target_company',
    COALESCE(
      revision.snapshot ->> 'target_company',
      composition.target_company
    ),
    'target_role',
    COALESCE(
      revision.snapshot ->> 'target_role',
      composition.target_role
    )
  )
FROM
  resume_compositions composition
WHERE
  composition.id = revision.composition_id;

CREATE OR REPLACE FUNCTION enrich_composition_revision_snapshot () RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  composition resume_compositions%ROWTYPE;
BEGIN
  SELECT * INTO composition FROM resume_compositions WHERE id = NEW.composition_id;
  IF composition.id IS NULL OR composition.user_id <> NEW.user_id THEN
    RAISE EXCEPTION 'ownership mismatch' USING ERRCODE='23503';
  END IF;
  NEW.snapshot = COALESCE(NEW.snapshot, '{}'::jsonb) || jsonb_build_object(
    'name', composition.name,
    'description', composition.description,
    'display_title', composition.display_title,
    'target_company', composition.target_company,
    'target_role', composition.target_role
  );
  RETURN NEW;
END;
$$;

CREATE TRIGGER composition_revision_metadata_snapshot
BEFORE INSERT OR UPDATE ON composition_revisions FOR EACH ROW
EXECUTE FUNCTION enrich_composition_revision_snapshot ();

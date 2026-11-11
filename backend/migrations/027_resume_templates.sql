-- Custom resume templates. A template starts from a built-in style (base_style) and stores
-- the user's appearance settings. Resumes link to one; editing it changes every linked resume.
CREATE TABLE resume_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  name text NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 80),
  base_style text NOT NULL CHECK (base_style IN ('classic', 'sheets', 'harvard', 'dais', 'sre')),
  settings jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(settings) = 'object'),
  revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, user_id)
);

CREATE UNIQUE INDEX resume_template_names ON resume_templates (user_id, lower(name));

-- template_id: the linked custom template, owned by the same user (composite key).
-- tools_layout: this resume's choice for the Tools section; NULL follows the template.
ALTER TABLE resume_compositions
ADD COLUMN template_id uuid,
ADD COLUMN tools_layout text CHECK (tools_layout IN ('table', 'inline')),
ADD CONSTRAINT resume_compositions_template_owner FOREIGN KEY (template_id, user_id) REFERENCES resume_templates (id, user_id) ON DELETE SET NULL (template_id);

CREATE INDEX resume_compositions_template ON resume_compositions (template_id)
WHERE
  template_id IS NOT NULL;

-- Revisions record the linked template and its settings at that moment, so history shows
-- what the resume looked like even after the template changes.
CREATE OR REPLACE FUNCTION enrich_composition_revision_snapshot () RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c resume_compositions%ROWTYPE; t resume_templates%ROWTYPE;
BEGIN
 SELECT * INTO c FROM resume_compositions WHERE id=NEW.composition_id;
 IF c.id IS NULL OR c.user_id<>NEW.user_id THEN RAISE EXCEPTION 'ownership mismatch' USING ERRCODE='23503'; END IF;
 IF c.template_id IS NOT NULL THEN SELECT * INTO t FROM resume_templates WHERE id=c.template_id; END IF;
 NEW.snapshot=COALESCE(NEW.snapshot,'{}'::jsonb)||jsonb_build_object('name',c.name,'description',c.description,'display_title',c.display_title,'target_company',c.target_company,'target_role',c.target_role,'preferred_page_length',c.preferred_page_length,'date_format',c.date_format,'template_style',c.template_style,'skill_row_max',c.skill_row_max,'template_id',c.template_id,'tools_layout',c.tools_layout,'template_name',t.name,'template_settings',t.settings,'section_sort_modes',c.section_sort_modes,'bullet_placements',COALESCE((SELECT jsonb_agg(to_jsonb(cb) ORDER BY cb.destination_section,cb.destination_parent_id,cb.sort_order,cb.id) FROM composition_bullets cb WHERE cb.composition_id=NEW.composition_id),'[]'::jsonb));
 RETURN NEW;
END $$;

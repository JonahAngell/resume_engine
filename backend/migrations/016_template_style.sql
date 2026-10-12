-- Per-resume visual template. Existing resumes stay on the current layout.
ALTER TABLE resume_compositions
ADD COLUMN template_style text NOT NULL DEFAULT 'classic' CHECK (
  template_style IN ('classic', 'sheets', 'harvard', 'dais', 'sre')
);

CREATE OR REPLACE FUNCTION enrich_composition_revision_snapshot () RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c resume_compositions%ROWTYPE;
BEGIN
 SELECT * INTO c FROM resume_compositions WHERE id=NEW.composition_id;
 IF c.id IS NULL OR c.user_id<>NEW.user_id THEN RAISE EXCEPTION 'ownership mismatch' USING ERRCODE='23503'; END IF;
 NEW.snapshot=COALESCE(NEW.snapshot,'{}'::jsonb)||jsonb_build_object('name',c.name,'description',c.description,'display_title',c.display_title,'target_company',c.target_company,'target_role',c.target_role,'preferred_page_length',c.preferred_page_length,'date_format',c.date_format,'template_style',c.template_style,'section_sort_modes',c.section_sort_modes,'bullet_placements',COALESCE((SELECT jsonb_agg(to_jsonb(cb) ORDER BY cb.destination_section,cb.destination_parent_id,cb.sort_order,cb.id) FROM composition_bullets cb WHERE cb.composition_id=NEW.composition_id),'[]'::jsonb));
 RETURN NEW;
END $$;

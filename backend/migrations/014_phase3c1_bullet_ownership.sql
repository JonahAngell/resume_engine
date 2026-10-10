-- Phase 3c.1 additive bullet ownership expansion.
ALTER TABLE bullets
ADD COLUMN IF NOT EXISTS education_item_id uuid REFERENCES education_items (id),
ADD COLUMN IF NOT EXISTS tool_group_id uuid REFERENCES tool_groups (id),
ADD COLUMN IF NOT EXISTS interest_id uuid REFERENCES interests (id),
ADD COLUMN IF NOT EXISTS custom_entry_id uuid REFERENCES custom_section_entries (id),
ADD COLUMN IF NOT EXISTS parent_type text GENERATED ALWAYS AS (
  CASE
    WHEN parent_id IS NOT NULL THEN 'content_item'
    WHEN education_item_id IS NOT NULL THEN 'education_item'
    WHEN tool_group_id IS NOT NULL THEN 'tool_group'
    WHEN interest_id IS NOT NULL THEN 'interest'
    WHEN custom_entry_id IS NOT NULL THEN 'custom_entry'
    ELSE ''
  END
) STORED;

ALTER TABLE bullets
ADD CONSTRAINT bullets_at_most_one_parent CHECK (
  num_nonnulls (
    parent_id,
    education_item_id,
    tool_group_id,
    interest_id,
    custom_entry_id
  ) <= 1
);

CREATE INDEX bullets_education_order ON bullets (education_item_id, sort_order);

CREATE INDEX bullets_tool_group_order ON bullets (tool_group_id, sort_order);

CREATE INDEX bullets_interest_order ON bullets (interest_id, sort_order);

CREATE INDEX bullets_custom_entry_order ON bullets (custom_entry_id, sort_order);

CREATE OR REPLACE FUNCTION phase3c1_parent_label (u uuid, t text, p uuid) RETURNS text LANGUAGE plpgsql STABLE AS $$ DECLARE r text; BEGIN IF t='content_item' THEN SELECT CASE WHEN kind='project' THEN name ELSE concat_ws(' – ',organization,title) END INTO r FROM content_items WHERE id=p AND user_id=u; ELSIF t='education_item' THEN SELECT institution INTO r FROM education_items WHERE id=p AND user_id=u; ELSIF t='tool_group' THEN SELECT name INTO r FROM tool_groups WHERE id=p AND user_id=u; ELSIF t='interest' THEN SELECT body INTO r FROM interests WHERE id=p AND user_id=u; ELSIF t='custom_entry' THEN SELECT primary_text INTO r FROM custom_section_entries WHERE id=p AND user_id=u; END IF; RETURN r; END $$;

CREATE OR REPLACE FUNCTION enforce_matching_user_ownership () RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE expected_user uuid; BEGIN IF TG_TABLE_NAME='tools' THEN SELECT user_id INTO expected_user FROM tool_groups WHERE id=NEW.group_id; ELSIF TG_TABLE_NAME='bullets' THEN SELECT user_id INTO expected_user FROM content_items WHERE id=NEW.parent_id UNION ALL SELECT user_id FROM education_items WHERE id=NEW.education_item_id UNION ALL SELECT user_id FROM tool_groups WHERE id=NEW.tool_group_id UNION ALL SELECT user_id FROM interests WHERE id=NEW.interest_id UNION ALL SELECT user_id FROM custom_section_entries WHERE id=NEW.custom_entry_id LIMIT 1; expected_user:=COALESCE(expected_user,NEW.user_id); ELSIF TG_TABLE_NAME='bullet_variants' THEN SELECT user_id INTO expected_user FROM bullets WHERE id=NEW.bullet_id; ELSIF TG_TABLE_NAME='seed_imports' THEN SELECT user_id INTO expected_user FROM resume_compositions WHERE id=NEW.composition_id; END IF; IF expected_user IS NULL OR expected_user<>NEW.user_id THEN RAISE EXCEPTION 'ownership mismatch' USING ERRCODE='23503'; END IF; RETURN NEW; END $$;

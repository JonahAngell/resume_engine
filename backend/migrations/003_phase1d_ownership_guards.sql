CREATE OR REPLACE FUNCTION enforce_matching_user_ownership () RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_user uuid;
BEGIN
  IF TG_TABLE_NAME = 'tools' THEN SELECT user_id INTO expected_user FROM tool_groups WHERE id=NEW.group_id;
  ELSIF TG_TABLE_NAME = 'bullets' THEN SELECT user_id INTO expected_user FROM content_items WHERE id=NEW.parent_id;
  ELSIF TG_TABLE_NAME = 'bullet_variants' THEN SELECT user_id INTO expected_user FROM bullets WHERE id=NEW.bullet_id;
  ELSIF TG_TABLE_NAME = 'seed_imports' THEN SELECT user_id INTO expected_user FROM resume_compositions WHERE id=NEW.composition_id;
  END IF;
  IF expected_user IS NULL OR expected_user <> NEW.user_id THEN RAISE EXCEPTION 'ownership mismatch' USING ERRCODE='23503'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER tools_owner_guard
BEFORE INSERT OR UPDATE ON tools FOR EACH ROW
EXECUTE FUNCTION enforce_matching_user_ownership ();

CREATE TRIGGER bullets_owner_guard
BEFORE INSERT OR UPDATE ON bullets FOR EACH ROW
EXECUTE FUNCTION enforce_matching_user_ownership ();

CREATE TRIGGER bullet_variants_owner_guard
BEFORE INSERT OR UPDATE ON bullet_variants FOR EACH ROW
EXECUTE FUNCTION enforce_matching_user_ownership ();

CREATE TRIGGER seed_imports_owner_guard
BEFORE INSERT OR UPDATE ON seed_imports FOR EACH ROW
EXECUTE FUNCTION enforce_matching_user_ownership ();

CREATE OR REPLACE FUNCTION enforce_composition_selection_ownership () RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE composition_user uuid; selected_user uuid; bullet_user uuid;
BEGIN
  SELECT user_id INTO composition_user FROM resume_compositions WHERE id=NEW.composition_id;
  IF TG_TABLE_NAME = 'composition_items' THEN
    IF NEW.section='education' THEN SELECT user_id INTO selected_user FROM education_items WHERE id=NEW.item_id;
    ELSIF NEW.section='tool_groups' THEN SELECT user_id INTO selected_user FROM tool_groups WHERE id=NEW.item_id;
    ELSIF NEW.section IN ('projects','work_experience','leadership') THEN SELECT user_id INTO selected_user FROM content_items WHERE id=NEW.item_id;
    ELSIF NEW.section='personal_interests' THEN SELECT user_id INTO selected_user FROM interests WHERE id=NEW.item_id;
    END IF;
  ELSE
    SELECT user_id INTO selected_user FROM bullet_variants WHERE id=NEW.variant_id AND bullet_id=NEW.bullet_id;
    SELECT user_id INTO bullet_user FROM bullets WHERE id=NEW.bullet_id;
    IF bullet_user IS DISTINCT FROM selected_user THEN RAISE EXCEPTION 'bullet variant ownership mismatch' USING ERRCODE='23503'; END IF;
  END IF;
  IF composition_user IS NULL OR selected_user IS NULL OR composition_user <> selected_user THEN RAISE EXCEPTION 'composition ownership mismatch' USING ERRCODE='23503'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER composition_items_owner_guard
BEFORE INSERT OR UPDATE ON composition_items FOR EACH ROW
EXECUTE FUNCTION enforce_composition_selection_ownership ();

CREATE TRIGGER composition_bullets_owner_guard
BEFORE INSERT OR UPDATE ON composition_bullets FOR EACH ROW
EXECUTE FUNCTION enforce_composition_selection_ownership ();

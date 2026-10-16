-- Named resume variants are starter compositions. Field variants let one
-- resume change an entry or profile without rewriting the shared library record.
ALTER TABLE resume_compositions
ADD COLUMN is_starter boolean NOT NULL DEFAULT false,
ADD COLUMN is_default_starter boolean NOT NULL DEFAULT false,
ADD COLUMN profile_variant_id uuid;

CREATE UNIQUE INDEX one_default_resume_variant ON resume_compositions (user_id)
WHERE
  is_default_starter
  AND archived_at IS NULL;

ALTER TABLE composition_items
ADD COLUMN variant_id uuid;

CREATE TABLE content_item_variants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  content_item_id uuid NOT NULL REFERENCES content_items (id),
  name text NOT NULL,
  item_name text,
  subtitle text,
  organization text,
  location text,
  title text,
  date_label text NOT NULL DEFAULT '',
  start_year integer,
  start_month integer CHECK (start_month BETWEEN 1 AND 12),
  end_year integer,
  end_month integer CHECK (end_month BETWEEN 1 AND 12),
  is_current boolean NOT NULL DEFAULT false,
  is_default boolean NOT NULL DEFAULT false,
  sort_order integer NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (content_item_id, name)
);

CREATE TABLE education_item_variants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  education_item_id uuid NOT NULL REFERENCES education_items (id),
  name text NOT NULL,
  institution text NOT NULL,
  college_school text,
  location text NOT NULL DEFAULT '',
  degree_type text,
  degree_major text,
  degree text NOT NULL DEFAULT '',
  graduation_year integer,
  graduation_month integer CHECK (graduation_month BETWEEN 1 AND 12),
  display_date text,
  graduation_date text NOT NULL DEFAULT '',
  is_default boolean NOT NULL DEFAULT false,
  sort_order integer NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (education_item_id, name)
);

CREATE TABLE profile_field_variants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  profile_id uuid NOT NULL REFERENCES profiles (id),
  name text NOT NULL,
  display_name text NOT NULL,
  phone text NOT NULL DEFAULT '',
  email text NOT NULL DEFAULT '',
  linkedin_label text NOT NULL DEFAULT '',
  linkedin_url text NOT NULL DEFAULT '',
  is_default boolean NOT NULL DEFAULT false,
  sort_order integer NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (profile_id, name)
);

ALTER TABLE resume_compositions
ADD CONSTRAINT resume_compositions_profile_variant_fkey FOREIGN KEY (profile_variant_id) REFERENCES profile_field_variants (id);

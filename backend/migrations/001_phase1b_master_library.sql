CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE app_users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id text NOT NULL UNIQUE,
  username text NOT NULL,
  display_name text NOT NULL,
  email text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL UNIQUE REFERENCES app_users (id),
  name text NOT NULL,
  phone text NOT NULL,
  email text NOT NULL,
  linkedin_label text NOT NULL,
  linkedin_url text NOT NULL,
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE summary_variants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  name text NOT NULL,
  body text NOT NULL,
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, name)
);

CREATE TABLE education_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  institution text NOT NULL,
  location text NOT NULL,
  degree text NOT NULL,
  graduation_date text NOT NULL,
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tool_groups (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  name text NOT NULL,
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, name)
);

CREATE TABLE tools (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  group_id uuid NOT NULL REFERENCES tool_groups (id),
  name text NOT NULL,
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (group_id, name)
);

CREATE TABLE content_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  kind text NOT NULL CHECK (kind IN ('project', 'employment', 'leadership')),
  name text,
  subtitle text,
  organization text,
  location text,
  title text,
  date_label text NOT NULL,
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (
    (
      kind = 'project'
      AND name IS NOT NULL
    )
    OR (
      kind <> 'project'
      AND organization IS NOT NULL
      AND title IS NOT NULL
    )
  )
);

CREATE TABLE bullets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  parent_id uuid NOT NULL REFERENCES content_items (id),
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE bullet_variants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  bullet_id uuid NOT NULL REFERENCES bullets (id),
  name text NOT NULL,
  body text NOT NULL,
  is_default boolean NOT NULL DEFAULT FALSE,
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (bullet_id, name)
);

CREATE UNIQUE INDEX one_default_variant_per_bullet ON bullet_variants (bullet_id)
WHERE
  is_default
  AND archived_at IS NULL;

CREATE TABLE interests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  body text NOT NULL,
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE resume_compositions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  name text NOT NULL,
  summary_variant_id uuid REFERENCES summary_variants (id),
  render_payload jsonb NOT NULL,
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, name)
);

CREATE TABLE composition_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  composition_id uuid NOT NULL REFERENCES resume_compositions (id),
  section text NOT NULL,
  item_id uuid NOT NULL,
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  UNIQUE (composition_id, section, item_id)
);

CREATE TABLE composition_bullets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  composition_id uuid NOT NULL REFERENCES resume_compositions (id),
  bullet_id uuid NOT NULL REFERENCES bullets (id),
  variant_id uuid NOT NULL REFERENCES bullet_variants (id),
  sort_order integer NOT NULL CHECK (sort_order >= 0),
  UNIQUE (composition_id, bullet_id)
);

CREATE TABLE seed_imports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  seed_key text NOT NULL,
  seed_sha256 text NOT NULL CHECK (length(seed_sha256) = 64),
  composition_id uuid NOT NULL REFERENCES resume_compositions (id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, seed_key)
);

CREATE INDEX content_items_user_kind_order ON content_items (user_id, kind, sort_order);

CREATE INDEX bullets_parent_order ON bullets (parent_id, sort_order);

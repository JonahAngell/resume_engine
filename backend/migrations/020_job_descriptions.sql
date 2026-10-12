-- Saved job descriptions for keyword comparison against an owned resume.
CREATE TABLE job_descriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users (id),
  company text NOT NULL DEFAULT '',
  role text NOT NULL DEFAULT '',
  title text NOT NULL,
  body text NOT NULL,
  composition_id uuid REFERENCES resume_compositions (id) ON DELETE SET NULL,
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT job_descriptions_company_length CHECK (length(company) <= 200),
  CONSTRAINT job_descriptions_role_length CHECK (length(role) <= 200),
  CONSTRAINT job_descriptions_title_length CHECK (length(title) BETWEEN 1 AND 300),
  CONSTRAINT job_descriptions_body_length CHECK (length(body) BETWEEN 1 AND 50000)
);

CREATE INDEX job_descriptions_user_updated
  ON job_descriptions (user_id, updated_at DESC, id);

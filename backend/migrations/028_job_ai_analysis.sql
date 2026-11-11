-- The AI reading of a job posting, saved when the user asks for it. It records the hash of the
-- posting text it read, so an edited posting no longer uses it.
ALTER TABLE job_descriptions
  ADD COLUMN ai_analysis jsonb;

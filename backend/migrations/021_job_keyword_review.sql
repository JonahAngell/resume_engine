-- Remember which qualification rows the user dismissed or added on a job description.
ALTER TABLE job_descriptions
  ADD COLUMN keyword_review jsonb NOT NULL DEFAULT '{}'::jsonb;

-- Link a resume to one saved job description. Company and role stay on the resume
-- so Home and search keep working; they are copied from the job when the link is set.
ALTER TABLE resume_compositions
  ADD COLUMN job_description_id uuid REFERENCES job_descriptions (id) ON DELETE SET NULL;

UPDATE resume_compositions AS composition
SET job_description_id = matched.job_id
FROM (
  SELECT composition.id AS composition_id, min(job.id::text)::uuid AS job_id
  FROM resume_compositions AS composition
  JOIN job_descriptions AS job
    ON job.user_id = composition.user_id
   AND job.archived_at IS NULL
   AND lower(btrim(job.company)) = lower(btrim(composition.target_company))
   AND lower(btrim(job.role)) = lower(btrim(composition.target_role))
  WHERE btrim(composition.target_company) <> ''
    AND btrim(composition.target_role) <> ''
  GROUP BY composition.id
  HAVING count(*) = 1
) AS matched
WHERE composition.id = matched.composition_id;

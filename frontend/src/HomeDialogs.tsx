import React, { useEffect, useState } from "react";
import { api } from "./api";
import ChoiceList from "./ChoiceList";
import ModalShell from "./ModalShell";

type JobOption = {
  id: string;
  company: string;
  role: string;
  title: string;
};

export function JobTargetField({
  jobId,
  company,
  role,
  onChange,
}: {
  jobId: string;
  company: string;
  role: string;
  onChange: (jobId: string) => void;
}) {
  const [jobs, setJobs] = useState<JobOption[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    api<JobOption[]>("/api/job-descriptions")
      .then((rows) => {
        if (!cancelled) setJobs(rows);
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const selected = jobs.find((job) => job.id === jobId) || null;
  const linked = Boolean(selected);
  const shownCompany = selected ? selected.company : company;
  const shownRole = selected ? selected.role : role;
  const unavailable = loaded && Boolean(jobId) && !selected;
  return (
    <div className="job-target-field">
      <div className="choice-field">
        <span>Job description</span>
        {!loaded ? (
          <p>Loading…</p>
        ) : (
          <ChoiceList
            label="Job description"
            search="always"
            value={jobId}
            empty="Nothing to choose."
            noMatch="No matching job descriptions."
            options={[
              { value: "", label: "None" },
              ...jobs.map((job) => ({ value: job.id, label: job.title })),
            ]}
            onChange={onChange}
          />
        )}
      </div>
      {error && <div role="alert">{error}</div>}
      {loaded && jobs.length === 0 && (
        <p>Save a job description on the Jobs page, then choose it here.</p>
      )}
      {unavailable && (
        <p>The linked job description is no longer available.</p>
      )}
      <dl className="target-facts">
        <div>
          <dt>Target company</dt>
          <dd>{shownCompany || "—"}</dd>
        </div>
        <div>
          <dt>Target role</dt>
          <dd>{shownRole || "—"}</dd>
        </div>
      </dl>
      {!linked && (shownCompany || shownRole) && !unavailable && (
        <small>Not linked to a saved job.</small>
      )}
      <small>
        Target company and target role are planning metadata and are not
        printed on the resume.
      </small>
    </div>
  );
}

export function RenameResumeDialog({ item, close, save }: any) {
  const [name, setName] = useState(item.name),
    [error, setError] = useState("");
  return (
    <ModalShell title="Rename resume" close={close}>
      <label>
        Resume Name
        <input
          value={name}
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      {error && <div role="alert">{error}</div>}
      <div className="form-actions">
        <button onClick={close}>Cancel</button>
        <button
          className="primary"
          onClick={() =>
            name.trim()
              ? save(
                  {
                    revision: item.revision,
                    name: name.trim(),
                    description: item.description || "",
                    display_title: item.display_title || "",
                    target_company: item.target_company || "",
                    target_role: item.target_role || "",
                  },
                  setError,
                )
              : setError("Resume name is required.")
          }
        >
          Save
        </button>
      </div>
    </ModalShell>
  );
}
export function EditDetailsDialog({ item, close, save }: any) {
  const [jobId, setJobId] = useState(item.job_description_id || ""),
    [error, setError] = useState("");
  return (
    <ModalShell title="Edit details" close={close}>
      <JobTargetField
        jobId={jobId}
        company={item.target_company || ""}
        role={item.target_role || ""}
        onChange={setJobId}
      />
      {error && <div role="alert">{error}</div>}
      <div className="form-actions">
        <button onClick={close}>Cancel</button>
        <button
          className="primary"
          onClick={() =>
            item.name.trim()
              ? save(
                  {
                    ...item,
                    job_description_id: jobId || null,
                  },
                  setError,
                )
              : setError("Resume name is required.")
          }
        >
          Save
        </button>
      </div>
    </ModalShell>
  );
}

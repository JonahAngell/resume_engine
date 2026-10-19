import React, { useEffect, useState } from "react";
import { api } from "./api";
import ChoiceList from "./ChoiceList";
import ModalShell from "./ModalShell";
import JobDescriptionFields, { emptyJobDraft } from "./JobDescriptionFields";

type DefaultSet = {
  id: string;
  name: string;
  description?: string;
  is_default: boolean;
  entry_count: number;
  bullet_count: number;
};
type JobOption = { id: string; title: string; company: string; role: string };

export type RecommendResult = {
  status: "ok" | "unavailable" | "rate_limited" | "invalid";
  detail: string;
  method: "ai" | "keywords";
  model: string;
  entry_count: number;
  bullet_count: number;
  entries: { section: string; label: string; bullets: number; reason: string }[];
  composition: any;
};

const ENTIRE_LIBRARY = "__entire__";

export default function NewResumeDialog({
  sets,
  close,
  createFromSet,
  createFromAi,
  manageSets,
}: {
  sets: DefaultSet[];
  close: () => void;
  createFromSet: (setId: string | null) => Promise<void>;
  createFromAi: (result: RecommendResult) => Promise<void>;
  manageSets: () => void;
}) {
  const [mode, setMode] = useState<"choose" | "defaults" | "ai">("choose");
  const title =
    mode === "defaults"
      ? "New from Defaults"
      : mode === "ai"
        ? "New from AI Recommendation"
        : "New Resume";
  return (
    <ModalShell title={title} close={close} className="new-resume-dialog">
      {mode === "choose" && (
        <div className="new-resume-choices">
          <button type="button" onClick={() => setMode("defaults")}>
            <strong>New from Defaults</strong>
            <span>Start from a defaults set you manage in the Library.</span>
          </button>
          <button type="button" onClick={() => setMode("ai")}>
            <strong>New from AI Recommendation</strong>
            <span>
              Pick a job description. AI reviews your whole library and builds
              a one-page resume from the most relevant entries and wording.
            </span>
          </button>
        </div>
      )}
      {mode === "defaults" && (
        <DefaultsStep
          sets={sets}
          back={() => setMode("choose")}
          create={createFromSet}
          manageSets={manageSets}
        />
      )}
      {mode === "ai" && (
        <AiStep back={() => setMode("choose")} create={createFromAi} />
      )}
    </ModalShell>
  );
}

function DefaultsStep({
  sets,
  back,
  create,
  manageSets,
}: {
  sets: DefaultSet[];
  back: () => void;
  create: (setId: string | null) => Promise<void>;
  manageSets: () => void;
}) {
  const [choice, setChoice] = useState(
    sets.find((set) => set.is_default)?.id || sets[0]?.id || ENTIRE_LIBRARY,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const counts = (set: DefaultSet) =>
    `${set.entry_count} ${set.entry_count === 1 ? "record" : "records"}, ${set.bullet_count} ${set.bullet_count === 1 ? "bullet" : "bullets"}`;
  return (
    <>
      <p>
        Choose which defaults set this resume starts from. Each set uses the
        records and wording you assigned to it in the Library.
      </p>
      <ChoiceList
        label="Defaults set"
        value={choice}
        options={[
          ...sets.map((set) => ({
            value: set.id,
            label: `${set.name}${set.is_default ? " (default)" : ""} · ${counts(set)}`,
          })),
          { value: ENTIRE_LIBRARY, label: "Entire library · every active record" },
        ]}
        onChange={setChoice}
      />
      {!sets.length && (
        <p className="library-note">
          You have no defaults sets yet. Create one in the Library, or start
          from the entire library.
        </p>
      )}
      <button type="button" className="link-button" onClick={manageSets}>
        Manage defaults sets in the Library
      </button>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="form-actions">
        <button type="button" onClick={back} disabled={busy}>
          Back
        </button>
        <button
          type="button"
          className="primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await create(choice === ENTIRE_LIBRARY ? null : choice);
            } catch (reason: any) {
              setError(reason.message || "Could not create the resume");
              setBusy(false);
            }
          }}
        >
          {busy ? "Creating…" : "Create resume"}
        </button>
      </div>
    </>
  );
}

function AiStep({
  back,
  create,
}: {
  back: () => void;
  create: (result: RecommendResult) => Promise<void>;
}) {
  const [jobs, setJobs] = useState<JobOption[] | null>(null);
  const [jobId, setJobId] = useState("");
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState(emptyJobDraft);
  const [aiAvailable, setAiAvailable] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    api<JobOption[]>("/api/job-descriptions")
      .then((rows) => {
        if (cancelled) return;
        setJobs(rows);
        if (!rows.length) setAdding(true);
      })
      .catch((reason: Error) => !cancelled && setError(reason.message));
    api<{ available: boolean }>("/api/ai/status")
      .then((status) => !cancelled && setAiAvailable(status.available))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  const ready = adding ? Boolean(draft.body.trim()) : Boolean(jobId);
  const generate = async () => {
    setBusy(true);
    setError("");
    try {
      let target = jobId;
      if (adding) {
        const saved = await api<JobOption>("/api/job-descriptions", {
          method: "POST",
          body: JSON.stringify(draft),
        });
        target = saved.id;
        // Keep the saved job if generation fails, so a retry does not duplicate it.
        setJobs((rows) => [saved, ...(rows || [])]);
        setJobId(saved.id);
        setAdding(false);
        setDraft(emptyJobDraft());
      }
      const result = await api<RecommendResult>("/api/compositions/ai-recommend", {
        method: "POST",
        body: JSON.stringify({ job_description_id: target }),
      });
      await create(result);
    } catch (reason: any) {
      setError(reason.message || "Could not build the resume");
      setBusy(false);
    }
  };
  if (busy)
    return (
      <div className="new-resume-progress" role="status" aria-live="polite">
        <span className="spinner" aria-hidden="true" />
        <p>
          <strong>Reviewing your library…</strong>
        </p>
        <p>
          Choosing the entries and wording that best match this job. This can
          take up to a minute.
        </p>
      </div>
    );
  return (
    <>
      {!aiAvailable && (
        <p className="library-note">
          AI is unavailable right now. The resume will be built by matching the
          job's keywords instead.
        </p>
      )}
      {!adding ? (
        <>
          <p>Choose the job this resume is for.</p>
          {jobs === null ? (
            <p>Loading…</p>
          ) : (
            <ChoiceList
              label="Job description"
              search="always"
              value={jobId}
              empty="No saved job descriptions."
              noMatch="No matching job descriptions."
              options={jobs.map((job) => ({ value: job.id, label: job.title }))}
              onChange={setJobId}
            />
          )}
          <button type="button" className="link-button" onClick={() => setAdding(true)}>
            + Add a new job description
          </button>
        </>
      ) : (
        <>
          <p>Paste the job posting. It is saved to your Jobs page.</p>
          <JobDescriptionFields draft={draft} setDraft={setDraft} />
          {!!jobs?.length && (
            <button type="button" className="link-button" onClick={() => setAdding(false)}>
              Choose a saved job description instead
            </button>
          )}
        </>
      )}
      {error && <p role="alert" className="error">{error}</p>}
      <div className="form-actions">
        <button type="button" onClick={back}>
          Back
        </button>
        <button type="button" className="primary" disabled={!ready} onClick={generate}>
          Build resume
        </button>
      </div>
    </>
  );
}

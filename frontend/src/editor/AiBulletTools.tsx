import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import ModalShell from "../ModalShell";
import { linesOver, type Fit } from "../FitIndicator";

/** What the editor's bullet dialogs need to call AI for the selected job. */
export type AiJobContext = {
  compositionId: string;
  revision: number;
  jobs: { id: string; title: string; company: string; role: string }[];
  jobId: string;
  setJobId: (id: string) => void;
  onApplied: (state: any) => Promise<void> | void;
  openReview: () => void;
  /** The preview's latest measurement, for the shrink-to-fit tools. */
  fit?: Fit | null;
  /** Printed lines of one placed bullet, when the preview has measured it. */
  lineCount?: (placement: any) => number | null;
  openShrink?: () => void;
};

/** Characters per bullet line when the preview hasn't measured one. */
export const DEFAULT_LINE_CHARS = 95;

export function charsPerLine(ai?: AiJobContext) {
  const measured = ai?.fit?.charsPerLine || 0;
  return measured >= 30 ? measured : DEFAULT_LINE_CHARS;
}

/** The preview's id for a placed bullet: its parent and its position among that parent's bullets. */
export function placementLineId(placements: any[], placement: any) {
  const parent = String(placement.destination_parent_id);
  const siblings = placements
    .filter((row) => String(row.destination_parent_id) === parent)
    .sort((a, b) => a.sort_order - b.sort_order || String(a.id).localeCompare(String(b.id)));
  const index = siblings.findIndex((row) => String(row.id) === String(placement.id));
  return index < 0 ? "" : `${parent}-bullet-${index}`;
}

export type AiDraft = { name: string; body: string; rationale: string };
type Drafts = {
  status: "ok" | "unavailable" | "rate_limited" | "invalid";
  detail: string;
  model: string;
  drafts: AiDraft[];
};
type Goal = "" | "concise" | "impact" | "align" | "one_line";
const GOALS: [Goal, string][] = [
  ["", "Mixed"],
  ["concise", "Concise"],
  ["impact", "Impact"],
  ["align", "Match the job"],
  ["one_line", "One line"],
];

export type PickCandidate = {
  key: string;
  bullet_id: string;
  variant_id: string;
  name: string;
  body: string;
  current: boolean;
  score: number | null;
  reason: string;
  keyword_hits: string[];
};
export type PickSlot = {
  placement_id: string;
  parent_id: string;
  section: string;
  parent_label: string;
  current_key: string;
  best_key: string;
  recommend: boolean;
  candidates: PickCandidate[];
};
export type VariantPick = {
  status: "ok" | "unavailable" | "rate_limited" | "invalid";
  detail: string;
  model: string;
  method: "ai" | "keywords";
  revision: number;
  slots: PickSlot[];
};

const SECTION_NAMES: Record<string, string> = {
  work_experience: "Work Experience",
  projects: "Projects",
  leadership: "Leadership",
  education: "Education",
};

export function jobLabel(job?: { title: string; company: string; role: string } | null) {
  if (!job) return "";
  return [job.role || job.title, job.company].filter(Boolean).join(" · ");
}

export function conflictMessage(reason: any) {
  return reason instanceof ApiError && reason.status === 409
    ? "This resume changed. Close this window and try again."
    : reason?.message || "Something went wrong";
}

export function JobSelect({ ai, label = "Tailor to job" }: { ai: AiJobContext; label?: string }) {
  if (!ai.jobs.length)
    return (
      <p className="ai-meta">
        Add a job on the <a href="#jobs">Jobs</a> page to get AI suggestions for it.
      </p>
    );
  return (
    <label className="ai-job-select">
      {label}
      <select value={ai.jobId} onChange={(event) => ai.setJobId(event.target.value)}>
        <option value="">Choose a job…</option>
        {ai.jobs.map((job) => (
          <option key={job.id} value={job.id}>
            {jobLabel(job) || "Untitled job"}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Top-of-dialog entry point to the whole-library review. */
export function ReviewBanner({ ai }: { ai: AiJobContext }) {
  const job = ai.jobs.find((item) => item.id === ai.jobId);
  return (
    <div className="ai-review-banner">
      <span className="ai-spark" aria-hidden="true">
        ✦
      </span>
      <div>
        <strong>Tailor every bullet</strong>
        <span>
          Review your whole library and pick the best wording
          {job ? ` for ${jobLabel(job)}` : " for a job"}.
        </span>
      </div>
      <button type="button" onClick={ai.openReview} disabled={!ai.jobs.length}>
        Review library
      </button>
    </div>
  );
}

/** Shown in bullet dialogs while the resume runs past its page target. */
export function ShrinkBanner({ ai }: { ai: AiJobContext }) {
  const over = linesOver(ai.fit || null);
  if (!ai.openShrink || !ai.fit || ai.fit.fits || !over) return null;
  return (
    <div className="ai-review-banner shrink-banner">
      <span className="ai-spark" aria-hidden="true">
        ✦
      </span>
      <div>
        <strong>Over by about {over} line{over === 1 ? "" : "s"}</strong>
        <span>Review the whole resume for bullets to condense and items to remove.</span>
      </div>
      <button type="button" onClick={ai.openShrink}>
        Shrink to fit
      </button>
    </div>
  );
}

/** Line count of the bullet and a live character count against the one-line budget. */
export function LineBudget({ ai, body, lines }: { ai?: AiJobContext; body: string; lines: number | null }) {
  const limit = charsPerLine(ai);
  const length = body.trim().length;
  const fits = length <= limit;
  return (
    <p className={`ai-meta line-budget ${fits ? "fits" : "over"}`} aria-live="polite">
      {lines ? `Currently ${lines} line${lines === 1 ? "" : "s"} on the resume. ` : ""}
      {length} of ~{limit} characters for one line
      {fits ? "." : ` (${length - limit} over).`}
    </p>
  );
}

/** Scores and job keywords for one library wording. */
export function PickBadges({ option, method, best }: { option: PickCandidate; method: string; best?: boolean }) {
  return (
    <span className="pick-badges">
      {best && <span className="pick-badge best">Best match</span>}
      {option.current && <span className="pick-badge">On resume</span>}
      {method === "ai" && option.score !== null && (
        <span className="pick-badge score" title="AI fit score for this job">
          Fit {option.score}
        </span>
      )}
      {option.keyword_hits.length > 0 && (
        <span className="pick-badge keywords" title={option.keyword_hits.join(", ")}>
          {option.keyword_hits.length} job keyword{option.keyword_hits.length === 1 ? "" : "s"}
        </span>
      )}
    </span>
  );
}

/** Ask the model for new wording of one placed bullet. Picking a draft hands it back. */
export function AiDraftPanel({
  ai,
  placementId,
  selected,
  onPick,
}: {
  ai: AiJobContext;
  placementId: string;
  selected?: string;
  onPick: (draft: AiDraft, model: string) => void;
}) {
  const [goal, setGoal] = useState<Goal>("");
  const [result, setResult] = useState<Drafts | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setResult(null);
    setError("");
  }, [ai.jobId, placementId]);
  const run = async (nextGoal: Goal = goal) => {
    // Only the one-line rewrite works without a job.
    if (!ai.jobId && nextGoal !== "one_line") return;
    setGoal(nextGoal);
    setLoading(true);
    setError("");
    try {
      setResult(
        await api<Drafts>(
          `/api/compositions/${ai.compositionId}/bullet-placements/${placementId}/ai-variants`,
          {
            method: "POST",
            body: JSON.stringify({
              job_id: ai.jobId || null,
              goal: nextGoal || null,
              max_chars: nextGoal === "one_line" ? charsPerLine(ai) : null,
            }),
          },
        ),
      );
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setLoading(false);
    }
  };
  return (
    <div className="ai-draft-panel">
      {!result && !loading && (
        <div className="ai-actions">
          <button type="button" className="ai-action" disabled={!ai.jobId} onClick={() => run("")}>
            <span aria-hidden="true">✦</span> Suggest new wording
          </button>
          <button type="button" className="ai-action" onClick={() => run("one_line")}>
            <span aria-hidden="true">✦</span> Make it one line
          </button>
        </div>
      )}
      {(result || loading) && (
        <div className="qual-filters" role="group" aria-label="Goal">
          {GOALS.map(([value, label]) => (
            <button
              key={value || "mixed"}
              type="button"
              className={goal === value ? "active" : ""}
              aria-pressed={goal === value}
              disabled={loading || (!ai.jobId && value !== "one_line")}
              onClick={() => run(value)}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      {!ai.jobId && (
        <p className="ai-meta">Choose a job to get wording aimed at it. One line works without a job.</p>
      )}
      {loading && <p className="ai-meta">{goal === "one_line" ? "Writing one-line versions…" : "Writing options…"}</p>}
      {!loading && result && result.status !== "ok" && <p className="ai-meta">{result.detail}</p>}
      {!loading && result?.status === "ok" && !result.drafts.length && (
        <p className="ai-meta">
          {goal === "one_line"
            ? `No safe one-line version. Drafts either ran past ${charsPerLine(ai)} characters or added facts this bullet doesn't show.`
            : "No safe rewrites. The model's ideas added facts this bullet doesn't show."}
        </p>
      )}
      {!loading && !!result?.drafts.length && (
        <div className="assist-options" role="list" aria-label="AI wording">
          {result.drafts.map((draft, index) => (
            <div
              key={`${draft.name}-${index}`}
              role="listitem"
              className={`assist-option ai-draft-option ${selected === draft.body ? "selected" : ""}`}
            >
              <span className="assist-option-text">
                <strong>{draft.name}</strong>
                <span>{draft.body}</span>
                {goal === "one_line" && (
                  <small>
                    {draft.body.length} of ~{charsPerLine(ai)} characters
                  </small>
                )}
                {draft.rationale && <small>{draft.rationale}</small>}
              </span>
              <button type="button" onClick={() => onPick(draft, result.model)}>
                {selected === draft.body ? "Selected" : "Use"}
              </button>
            </div>
          ))}
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}

/** Save AI wording as a new variant for this resume, with provenance. */
export async function acceptAiWording(
  ai: AiJobContext,
  placementId: string,
  draft: AiDraft,
  body: string,
  model: string,
) {
  const source = body.trim() === draft.body.trim() ? "draft" : "edited";
  return api(
    `/api/compositions/${ai.compositionId}/bullet-placements/${placementId}/ai-variants/accept`,
    {
      method: "POST",
      body: JSON.stringify({
        revision: ai.revision,
        name: draft.name,
        body: body.trim(),
        source,
        job_id: ai.jobId || null,
        model,
      }),
    },
  );
}

export function useVariantPick(ai: AiJobContext, placementIds: string[] | null) {
  const [result, setResult] = useState<VariantPick | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const ids = placementIds ? placementIds.join(",") : "";
  useEffect(() => {
    setResult(null);
    setError("");
    if (!ai.jobId || placementIds === null) return;
    let cancelled = false;
    setLoading(true);
    api<VariantPick>(`/api/compositions/${ai.compositionId}/ai-variant-pick`, {
      method: "POST",
      body: JSON.stringify({ job_id: ai.jobId, placement_ids: placementIds }),
    })
      .then((next) => !cancelled && setResult(next))
      .catch((reason: Error) => !cancelled && setError(reason.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // The revision is left out on purpose: a save from this dialog should not re-run the model.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ai.compositionId, ai.jobId, ids]);
  return { result, loading, error };
}

/** Whole-resume review: one row per placed bullet with the best library wording for the job. */
export function LibraryReviewDialog({ ai, close }: { ai: AiJobContext; close: () => void }) {
  const all = useMemo(() => [] as string[], []);
  const { result, loading, error } = useVariantPick(ai, all);
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [showAll, setShowAll] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");
  const job = ai.jobs.find((item) => item.id === ai.jobId);

  useEffect(() => {
    const next: Record<string, string> = {};
    for (const slot of result?.slots || []) next[slot.placement_id] = slot.best_key;
    setChoice(next);
    setOpen(null);
  }, [result]);

  const slots = (result?.slots || []).filter((slot) => slot.candidates.length > 1);
  const single = (result?.slots.length || 0) - slots.length;
  const recommended = slots.filter((slot) => slot.recommend).length;
  const changes = slots.filter((slot) => (choice[slot.placement_id] || slot.current_key) !== slot.current_key);
  const shown = showAll ? slots : slots.filter((slot) => slot.recommend || changes.includes(slot));
  const groups = new Map<string, PickSlot[]>();
  for (const slot of shown) {
    const key = `${slot.section}|${slot.parent_label}`;
    groups.set(key, [...(groups.get(key) || []), slot]);
  }
  const method = result?.method || "keywords";

  const apply = async () => {
    if (!changes.length) return;
    setBusy(true);
    setSaveError("");
    try {
      const items = changes.map((slot) => {
        const picked = slot.candidates.find((item) => item.key === choice[slot.placement_id])!;
        return { placement_id: slot.placement_id, bullet_id: picked.bullet_id, variant_id: picked.variant_id };
      });
      const state = await api(`/api/compositions/${ai.compositionId}/bullet-placements/replace-many`, {
        method: "POST",
        body: JSON.stringify({ revision: ai.revision, items }),
      });
      await ai.onApplied(state);
      close();
    } catch (reason: any) {
      setSaveError(conflictMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell title="Tailor bullets to a job" close={close} className="assist-dialog library-review-dialog">
      <div className="assist-body">
        <p className="ai-meta">
          For every bullet on this resume, compare each saved wording in your library with the job and choose the best.
          Nothing new is written, so every option is your own text.
        </p>
        <JobSelect ai={ai} />
        {loading && (
          <p className="ai-meta" role="status">
            Reviewing your library{job ? ` against ${jobLabel(job)}` : ""}…
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {!loading && result && (
          <>
            {result.status !== "ok" && <p className="assist-note">{result.detail}</p>}
            <div className="review-summary">
              <strong>
                {recommended
                  ? `${recommended} of ${slots.length} bullets have a better match`
                  : slots.length
                    ? "Your current wording is already the best match"
                    : "No bullet has another saved wording yet"}
              </strong>
              <span className="ai-meta">
                {method === "ai" ? "Ranked by AI fit and job keywords." : "Ranked by job keywords."}
                {single > 0 && ` ${single} bullet${single === 1 ? " has" : "s have"} no other wording in the library.`}
              </span>
              {!slots.length && (
                <span className="ai-meta">
                  Save more wordings to compare: use a bullet's switch button and choose New wording with AI, or
                  edit a bullet and save it as a variant.
                </span>
              )}
              {slots.length > recommended && (
                <label className="review-toggle">
                  <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
                  Show all bullets
                </label>
              )}
            </div>
            {[...groups.entries()].map(([key, rows]) => (
              <section key={key} className="review-group">
                <h3 className="assist-section">
                  {rows[0].parent_label || "Untitled"}
                  <small> · {SECTION_NAMES[rows[0].section] || rows[0].section}</small>
                </h3>
                {rows.map((slot) => {
                  const current = slot.candidates.find((item) => item.current)!;
                  const pickedKey = choice[slot.placement_id] || slot.current_key;
                  const picked = slot.candidates.find((item) => item.key === pickedKey) || current;
                  const switching = pickedKey !== slot.current_key;
                  return (
                    <div key={slot.placement_id} className={`review-slot ${switching ? "switching" : ""}`}>
                      <label className="review-switch">
                        <input
                          type="checkbox"
                          checked={switching}
                          aria-label={`Switch "${current.body.slice(0, 60)}"`}
                          onChange={(e) =>
                            setChoice({
                              ...choice,
                              [slot.placement_id]: e.target.checked
                                ? slot.best_key !== slot.current_key
                                  ? slot.best_key
                                  : slot.candidates.find((item) => !item.current)!.key
                                : slot.current_key,
                            })
                          }
                        />
                      </label>
                      <div className="review-texts">
                        <p className={switching ? "assist-before" : ""}>{current.body}</p>
                        {switching && <p className="assist-after">{picked.body}</p>}
                        <PickBadges
                          option={picked}
                          method={method}
                          best={picked.key === slot.best_key && slot.recommend}
                        />
                        {picked.reason && <small className="ai-meta">{picked.reason}</small>}
                        <button
                          type="button"
                          className="link-button"
                          aria-expanded={open === slot.placement_id}
                          onClick={() => setOpen(open === slot.placement_id ? null : slot.placement_id)}
                        >
                          {open === slot.placement_id ? "Hide options" : `Compare ${slot.candidates.length} options`}
                        </button>
                        {open === slot.placement_id && (
                          <div className="assist-options" role="radiogroup" aria-label="Wording options">
                            {slot.candidates.map((option) => (
                              <label
                                key={option.key}
                                className={`assist-option ${pickedKey === option.key ? "selected" : ""}`}
                              >
                                <input
                                  type="radio"
                                  name={`pick-${slot.placement_id}`}
                                  checked={pickedKey === option.key}
                                  onChange={() => setChoice({ ...choice, [slot.placement_id]: option.key })}
                                />
                                <span className="assist-option-text">
                                  <span>{option.body}</span>
                                  <PickBadges
                                    option={option}
                                    method={method}
                                    best={option.key === slot.best_key && slot.recommend}
                                  />
                                  {option.reason && <small>{option.reason}</small>}
                                </span>
                              </label>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </section>
            ))}
          </>
        )}
        <p className="ai-meta">Switching changes this resume only. Your library wording stays as it is.</p>
        {saveError && (
          <p role="alert" className="error">
            {saveError}
          </p>
        )}
      </div>
      <div className="assist-footer">
        <button type="button" onClick={close}>
          Close
        </button>
        <button type="button" className="primary" disabled={busy || !changes.length} onClick={apply}>
          {busy ? "Saving…" : changes.length ? `Apply ${changes.length} switch${changes.length === 1 ? "" : "es"}` : "Apply"}
        </button>
      </div>
    </ModalShell>
  );
}

export type CondenseItem = {
  kind: "condense" | "remove_bullet" | "remove_entry";
  id: string;
  section: string;
  parent_label: string;
  original: string;
  body: string;
  name: string;
  lines: number;
  lines_saved: number;
  reason: string;
  keyword_hits: string[];
  recommended: boolean;
};
type CondenseResult = {
  status: "ok" | "unavailable" | "rate_limited" | "invalid";
  detail: string;
  model: string;
  method: "ai" | "heuristic";
  revision: number;
  lines_over: number;
  chars_per_line: number;
  items: CondenseItem[];
};

const itemKey = (item: CondenseItem) => `${item.kind}:${item.id}`;
const linesOf = (text: string, perLine: number) => Math.max(1, Math.ceil(text.trim().length / Math.max(1, perLine)));

/** Whole-resume review: bullets to condense and bullets or entries to remove, applied in one save. */
export function ShrinkReviewDialog({ ai, close }: { ai: AiJobContext; close: () => void }) {
  const [result, setResult] = useState<CondenseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [text, setText] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");
  const fit = ai.fit || null;
  const over = linesOver(fit);
  const perLine = charsPerLine(ai);

  useEffect(() => {
    let cancelled = false;
    setResult(null);
    setError("");
    setLoading(true);
    api<CondenseResult>(`/api/compositions/${ai.compositionId}/ai-condense`, {
      method: "POST",
      body: JSON.stringify({
        job_id: ai.jobId || null,
        bullet_lines: fit?.bulletLines || {},
        item_lines: fit?.itemLines || {},
        chars_per_line: perLine,
        lines_over: over,
      }),
    })
      .then((next) => {
        if (cancelled) return;
        setResult(next);
        setPicked(Object.fromEntries(next.items.map((item) => [itemKey(item), item.recommended])));
        setText(Object.fromEntries(next.items.filter((item) => item.kind === "condense").map((item) => [item.id, item.body])));
      })
      .catch((reason: Error) => !cancelled && setError(reason.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // Measured once on open and per job: re-running on every save would re-ask the model.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ai.compositionId, ai.jobId]);

  const items = result?.items || [];
  const saved = (item: CondenseItem) => {
    if (item.kind !== "condense") return item.lines_saved;
    const draft = (text[item.id] || "").trim();
    return draft && draft !== item.original ? Math.max(0, item.lines - linesOf(draft, perLine)) : 0;
  };
  const applicable = (item: CondenseItem) =>
    item.kind !== "condense" || ((text[item.id] || "").trim() !== "" && (text[item.id] || "").trim() !== item.original);
  const chosen = items.filter((item) => picked[itemKey(item)] && applicable(item));
  const total = chosen.reduce((sum, item) => sum + saved(item), 0);
  const groups: [CondenseItem["kind"], string, string][] = [
    ["condense", "Condense", "Shorter wording, saved as a new variant for this resume."],
    ["remove_bullet", "Remove bullets", "Taken off this resume only. They stay in your library."],
    ["remove_entry", "Remove entries", "The whole role or project leaves this resume. It stays in your library."],
  ];

  const apply = async () => {
    if (!chosen.length) return;
    setBusy(true);
    setSaveError("");
    try {
      const state = await api(`/api/compositions/${ai.compositionId}/ai-condense/apply`, {
        method: "POST",
        body: JSON.stringify({
          revision: ai.revision,
          job_id: ai.jobId || null,
          remove_bullets: chosen.filter((item) => item.kind === "remove_bullet").map((item) => item.id),
          remove_entries: chosen.filter((item) => item.kind === "remove_entry").map((item) => item.id),
          rewrites: chosen
            .filter((item) => item.kind === "condense")
            .map((item) => {
              const body = (text[item.id] || "").trim();
              return {
                placement_id: item.id,
                body,
                name: item.name || "Condensed",
                source: item.body && body === item.body.trim() ? "draft" : "edited",
                model: result?.model || "",
              };
            }),
        }),
      });
      await ai.onApplied(state);
      close();
    } catch (reason: any) {
      setSaveError(conflictMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell title="Shrink to fit" close={close} className="assist-dialog library-review-dialog shrink-dialog">
      <div className="assist-body">
        <p className="ai-meta">
          Find bullets to tighten and items to drop so the resume fits its target length. Condensed wording keeps
          only facts the bullet already states.
        </p>
        {ai.jobs.length > 0 && <JobSelect ai={ai} label="Favor relevance to (optional)" />}
        <div className={`review-summary shrink-summary ${over && total >= over ? "covered" : ""}`} role="status">
          <strong>
            {fit?.fits || !over
              ? "Your resume fits its target length."
              : `Over by about ${over} line${over === 1 ? "" : "s"}.`}
            {chosen.length > 0 && ` Selected changes save about ${total} line${total === 1 ? "" : "s"}.`}
          </strong>
          {!!over && chosen.length > 0 && total < over && (
            <span className="ai-meta">Select more to cover the rest.</span>
          )}
          {result && (
            <span className="ai-meta">
              {result.method === "ai"
                ? "Suggested by AI. Line counts are estimates from the preview."
                : "Showing bullets that wrap" + (ai.jobId ? " and items that use none of the job's keywords." : ".")}
            </span>
          )}
        </div>
        {loading && (
          <p className="ai-meta" role="status">
            Reviewing your resume…
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {!loading && result && result.status !== "ok" && <p className="assist-note">{result.detail}</p>}
        {!loading && result && !items.length && (
          <p className="ai-meta">Nothing to suggest. No bullet wraps onto a second line.</p>
        )}
        {!loading &&
          groups.map(([kind, title, note]) => {
            const rows = items.filter((item) => item.kind === kind);
            if (!rows.length) return null;
            return (
              <section key={kind} className="review-group">
                <h3 className="assist-section">
                  {title}
                  <small> · {note}</small>
                </h3>
                {rows.map((item) => {
                  const key = itemKey(item);
                  const on = !!picked[key];
                  const draft = text[item.id] ?? "";
                  const ready = applicable(item);
                  return (
                    <div key={key} className={`review-slot ${on ? "switching" : ""}`}>
                      <label className="review-switch">
                        <input
                          type="checkbox"
                          checked={on && ready}
                          disabled={!ready}
                          aria-label={`${title}: ${(item.original || item.parent_label).slice(0, 60)}`}
                          onChange={(event) => setPicked({ ...picked, [key]: event.target.checked })}
                        />
                      </label>
                      <div className="review-texts">
                        {kind === "remove_entry" ? (
                          <p className={on ? "assist-before" : ""}>
                            <strong>{item.parent_label || "Untitled"}</strong>
                            <small> · {SECTION_NAMES[item.section] || item.section}</small>
                          </p>
                        ) : (
                          <>
                            <small className="ai-meta">{item.parent_label}</small>
                            <p className={on && ready ? "assist-before" : ""}>{item.original}</p>
                          </>
                        )}
                        {kind === "condense" && (
                          <>
                            <textarea
                              className="shrink-draft"
                              rows={2}
                              value={draft}
                              placeholder="Write a shorter version"
                              aria-label="Shorter wording"
                              onChange={(event) => {
                                setText({ ...text, [item.id]: event.target.value });
                                if (event.target.value.trim()) setPicked({ ...picked, [key]: true });
                              }}
                            />
                            {draft.trim() && <LineBudget ai={ai} body={draft} lines={null} />}
                          </>
                        )}
                        <span className="pick-badges">
                          <span className="pick-badge">
                            {item.lines} line{item.lines === 1 ? "" : "s"}
                          </span>
                          {saved(item) > 0 && <span className="pick-badge best">Saves ~{saved(item)}</span>}
                          {item.keyword_hits.length > 0 && (
                            <span className="pick-badge keywords" title={item.keyword_hits.join(", ")}>
                              {item.keyword_hits.length} job keyword{item.keyword_hits.length === 1 ? "" : "s"}
                            </span>
                          )}
                        </span>
                        {item.reason && <small className="ai-meta">{item.reason}</small>}
                      </div>
                    </div>
                  );
                })}
              </section>
            );
          })}
        {saveError && (
          <p role="alert" className="error">
            {saveError}
          </p>
        )}
      </div>
      <div className="assist-footer">
        <button type="button" onClick={close}>
          Close
        </button>
        <button type="button" className="primary" disabled={busy || !chosen.length} onClick={apply}>
          {busy ? "Saving…" : chosen.length ? `Apply ${chosen.length} change${chosen.length === 1 ? "" : "s"}` : "Apply"}
        </button>
      </div>
    </ModalShell>
  );
}

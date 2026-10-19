import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { diffWords } from "./diffWords";
import { activeIdsForTerms } from "../matchMarks";
import type { JobMatchState } from "./useJobMatch";
import { groupLabel, type AssistRequest, type CoachSuggestion, type CoachResult } from "./types";

const PRIORITY_LABEL = { high: "High impact", medium: "Medium impact", low: "Low impact" } as const;

function readDismissed(key: string): string[] {
  try {
    return JSON.parse(localStorage.getItem(key) || "[]");
  } catch {
    return [];
  }
}

function writeDismissed(key: string, ids: string[]) {
  try {
    localStorage.setItem(key, JSON.stringify(ids));
  } catch {
    // Remembering dismissals is a convenience only.
  }
}

export default function CoachTab({
  state,
  compositionId,
  revision,
  summaryVariantId,
  onApplied,
  onAssist,
  onActive,
  autoRun = false,
  onAutoRunDone,
}: {
  state: JobMatchState;
  compositionId: string;
  revision: number;
  summaryVariantId: string | null;
  onApplied: (composition: any) => void;
  onAssist: (request: AssistRequest) => void;
  onActive: (ids: string[]) => void;
  /** Start a review on arrival, as after New from AI Recommendation. */
  autoRun?: boolean;
  onAutoRunDone?: () => void;
}) {
  const job = state.compareJob;
  const storageKey = `resume-engine-coach-dismissed:${compositionId}:${job?.id || ""}`;
  const [result, setResult] = useState<CoachResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [applied, setApplied] = useState<string[]>([]);
  const [dismissed, setDismissed] = useState<string[]>(() => readDismissed(storageKey));
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState("");

  useEffect(() => {
    setResult(null);
    setApplied([]);
    setEditing({});
    setError("");
    setDismissed(readDismissed(storageKey));
  }, [storageKey]);

  const review = async () => {
    if (!job) return;
    setLoading(true);
    setError("");
    try {
      const next = await api<CoachResult>(`/api/job-descriptions/${job.id}/ai-coach`, {
        method: "POST",
        body: JSON.stringify({ composition_id: compositionId }),
      });
      setResult(next);
      setApplied([]);
      setEditing({});
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!autoRun || !job || loading || result) return;
    onAutoRunDone?.();
    review();
    // review reads the current job; it only needs to start once per request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun, job?.id]);

  const dismiss = (id: string) => {
    const next = [...new Set([...dismissed, id])];
    setDismissed(next);
    writeDismissed(storageKey, next);
  };

  const accept = async (card: CoachSuggestion) => {
    if (!job) return;
    const text = (editing[card.id] ?? card.proposed).trim();
    if (!text) return;
    setSaving(card.id);
    setError("");
    try {
      let composition;
      if (card.kind === "summary") {
        composition = await api(`/api/compositions/${compositionId}/summaries/${summaryVariantId}/save`, {
          method: "POST",
          body: JSON.stringify({
            revision,
            mode: "new",
            name: `Summary for ${job.role || job.title || "this job"}`.slice(0, 120),
            body: text,
          }),
        });
      } else {
        composition = await api(
          `/api/compositions/${compositionId}/bullet-placements/${card.placement_id}/ai-variants/accept`,
          {
            method: "POST",
            body: JSON.stringify({
              revision,
              name: `${card.keyword || "Tailored"} (${job.company || "job"})`.slice(0, 120),
              body: text,
              source: text === card.proposed.trim() ? "draft" : "edited",
              job_id: job.id,
              model: result?.model || "",
            }),
          },
        );
      }
      onApplied(composition);
      setApplied((current) => [...current, card.id]);
    } catch (reason: any) {
      setError(
        reason instanceof ApiError && reason.status === 409
          ? "This resume changed. Reload to see the latest, then try again."
          : reason.message,
      );
    } finally {
      setSaving("");
    }
  };

  const open = useMemo(
    () => (result?.suggestions || []).filter((card) => !applied.includes(card.id) && !dismissed.includes(card.id)),
    [result, applied, dismissed],
  );
  const equivalents = (result?.equivalents || []).filter(
    (item) =>
      !dismissed.includes(item.id) &&
      !state.match?.required.concat(state.match?.preferred || [], state.match?.responsibilities || []).some(
        (row) => row.text === item.requirement && row.matched,
      ),
  );
  const doneCount = (result?.suggestions || []).length - open.length;
  const stale = result && result.status === "ok" && result.revision !== revision;

  return (
    <div className="coach-tab">
      <div className="tab-intro">
        <p>
          Reads your whole resume against {job ? <strong>{job.role || job.title}</strong> : "the job"} and suggests edits you can accept,
          edit or dismiss. Suggestions never add facts your resume doesn't already show.
        </p>
        <button type="button" className="primary" disabled={loading || !job} onClick={review}>
          {loading ? "Reviewing…" : result ? "Re-review" : "Review my resume"}
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {loading && (
        <div className="skeleton-list" aria-hidden="true">
          <div className="skeleton-card" />
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </div>
      )}
      {!loading && result && result.status !== "ok" && <p className="empty-state">{result.detail}</p>}
      {!loading && result?.status === "ok" && (
        <>
          <p className="coach-progress">
            {result.suggestions.length} suggestion{result.suggestions.length === 1 ? "" : "s"}
            {doneCount > 0 && ` · ${applied.length} applied, ${doneCount - applied.length} dismissed`}
            {result.dropped > 0 && ` · ${result.dropped} unsafe idea${result.dropped === 1 ? "" : "s"} filtered out`}
          </p>
          {stale && (
            <p className="coach-stale">
              Your resume changed since this review.{" "}
              <button type="button" className="link-button" onClick={review}>
                Re-review
              </button>
            </p>
          )}
          {open.length === 0 && result.suggestions.length > 0 && <p className="empty-state">All suggestions handled.</p>}
          {result.suggestions.length === 0 && <p className="empty-state">The model had no safe edits to suggest.</p>}
          <ul className="coach-list">
            {open.map((card) => {
              const text = editing[card.id];
              return (
                <li key={card.id} className={`coach-card kind-${card.kind}`}>
                  <div className="coach-card-head">
                    <span className={`priority-dot priority-${card.priority}`} title={PRIORITY_LABEL[card.priority]} aria-label={PRIORITY_LABEL[card.priority]} />
                    <span className={`badge group-${card.group}`}>{groupLabel(card.group)}</span>
                    <span className="coach-kind">
                      {card.kind === "rewrite" ? "Reword a bullet" : card.kind === "summary" ? "Reword your summary" : "Add a skill"}
                    </span>
                  </div>
                  <p className="coach-requirement">{card.requirement}</p>
                  {card.kind !== "add_skill" && (
                    <div className="coach-compare">
                      <p className="coach-before">
                        <span className="coach-label">Now</span>
                        {card.original}
                      </p>
                      {text === undefined ? (
                        <p className="coach-after">
                          <span className="coach-label">Suggested</span>
                          {diffWords(card.original, card.proposed)}
                        </p>
                      ) : (
                        <label className="coach-after">
                          <span className="coach-label">Your edit</span>
                          <textarea
                            rows={3}
                            value={text}
                            onChange={(event) => setEditing((current) => ({ ...current, [card.id]: event.target.value }))}
                          />
                        </label>
                      )}
                    </div>
                  )}
                  {card.rationale && <p className="coach-why">{card.rationale}</p>}
                  <div className="row-actions">
                    {card.kind === "add_skill" ? (
                      <button type="button" className="primary" onClick={() => onAssist({ kind: "skill", keyword: card.keyword })}>
                        Add {card.keyword} to Skills
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="primary"
                          disabled={!!saving || (card.kind === "summary" && !summaryVariantId)}
                          onClick={() => accept(card)}
                        >
                          {saving === card.id ? "Saving…" : text === undefined ? "Accept" : "Save edit"}
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            setEditing((current) => {
                              const next = { ...current };
                              if (text === undefined) next[card.id] = card.proposed;
                              else delete next[card.id];
                              return next;
                            })
                          }
                        >
                          {text === undefined ? "Edit" : "Cancel edit"}
                        </button>
                      </>
                    )}
                    <button type="button" className="link-button" onClick={() => dismiss(card.id)}>
                      Dismiss
                    </button>
                    {card.keyword && (
                      <button
                        type="button"
                        className="link-button"
                        onMouseEnter={() => onActive(activeIdsForTerms([card.keyword]))}
                        onMouseLeave={() => onActive([])}
                        onFocus={() => onActive(activeIdsForTerms([card.keyword]))}
                        onBlur={() => onActive([])}
                        onClick={() => onActive(activeIdsForTerms([card.keyword]))}
                      >
                        Show in documents
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          {equivalents.length > 0 && (
            <section className="coach-equivalents" aria-label="Already covered in other words">
              <h3>Already covered in other words</h3>
              <ul className="coach-list">
                {equivalents.map((item) => (
                  <li key={item.id} className="coach-card kind-equivalent">
                    <div className="coach-card-head">
                      <span className={`badge group-${item.group}`}>{groupLabel(item.group)}</span>
                    </div>
                    <p className="coach-requirement">{item.requirement}</p>
                    <p className="coach-before">“{item.bullet}”</p>
                    {item.rationale && <p className="coach-why">{item.rationale}</p>}
                    <div className="row-actions">
                      <button type="button" disabled={state.busy} onClick={() => state.markRequirement({ text: item.requirement }, true)}>
                        Mark as match
                      </button>
                      <button type="button" className="link-button" onClick={() => dismiss(item.id)}>
                        Dismiss
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <p className="ai-meta">AI suggestions never change the match score. The deterministic match re-runs after each change.</p>
        </>
      )}
    </div>
  );
}

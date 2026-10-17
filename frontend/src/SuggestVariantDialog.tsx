import React, { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import KeywordText from "./KeywordText";
import ModalShell from "./ModalShell";
import type { CompareJob } from "./matchMarks";
import type { VariantTarget } from "./match/types";

type Draft = { name: string; body: string; rationale: string };
type Suggestions = {
  status: "ok" | "unavailable" | "rate_limited" | "invalid";
  detail: string;
  model: string;
  original: string;
  category: string;
  drafts: Draft[];
  dropped: number;
  fits?: boolean;
  reason?: string;
};
type Goal = "" | "concise" | "impact" | "align";

const GOALS: [Goal, string][] = [
  ["", "Mixed"],
  ["concise", "Concise"],
  ["impact", "Impact"],
  ["align", "Match the requirement"],
];
// The model may not add these terms; drafts only sharpen wording.
const GUARDED = new Set(["tool", "credential", "degree", "experience_duration"]);
const OWN = -1;


export default function SuggestVariantDialog({
  compositionId,
  revision,
  job,
  target,
  onApplied,
  onAddSkill,
  close,
}: {
  compositionId: string;
  revision: number;
  job: CompareJob;
  target: VariantTarget;
  onApplied: (state: any) => void;
  onAddSkill: (keyword: string) => void;
  close: () => void;
}) {
  const [goal, setGoal] = useState<Goal>("");
  const [result, setResult] = useState<Suggestions | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<number | null>(null);
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [editing, setEditing] = useState<number | null>(null);
  const [own, setOwn] = useState(target.excerpt);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSelected(null);
    setEdits({});
    setEditing(null);
    api<Suggestions>(
      `/api/compositions/${compositionId}/bullet-placements/${target.placementId}/ai-variants`,
      {
        method: "POST",
        body: JSON.stringify({
          job_id: job.id,
          keyword: target.keyword,
          requirement: target.requirement,
          category: target.category || "",
          goal: goal || null,
          incorporate_keyword: !!target.incorporate,
        }),
      },
    )
      .then((next) => {
        if (cancelled) return;
        setResult(next);
        if (next.original) setOwn((current) => (current === target.excerpt ? next.original : current));
      })
      .catch((reason: Error) => !cancelled && setError(reason.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [compositionId, target, job.id, goal]);

  const original = result?.original || target.excerpt;
  const drafts = result?.drafts || [];
  const category = result?.category || target.category;
  const workIn = !!target.incorporate && !!target.keyword && !GUARDED.has(category);
  const textOf = (index: number) => (index === OWN ? own : edits[index] ?? drafts[index]?.body ?? "");
  const chosenText = selected === null ? "" : textOf(selected).trim();
  const canApply =
    !busy && selected !== null && !!chosenText && chosenText !== original.trim();

  const apply = async () => {
    if (!canApply || selected === null) return;
    const draft = selected === OWN ? null : drafts[selected];
    const source = !draft ? "own" : chosenText === draft.body.trim() ? "draft" : "edited";
    setBusy(true);
    setError("");
    try {
      const state = await api(
        `/api/compositions/${compositionId}/bullet-placements/${target.placementId}/ai-variants/accept`,
        {
          method: "POST",
          body: JSON.stringify({
            revision,
            name: draft ? draft.name : "My wording",
            body: chosenText,
            source,
            job_id: source === "own" ? null : job.id,
            model: result?.model || "",
          }),
        },
      );
      onApplied(state);
      close();
    } catch (reason: any) {
      setError(
        reason instanceof ApiError && reason.status === 409
          ? "This resume changed. Reload to see the latest, then try again."
          : reason.message,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell title={workIn ? `Work in ${target.keyword}` : "Suggest wording"} close={close} className="assist-dialog">
      <div className="assist-body">
        <p className="ai-meta">
          For {[job.role || job.title, job.company].filter(Boolean).join(" · ")}
          {target.keyword && <> · {target.keyword}</>}
        </p>
        <blockquote className="assist-original">{original}</blockquote>
        <div className="qual-filters" role="group" aria-label="Goal">
          {GOALS.map(([value, label]) => (
            <button
              key={value || "mixed"}
              type="button"
              className={goal === value ? "active" : ""}
              aria-pressed={goal === value}
              disabled={loading}
              onClick={() => setGoal(value)}
            >
              {label}
            </button>
          ))}
        </div>
        {GUARDED.has(category) && target.keyword && (
          <p className="assist-note">
            Drafts can't add {target.keyword} for you. If it's true, choose Write my own.
            {category === "tool" && (
              <>
                {" "}
                <button type="button" className="link-button" onClick={() => onAddSkill(target.keyword)}>
                  Add to Skills instead
                </button>
              </>
            )}
          </p>
        )}
        {workIn && (
          <p className="assist-note">
            Each option uses {target.keyword}. Only pick one if it describes work you actually did.
          </p>
        )}
        {loading && <p className="ai-meta">Reviewing…</p>}
        {!loading && result && result.status !== "ok" && <p className="ai-meta">{result.detail}</p>}
        {!loading && result?.status === "ok" && drafts.length === 0 && result.fits === false && (
          <p className="ai-meta">
            The AI doesn't think {target.keyword} fits this bullet{result.reason ? `: ${result.reason}` : "."}
          </p>
        )}
        {!loading && result?.status === "ok" && drafts.length === 0 && result.fits !== false && (
          <p className="ai-meta">
            No safe rewrites. The model's ideas added facts the bullet doesn't show
            {workIn ? ` or left out ${target.keyword}` : ""}.
          </p>
        )}
        <div className="assist-options" role="radiogroup" aria-label="Wording options">
          {!loading &&
            drafts.map((draft, index) => (
              <div
                key={`${draft.name}-${index}`}
                className={`assist-option ${selected === index ? "selected" : ""}`}
              >
                <label className="assist-option-pick">
                  <input
                    type="radio"
                    name="variant-option"
                    aria-label={draft.name}
                    checked={selected === index}
                    onChange={() => setSelected(index)}
                  />
                  <span className="assist-option-text">
                    <strong>{draft.name}</strong>
                    {editing === index ? null : (
                      <span>
                        <KeywordText text={textOf(index)} keyword={workIn ? target.keyword : ""} />
                      </span>
                    )}
                    {draft.rationale && <small>{draft.rationale}</small>}
                  </span>
                </label>
                {editing === index ? (
                  <textarea
                    aria-label={`Edit ${draft.name}`}
                    value={textOf(index)}
                    rows={3}
                    autoFocus
                    onChange={(e) => setEdits((current) => ({ ...current, [index]: e.target.value }))}
                  />
                ) : null}
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    setSelected(index);
                    setEditing(editing === index ? null : index);
                  }}
                >
                  {editing === index ? "Done" : "Edit"}
                </button>
              </div>
            ))}
          <div className={`assist-option ${selected === OWN ? "selected" : ""}`}>
            <label className="assist-option-pick">
              <input
                type="radio"
                name="variant-option"
                aria-label="Write my own"
                checked={selected === OWN}
                onChange={() => setSelected(OWN)}
              />
              <span className="assist-option-text">
                <strong>Write my own</strong>
              </span>
            </label>
            {selected === OWN && (
              <textarea
                aria-label="Your wording"
                value={own}
                rows={3}
                onChange={(e) => setOwn(e.target.value)}
              />
            )}
          </div>
        </div>
        <p className="ai-meta">Saved as a new variant for this resume. Other resumes aren't changed.</p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </div>
      <div className="assist-footer">
        <button type="button" onClick={close}>
          Close
        </button>
        <button type="button" className="primary" disabled={!canApply} onClick={apply}>
          {busy ? "Saving…" : "Use this wording"}
        </button>
      </div>
    </ModalShell>
  );
}

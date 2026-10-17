import React, { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import KeywordText, { hasPlaceholder } from "./KeywordText";
import ModalShell from "./ModalShell";
import type { CompareJob } from "./matchMarks";
import type { KeywordAssistResult, KeywordEntry, VariantTarget } from "./match/types";

const SECTION_LABELS: Record<string, string> = {
  work_experience: "Experience",
  projects: "Projects",
  leadership: "Leadership",
};
const OWN = "own";

function entryLabel(entry: KeywordEntry) {
  return `${entry.entry} · ${SECTION_LABELS[entry.section] || entry.section}`;
}

function EntryPicker({
  entries,
  value,
  onChange,
  label,
}: {
  entries: KeywordEntry[];
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  return (
    <label className="assist-field assist-entry">
      <span>Add under</span>
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        {entries.map((entry) => (
          <option key={entry.parent_id} value={entry.parent_id}>
            {entryLabel(entry)}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Work one job keyword into the resume: revise placed bullets or add a new one. */
export default function KeywordAssistDialog({
  compositionId,
  revision,
  job,
  keyword,
  requirement,
  category,
  onApplied,
  onRevise,
  onAddSkill,
  close,
}: {
  compositionId: string;
  revision: number;
  job: CompareJob;
  keyword: string;
  requirement: string;
  category: string;
  onApplied: (state: any) => void;
  /** Opens Suggest wording for one bullet, in keyword mode, for more angles. */
  onRevise: (target: VariantTarget) => void;
  onAddSkill: (keyword: string) => void;
  close: () => void;
}) {
  const [result, setResult] = useState<KeywordAssistResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [parents, setParents] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [own, setOwn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api<KeywordAssistResult>(`/api/compositions/${compositionId}/ai-keyword-assist`, {
      method: "POST",
      body: JSON.stringify({ job_id: job.id, keyword, requirement, category: category || "" }),
    })
      .then((next) => {
        if (cancelled) return;
        setResult(next);
        setParents((current) => ({ ...current, [OWN]: current[OWN] || next.entries[0]?.parent_id || "" }));
      })
      .catch((reason: Error) => !cancelled && setError(reason.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [compositionId, job.id, keyword, requirement, category]);

  const revisions = result?.revisions || [];
  const fresh = result?.new_bullets || [];
  const entries = result?.entries || [];
  const textOf = (id: string) => {
    if (id === OWN) return own;
    const card = revisions.find((item) => item.id === id) || fresh.find((item) => item.id === id);
    return edits[id] ?? card?.body ?? "";
  };
  const parentOf = (id: string) => parents[id] ?? fresh.find((item) => item.id === id)?.parent_id ?? "";
  const chosenText = selected ? textOf(selected).trim() : "";
  const revisionCard = revisions.find((item) => item.id === selected);
  const newCard = fresh.find((item) => item.id === selected);
  const needsParent = selected === OWN || !!newCard;
  const placeholder = needsParent && hasPlaceholder(chosenText);
  const canApply =
    !busy &&
    !!selected &&
    !!chosenText &&
    !placeholder &&
    (!needsParent || !!parentOf(selected)) &&
    (!revisionCard || chosenText !== revisionCard.original.trim());

  const apply = async () => {
    if (!canApply || !selected) return;
    setBusy(true);
    setError("");
    try {
      let state;
      if (revisionCard) {
        const source = chosenText === revisionCard.body.trim() ? "draft" : "edited";
        state = await api(
          `/api/compositions/${compositionId}/bullet-placements/${revisionCard.placement_id}/ai-variants/accept`,
          {
            method: "POST",
            body: JSON.stringify({
              revision,
              name: `Uses ${keyword}`.slice(0, 120),
              body: chosenText,
              source,
              job_id: job.id,
              model: result?.model || "",
            }),
          },
        );
      } else {
        const parentId = parentOf(selected);
        const source = !newCard
          ? "own"
          : chosenText === newCard.body.trim() && parentId === newCard.parent_id
            ? "draft"
            : "edited";
        state = await api(`/api/compositions/${compositionId}/ai-keyword-assist/accept-new`, {
          method: "POST",
          body: JSON.stringify({
            revision,
            parent_id: parentId,
            body: chosenText,
            source,
            job_id: source === "own" ? null : job.id,
            model: result?.model || "",
          }),
        });
      }
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

  const editToggle = (id: string, label: string) => (
    <button
      type="button"
      className="link-button"
      onClick={() => {
        setSelected(id);
        setEditing(editing === id ? null : id);
      }}
    >
      {editing === id ? "Done" : `Edit ${label}`}
    </button>
  );
  const editor = (id: string, label: string) =>
    editing === id ? (
      <textarea
        aria-label={`Edit ${label}`}
        value={textOf(id)}
        rows={3}
        autoFocus
        onChange={(e) => setEdits((current) => ({ ...current, [id]: e.target.value }))}
      />
    ) : null;
  const nothing = !loading && result?.status === "ok" && !revisions.length && !fresh.length;

  return (
    <ModalShell title={`Work in ${keyword}`} close={close} className="assist-dialog keyword-assist">
      <div className="assist-body">
        <p className="ai-meta">
          For {[job.role || job.title, job.company].filter(Boolean).join(" · ")}
          {requirement && <> · {requirement}</>}
        </p>
        <p className="assist-note">
          Only use wording with {keyword} if it describes work you actually did. It appears on your resume as written.
        </p>
        {loading && <p className="ai-meta">Reviewing your resume…</p>}
        {!loading && result && result.status !== "ok" && <p className="ai-meta">{result.detail}</p>}
        {!loading && result?.status === "ok" && !result.allowed && (
          <p className="ai-meta">
            The AI can't add {keyword} for you.{" "}
            <button type="button" className="link-button" onClick={() => onAddSkill(keyword)}>
              Add to Skills instead
            </button>
          </p>
        )}
        {nothing && result?.allowed && (
          <p className="ai-meta">
            {result.no_fit_reason
              ? `No safe suggestions: ${result.no_fit_reason}`
              : `No safe suggestions. The model's ideas added facts your resume doesn't show.`}
          </p>
        )}
        <div className="assist-options" role="radiogroup" aria-label="Ways to use the keyword">
          {!loading && revisions.length > 0 && <h4 className="assist-section">Revise an existing bullet</h4>}
          {!loading &&
            revisions.map((card, index) => {
              const label = `revision ${index + 1}`;
              return (
                <div key={card.id} className={`assist-option ${selected === card.id ? "selected" : ""}`}>
                  <label className="assist-option-pick">
                    <input
                      type="radio"
                      name="keyword-option"
                      aria-label={`Revise: ${card.original}`}
                      checked={selected === card.id}
                      onChange={() => setSelected(card.id)}
                    />
                    <span className="assist-option-text">
                      <small>{[card.entry, card.section].filter(Boolean).join(" · ")}</small>
                      <span className="assist-before">{card.original}</span>
                      {editing === card.id ? null : (
                        <strong className="assist-after">
                          <KeywordText text={textOf(card.id)} keyword={keyword} />
                        </strong>
                      )}
                      {card.rationale && <small>{card.rationale}</small>}
                    </span>
                  </label>
                  {editor(card.id, label)}
                  <div className="assist-option-links">
                    {editToggle(card.id, label)}
                    <button
                      type="button"
                      className="link-button"
                      onClick={() =>
                        onRevise({
                          placementId: card.placement_id,
                          excerpt: card.original,
                          keyword,
                          requirement,
                          category: result?.category || category,
                          incorporate: true,
                        })
                      }
                    >
                      More options for this bullet
                    </button>
                  </div>
                </div>
              );
            })}
          {!loading && !!result?.allowed && entries.length > 0 && (
            <h4 className="assist-section">Add a new bullet</h4>
          )}
          {!loading &&
            fresh.map((card, index) => {
              const label = `new bullet ${index + 1}`;
              return (
                <div key={card.id} className={`assist-option ${selected === card.id ? "selected" : ""}`}>
                  <label className="assist-option-pick">
                    <input
                      type="radio"
                      name="keyword-option"
                      aria-label={`New bullet: ${card.body}`}
                      checked={selected === card.id}
                      onChange={() => setSelected(card.id)}
                    />
                    <span className="assist-option-text">
                      {editing === card.id ? null : (
                        <strong className="assist-after">
                          <KeywordText text={textOf(card.id)} keyword={keyword} />
                        </strong>
                      )}
                      {card.rationale && <small>{card.rationale}</small>}
                    </span>
                  </label>
                  {editor(card.id, label)}
                  {selected === card.id && (
                    <EntryPicker
                      entries={entries}
                      value={parentOf(card.id)}
                      label={`Entry for ${label}`}
                      onChange={(value) => setParents((current) => ({ ...current, [card.id]: value }))}
                    />
                  )}
                  {selected === card.id && hasPlaceholder(textOf(card.id)) && (
                    <p className="assist-placeholder-note">Replace each [placeholder] with your real detail before saving.</p>
                  )}
                  <div className="assist-option-links">{editToggle(card.id, label)}</div>
                </div>
              );
            })}
          {!loading && !!result?.allowed && entries.length > 0 && (
            <div className={`assist-option ${selected === OWN ? "selected" : ""}`}>
              <label className="assist-option-pick">
                <input
                  type="radio"
                  name="keyword-option"
                  aria-label="Write a new bullet myself"
                  checked={selected === OWN}
                  onChange={() => {
                    setSelected(OWN);
                    setOwn((current) => current || `${keyword} `);
                  }}
                />
                <span className="assist-option-text">
                  <strong>Write a new bullet myself</strong>
                </span>
              </label>
              {selected === OWN && (
                <>
                  <textarea aria-label="Your bullet" value={own} rows={3} autoFocus onChange={(e) => setOwn(e.target.value)} />
                  <EntryPicker
                    entries={entries}
                    value={parentOf(OWN)}
                    label="Entry for your bullet"
                    onChange={(value) => setParents((current) => ({ ...current, [OWN]: value }))}
                  />
                </>
              )}
            </div>
          )}
        </div>
        <p className="ai-meta">
          {revisionCard
            ? "Saved as a new variant for this resume. Other resumes aren't changed."
            : "A new bullet is added to this resume and your library. Other resumes aren't changed."}
        </p>
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
          {busy ? "Saving…" : revisionCard ? "Use this wording" : "Add this bullet"}
        </button>
      </div>
    </ModalShell>
  );
}

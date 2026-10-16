import React, { useEffect, useId, useState } from "react";
import { api, ApiError } from "./api";
import ModalShell from "./ModalShell";

type GroupOption = {
  group_id: string;
  name: string;
  on_resume: boolean;
  score: number;
  reason: string;
};

type ExistingTool = {
  tool_id: string;
  group_id: string | null;
  group_name: string;
  name: string;
  state: "on_resume" | "hidden_here" | "group_not_on_resume" | "archived";
};

type Recommendation = {
  label: string;
  existing: ExistingTool | null;
  groups: GroupOption[];
  recommended_group_id: string | null;
  new_group_name: string | null;
  source: "library" | "related" | "hint" | "ai" | "none";
  status: string;
};

const NEW_GROUP = "__new__";

function existingNote(existing: ExistingTool | null, chosen: string) {
  if (!existing) return "";
  const group = existing.group_name;
  if (existing.group_id && chosen !== existing.group_id)
    return `${existing.name} is already in ${group}. Adding it here keeps that one as it is.`;
  if (existing.state === "archived") return `Restores ${existing.name} from the archive into ${group}.`;
  if (existing.state === "hidden_here") return `${existing.name} is in ${group}. This shows it on this resume.`;
  if (existing.state === "group_not_on_resume")
    return `${existing.name} is in ${group}. This adds it to this resume.`;
  return `${existing.name} is already in ${group} on this resume.`;
}

export default function AddSkillDialog({
  compositionId,
  revision,
  keyword,
  onApplied,
  close,
}: {
  compositionId: string;
  revision: number;
  keyword: string;
  onApplied: (state: any) => void;
  close: () => void;
}) {
  const nameId = useId();
  const newGroupId = useId();
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [lookingWithAi, setLookingWithAi] = useState(false);
  const [aiNote, setAiNote] = useState("");
  const [name, setName] = useState(keyword);
  const [choice, setChoice] = useState("");
  const [newGroup, setNewGroup] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const ask = (allowAi: boolean) =>
      api<Recommendation>(`/api/compositions/${compositionId}/skills/recommend`, {
        method: "POST",
        body: JSON.stringify({ keyword, allow_ai: allowAi }),
      });
    const apply = (next: Recommendation) => {
      setRec(next);
      setName((current) => (current === keyword ? next.label : current));
      if (next.recommended_group_id) setChoice(next.recommended_group_id);
      else if (!next.groups.length) setChoice(NEW_GROUP);
      if (next.new_group_name) setNewGroup((current) => current || next.new_group_name || "");
    };
    ask(false)
      .then(async (local) => {
        if (cancelled) return;
        apply(local);
        // Local library, related skills and hints come first. The model is only asked when they found nothing.
        if (local.source !== "none") return;
        setLookingWithAi(true);
        try {
          const withAi = await ask(true);
          if (cancelled) return;
          if (withAi.source === "ai") apply(withAi);
          else setAiNote("No suggestion.");
        } catch {
          if (!cancelled) setAiNote("No suggestion.");
        } finally {
          if (!cancelled) setLookingWithAi(false);
        }
      })
      .catch((reason: Error) => !cancelled && setError(reason.message));
    return () => {
      cancelled = true;
    };
  }, [compositionId, keyword]);

  const recommended = rec?.groups.find((group) => group.group_id === rec.recommended_group_id);
  const canAdd =
    !busy && name.trim() && (choice === NEW_GROUP ? newGroup.trim() : choice);

  const add = async () => {
    if (!canAdd) return;
    setBusy(true);
    setError("");
    try {
      const state = await api(`/api/compositions/${compositionId}/skills`, {
        method: "POST",
        body: JSON.stringify(
          choice === NEW_GROUP
            ? { revision, name: name.trim(), new_group_name: newGroup.trim() }
            : { revision, name: name.trim(), group_id: choice },
        ),
      });
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
    <ModalShell title="Add to Skills" close={close} className="assist-dialog">
      <div className="assist-body">
        <label className="assist-field" htmlFor={nameId}>
          <span>Skill</span>
          <input id={nameId} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
        </label>
        <p className="assist-note">Only add skills you've used.</p>
        {!rec && !error && <p className="ai-meta">Finding a group…</p>}
        {rec && (
          <fieldset className="assist-options">
            <legend>Group</legend>
            {rec.groups.map((group) => (
              <label
                key={group.group_id}
                className={`assist-option ${choice === group.group_id ? "selected" : ""}`}
              >
                <input
                  type="radio"
                  name="skill-group"
                  value={group.group_id}
                  checked={choice === group.group_id}
                  onChange={() => setChoice(group.group_id)}
                />
                <span className="assist-option-text">
                  <strong>{group.name}</strong>
                  {!group.on_resume && <span className="status-badge default">Not on this resume yet</span>}
                  {group.group_id === rec.recommended_group_id && group.reason && (
                    <small>{group.reason}</small>
                  )}
                </span>
              </label>
            ))}
            <label className={`assist-option ${choice === NEW_GROUP ? "selected" : ""}`}>
              <input
                type="radio"
                name="skill-group"
                value={NEW_GROUP}
                checked={choice === NEW_GROUP}
                onChange={() => setChoice(NEW_GROUP)}
              />
              <span className="assist-option-text">
                <strong>New group</strong>
                {choice === NEW_GROUP && (
                  <input
                    id={newGroupId}
                    aria-label="New group name"
                    value={newGroup}
                    maxLength={120}
                    placeholder="Group name"
                    onChange={(e) => setNewGroup(e.target.value)}
                  />
                )}
              </span>
            </label>
          </fieldset>
        )}
        {lookingWithAi && <p className="ai-meta">Looking for a group…</p>}
        {!lookingWithAi && aiNote && !recommended && <p className="ai-meta">{aiNote}</p>}
        {rec?.existing && <p className="assist-note">{existingNote(rec.existing, choice)}</p>}
        <p className="ai-meta">Adds to your Library and this resume. Other resumes aren't changed.</p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </div>
      <div className="assist-footer">
        <button type="button" onClick={close}>
          Cancel
        </button>
        <button type="button" className="primary" disabled={!canAdd} onClick={add}>
          {busy ? "Adding…" : "Add"}
        </button>
      </div>
    </ModalShell>
  );
}

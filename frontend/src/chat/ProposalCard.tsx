import { useState } from "react";
import { diffWords } from "../match/diffWords";

export type ChatProposal = {
  id: string;
  kind: "rewrite" | "summary" | "new_bullet" | "remove" | "reorder" | "add_skill" | "use_library";
  rationale: string;
  placement_id: string;
  bullet_id: string;
  variant_id: string;
  parent_id: string;
  parent_type: string;
  section: string;
  entry: string;
  keyword: string;
  original: string;
  proposed: string;
  placeholders: boolean;
  order: string[];
  before: string[];
  after: string[];
  /** Set on held-back wording: why the guard flagged it. */
  reason?: string;
  term?: string;
};

export type ProposalOutcome = "applied" | "dismissed";

const PLACEHOLDER = /\[[^[\]\n]{1,30}\]/;

function title(card: ChatProposal) {
  switch (card.kind) {
    case "rewrite":
      return "Reword a bullet";
    case "summary":
      return "Reword your summary";
    case "new_bullet":
      return `Add a bullet${card.entry ? ` to ${card.entry}` : ""}`;
    case "remove":
      return "Remove a bullet";
    case "reorder":
      return `Reorder bullets${card.entry ? ` in ${card.entry}` : ""}`;
    case "add_skill":
      return `Add ${card.keyword} to Skills`;
    case "use_library":
      return card.placement_id ? "Swap in a library bullet" : `Add a library bullet${card.entry ? ` to ${card.entry}` : ""}`;
  }
}

export default function ProposalCard({
  card,
  held = false,
  outcome,
  saving,
  disabled,
  summaryReady,
  onAccept,
  onDismiss,
}: {
  card: ChatProposal;
  /** Wording the guard flagged: shown with its reason, and saved only after the user edits it. */
  held?: boolean;
  outcome?: ProposalOutcome;
  saving: boolean;
  disabled: boolean;
  summaryReady: boolean;
  onAccept: (text: string) => void;
  onDismiss: () => void;
}) {
  const editable = card.kind === "rewrite" || card.kind === "summary" || card.kind === "new_bullet";
  // Wording with [placeholders] or held back by the guard opens in edit mode: the user supplies the details.
  const [text, setText] = useState<string | undefined>(card.placeholders || held ? card.proposed : undefined);
  const value = text ?? card.proposed;
  const placeholders = editable && PLACEHOLDER.test(value);
  const untouched = held && value.trim() === card.proposed.trim();
  const blocked = placeholders || untouched;

  if (outcome) {
    return (
      <li className={`chat-proposal done ${outcome}`}>
        <span className="coach-kind">{title(card)}</span>
        <span className="chat-outcome">{outcome === "applied" ? "Applied" : "Dismissed"}</span>
      </li>
    );
  }

  return (
    <li className={`chat-proposal kind-${card.kind}${held ? " held" : ""}`}>
      <span className="coach-kind">{title(card)}</span>
      {held && card.reason && (
        <p className="chat-warning">
          <span aria-hidden="true">⚠ </span>
          {card.reason}
        </p>
      )}
      {(card.kind === "rewrite" || card.kind === "summary" || (card.kind === "use_library" && card.placement_id)) && (
        <div className="coach-compare">
          <p className="coach-before">
            <span className="coach-label">Now</span>
            {card.original}
          </p>
          {text === undefined ? (
            <p className="coach-after">
              <span className="coach-label">{card.kind === "use_library" ? "From your library" : "Suggested"}</span>
              {card.kind === "use_library" ? card.proposed : diffWords(card.original, card.proposed)}
            </p>
          ) : null}
        </div>
      )}
      {(card.kind === "new_bullet" || (card.kind === "use_library" && !card.placement_id)) && text === undefined && (
        <p className="coach-after">
          <span className="coach-label">{card.kind === "use_library" ? "From your library" : "New bullet"}</span>
          {card.proposed}
        </p>
      )}
      {editable && text !== undefined && (
        <label className="coach-after">
          <span className="coach-label">Your edit</span>
          <textarea rows={3} value={text} onChange={(event) => setText(event.target.value)} />
        </label>
      )}
      {placeholders && <p className="chat-note">Replace the [placeholders] with your own details before saving.</p>}
      {card.kind === "remove" && (
        <p className="coach-before chat-removed">
          <span className="coach-label">Remove</span>
          <del>{card.original}</del>
          <span className="chat-note">It stays in your library.</span>
        </p>
      )}
      {card.kind === "reorder" && (
        <div className="chat-reorder">
          <ol aria-label="Current order">
            {card.before.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ol>
          <span className="coach-label">New order</span>
          <ol aria-label="New order">
            {card.after.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ol>
        </div>
      )}
      {card.rationale && <p className="coach-why">{card.rationale}</p>}
      <div className="row-actions">
        <button
          type="button"
          className="primary"
          disabled={disabled || blocked || (editable && !value.trim()) || (card.kind === "summary" && !summaryReady)}
          onClick={() => onAccept(value)}
        >
          {saving ? "Saving…" : card.kind === "add_skill" ? "Choose a group…" : held ? "Save my edit" : text === undefined ? "Accept" : "Save edit"}
        </button>
        {editable && !held && (
          <button type="button" disabled={disabled} onClick={() => setText(text === undefined ? card.proposed : undefined)}>
            {text === undefined ? "Edit" : "Cancel edit"}
          </button>
        )}
        <button type="button" className="link-button" disabled={disabled} onClick={onDismiss}>
          Dismiss
        </button>
      </div>
    </li>
  );
}

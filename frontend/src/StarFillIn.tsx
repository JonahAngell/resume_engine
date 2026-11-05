import React from "react";

/** STAR method support for AI drafts: the breakdown of a draft and fields for its [placeholders]. */

export type StarPart = "situation" | "task" | "action" | "result";
export type StarParts = Record<StarPart, string>;
export type StarGap = { placeholder: string; part: StarPart; question: string };

export const STAR_PARTS: [StarPart, string, string][] = [
  ["situation", "S", "Situation"],
  ["task", "T", "Task"],
  ["action", "A", "Action"],
  ["result", "R", "Result"],
];
const LABEL = Object.fromEntries(
  STAR_PARTS.map(([part, , label]) => [part, label]),
) as Record<StarPart, string>;

/** The draft with every answered [placeholder] replaced; unanswered ones stay in brackets. */
export function fillPlaceholders(
  body: string,
  gaps: StarGap[],
  values: Record<string, string>,
) {
  let text = body;
  for (const gap of gaps) {
    const value = (values[gap.placeholder] || "").trim();
    if (value) text = text.split(gap.placeholder).join(value);
  }
  return text;
}

function listOf(items: string[]) {
  return items.length < 2
    ? items.join("")
    : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** "Your bullet doesn't show its Situation and Result" for the original bullet. */
export function StarMissingNote({ missing }: { missing?: StarPart[] }) {
  if (!missing?.length) {
    return (
      <p className="assist-note">
        STAR drafts frame the bullet as Situation, Task, Action and Result.
      </p>
    );
  }
  return (
    <p className="assist-note">
      Your bullet doesn't show its {listOf(missing.map((part) => LABEL[part]))}.
      Drafts mark what's missing in [brackets] so you can add the real details.
    </p>
  );
}

/** Four S/T/A/R chips; a part the draft lacks, or still has as a placeholder, is flagged. */
export function StarBreakdown({
  star,
  gaps = [],
  values = {},
}: {
  star?: StarParts | null;
  gaps?: StarGap[];
  values?: Record<string, string>;
}) {
  if (!star) return null;
  const open = new Set(
    gaps
      .filter((gap) => !(values[gap.placeholder] || "").trim())
      .map((gap) => gap.part),
  );
  return (
    <ul className="star-breakdown" aria-label="STAR breakdown">
      {STAR_PARTS.map(([part, letter, label]) => {
        const text = fillPlaceholders(star[part], gaps, values);
        const state = !text ? "absent" : open.has(part) ? "needs" : "present";
        return (
          <li key={part} className={`star-part star-${state}`}>
            <span className="star-letter" aria-hidden="true">
              {letter}
            </span>
            <span>
              <span className="star-label">{label}</span>
              {state === "absent" ? (
                <span className="star-text star-muted"> not stated</span>
              ) : (
                <span className="star-text"> {text}</span>
              )}
              {state === "needs" && (
                <span className="sr-only"> (needs your details)</span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** One field per [placeholder], labelled with the model's question and its STAR part. */
export function StarGapFields({
  gaps,
  values,
  onChange,
  idPrefix,
}: {
  gaps: StarGap[];
  values: Record<string, string>;
  onChange: (placeholder: string, value: string) => void;
  idPrefix: string;
}) {
  if (!gaps.length) return null;
  const left = gaps.filter(
    (gap) => !(values[gap.placeholder] || "").trim(),
  ).length;
  return (
    <fieldset className="star-gaps">
      <legend>Add the missing details</legend>
      {gaps.map((gap, index) => {
        const id = `${idPrefix}-gap-${index}`;
        return (
          <div key={gap.placeholder} className="star-gap">
            <label htmlFor={id}>
              <span className={`star-chip star-chip-${gap.part}`}>
                {LABEL[gap.part]}
              </span>{" "}
              {gap.question}
            </label>
            <input
              id={id}
              type="text"
              value={values[gap.placeholder] || ""}
              placeholder={gap.placeholder.slice(1, -1)}
              maxLength={120}
              onChange={(event) =>
                onChange(gap.placeholder, event.target.value)
              }
            />
          </div>
        );
      })}
      <p
        className={left ? "assist-placeholder-note" : "ai-meta"}
        aria-live="polite"
      >
        {left
          ? `${left} detail${left === 1 ? "" : "s"} left. Only add what's true; the AI can't know these.`
          : "All details added."}
      </p>
    </fieldset>
  );
}

import React, { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { api } from "../api";
import type { MarkItem } from "../matchMarks";
import { groupLabel, type AssistRequest } from "./types";

type Definition = {
  status: "ok" | "unavailable" | "rate_limited" | "invalid";
  detail: string;
  definition: string;
  in_this_job: string;
};
type DefineState = { loading: true } | { loading: false; result?: Definition; error?: string };

/** Definitions already fetched this session, by job and keyword. */
const definitions = new Map<string, Definition>();
const defineKey = (jobId: string, keyword: string) => `${jobId}:${keyword.trim().toLowerCase()}`;

export type PopoverAnchor = { left: number; top: number; right: number; bottom: number };

const GAP = 8;
const MARGIN = 12;

export default function MarkPopover({
  anchor,
  items,
  source,
  jobId,
  onClose,
  onAssist,
  onSkip,
  onShowInDashboard,
  onShowOther,
}: {
  anchor: PopoverAnchor;
  items: MarkItem[];
  source: "job" | "resume";
  jobId: string;
  onClose: () => void;
  onAssist: (request: AssistRequest) => void;
  /** Hide a missing keyword the user doesn't have. It still counts as missing in scores. */
  onSkip: (item: MarkItem) => void;
  onShowInDashboard: (item: MarkItem) => void;
  onShowOther: (item: MarkItem) => void;
}) {
  const card = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const [defined, setDefined] = useState<Record<string, DefineState>>(() => {
    const known: Record<string, DefineState> = {};
    for (const item of items) {
      const result = definitions.get(defineKey(jobId, item.keyword));
      if (result) known[item.keyword] = { loading: false, result };
    }
    return known;
  });

  const define = async (item: MarkItem) => {
    if (!jobId) return;
    setDefined((current) => ({ ...current, [item.keyword]: { loading: true } }));
    try {
      const result = await api<Definition>(`/api/job-descriptions/${jobId}/define`, {
        method: "POST",
        body: JSON.stringify({ keyword: item.keyword, requirement: item.requirement }),
      });
      if (result.status === "ok") definitions.set(defineKey(jobId, item.keyword), result);
      setDefined((current) => ({ ...current, [item.keyword]: { loading: false, result } }));
    } catch (reason: any) {
      setDefined((current) => ({ ...current, [item.keyword]: { loading: false, error: reason.message } }));
    }
  };

  useLayoutEffect(() => {
    const box = card.current?.getBoundingClientRect();
    if (!box) return;
    const width = box.width;
    const height = box.height;
    const below = anchor.bottom + GAP;
    const top = below + height > innerHeight - MARGIN ? Math.max(MARGIN, anchor.top - GAP - height) : below;
    const left = Math.min(Math.max(MARGIN, anchor.left), innerWidth - width - MARGIN);
    setPosition({ left, top });
  }, [anchor, items, defined]);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    requestAnimationFrame(() =>
      (card.current?.querySelector<HTMLElement>(".mark-actions button") || card.current?.querySelector<HTMLElement>("button"))?.focus(),
    );
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    const onPointer = (event: PointerEvent) => {
      if (card.current && !card.current.contains(event.target as Node)) onClose();
    };
    // Close when the user scrolls the page, not when hover pairing scrolls a document into view.
    const onScroll = (event: Event) => {
      if (card.current && event.target instanceof Node && card.current.contains(event.target)) return;
      onClose();
    };
    addEventListener("keydown", onKey);
    addEventListener("pointerdown", onPointer, true);
    addEventListener("wheel", onScroll, { capture: true, passive: true });
    addEventListener("touchmove", onScroll, { capture: true, passive: true });
    addEventListener("resize", onClose);
    return () => {
      removeEventListener("keydown", onKey);
      removeEventListener("pointerdown", onPointer, true);
      removeEventListener("wheel", onScroll, true);
      removeEventListener("touchmove", onScroll, true);
      removeEventListener("resize", onClose);
      if (opener?.isConnected) opener.focus();
    };
  }, [onClose]);

  const first = items[0];
  return (
    <div
      ref={card}
      className="mark-popover"
      role="dialog"
      aria-labelledby={titleId}
      style={position ? { left: position.left, top: position.top } : { visibility: "hidden", left: 0, top: 0 }}
    >
      <div className="mark-popover-head">
        <h3 id={titleId}>{first?.keyword || "Highlight"}</h3>
        <button type="button" className="icon-button" aria-label="Close" onClick={onClose}>
          ×
        </button>
      </div>
      {items.map((item, index) => (
        <section className="mark-popover-item" key={`${item.requirement}-${item.keyword}-${index}`}>
          {index > 0 && <h4>{item.keyword}</h4>}
          <p className="mark-badges">
            <span className={`badge group-${item.group}`}>{groupLabel(item.group)}</span>
            <span className={`badge status-${item.status}`}>
              {item.status === "matched" ? (item.manual ? "Marked as matched" : "Matched") : "Suggested"}
            </span>
          </p>
          <p className="mark-requirement">{item.requirement}</p>
          <DefinitionView state={defined[item.keyword]} />
          {item.status === "suggested" && !item.rewrites.length && !item.addSkill && !item.workIn && (
            <p className="mark-hint">Not found in this resume yet. Mark it as a match from the dashboard if you cover it in other words.</p>
          )}
          <div className="mark-actions">
            {item.workIn && (
              <button
                type="button"
                className="primary"
                title={`Suggest bullets that use ${item.keyword}`}
                onClick={() =>
                  onAssist({ kind: "keyword", keyword: item.keyword, requirement: item.requirement, category: item.category })
                }
              >
                Work into resume
              </button>
            )}
            {item.rewrites.map((target) => (
              <button
                type="button"
                className={item.workIn ? "" : "primary"}
                key={target.placementId}
                title={target.excerpt}
                onClick={() => onAssist({ kind: "rewrite", target })}
              >
                Generate AI revision
                {item.rewrites.length > 1 && <span className="mark-action-note">“{target.excerpt.slice(0, 40)}…”</span>}
              </button>
            ))}
            {item.addSkill && (
              <button type="button" onClick={() => onAssist({ kind: "skill", keyword: item.keyword })}>
                Add to Skills
              </button>
            )}
            {item.status === "suggested" && jobId && !defined[item.keyword] && (
              <button type="button" title={`Explain what ${item.keyword} means`} onClick={() => define(item)}>
                Define
              </button>
            )}
            {item.status === "suggested" && (
              <button
                type="button"
                className="link-button"
                title="Hides the highlight. It still counts as missing in your ATS score."
                onClick={() => onSkip(item)}
              >
                I don’t have this
              </button>
            )}
            <button type="button" className="link-button" onClick={() => onShowInDashboard(item)}>
              Show in dashboard
            </button>
            <button type="button" className="link-button" onClick={() => onShowOther(item)}>
              {source === "job" ? "Show in resume" : "Show in job"}
            </button>
          </div>
        </section>
      ))}
    </div>
  );
}

function DefinitionView({ state }: { state?: DefineState }) {
  if (!state) return null;
  if (state.loading) return <p className="mark-hint" role="status">Looking up a definition…</p>;
  if (state.error || state.result?.status !== "ok") {
    return <p className="mark-hint" role="status">{state.error || state.result?.detail || "No definition available."}</p>;
  }
  return (
    <div className="mark-definition" role="status">
      <p>{state.result.definition}</p>
      {state.result.in_this_job && <p className="mark-hint">In this job: {state.result.in_this_job}</p>}
      <p className="mark-hint">AI-generated. Check before relying on it.</p>
    </div>
  );
}

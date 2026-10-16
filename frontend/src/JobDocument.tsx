import React, { useEffect, useRef } from "react";
import { highlightSegments, type CompareJob, type MatchMark } from "./matchMarks";
import type { PopoverAnchor } from "./match/MarkPopover";

export default function JobDocument({
  job,
  marks,
  activeIds,
  onActive,
  onMarkClick,
}: {
  job: CompareJob | null;
  marks: MatchMark[];
  activeIds: string[];
  onActive: (ids: string[]) => void;
  /** A highlight was clicked or activated from the keyboard. */
  onMarkClick?: (markId: string, anchor: PopoverAnchor) => void;
}) {
  const paper = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!activeIds.length || !paper.current) return;
    const hit = [...paper.current.querySelectorAll<HTMLElement>("[data-match-id]")].find((el) =>
      activeIds.includes(el.dataset.matchId || ""),
    );
    hit?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [activeIds, job, marks]);

  if (!job) {
    return (
      <div className="job-document-empty">
        <p>Choose a saved job description to compare it with this resume.</p>
      </div>
    );
  }
  const meta = [job.company, job.role].filter(Boolean).join(" · ");
  const open = (element: HTMLElement) => {
    const id = element.dataset.matchId || "";
    const box = element.getBoundingClientRect();
    if (id) onMarkClick?.(id, { left: box.left, top: box.top, right: box.right, bottom: box.bottom });
  };
  const segments = highlightSegments(job.body, marks);
  return (
    <article
      className="job-paper"
      ref={paper}
      aria-label="Job description"
      onMouseOver={(event) => {
        const hit = (event.target as HTMLElement).closest<HTMLElement>("[data-match-id]");
        if (!hit || !event.currentTarget.contains(hit)) return;
        const id = hit.dataset.matchId || "";
        if (id) onActive([id]);
      }}
      onMouseOut={(event) => {
        const next = event.relatedTarget;
        if (next instanceof Node && event.currentTarget.contains(next)) {
          const hit = next instanceof Element ? next.closest("[data-match-id]") : null;
          if (hit) return;
        }
        onActive([]);
      }}
    >
      <h2>{job.title || "Job description"}</h2>
      {meta && <p className="job-paper-meta">{meta}</p>}
      {job.body.trim() ? (
        <div className="job-paper-body">
          {segments.map((segment, index) =>
            segment.mark ? (
              <mark
                key={`${segment.mark.id}-${index}`}
                data-match-id={segment.mark.id}
                className={`doc-hit ${segment.mark.kind}${activeIds.includes(segment.mark.id) ? " hit-paired" : ""}`}
                role="button"
                tabIndex={0}
                aria-label={`${segment.text}: ${segment.mark.kind === "match" ? "matched" : "suggested"}. Show details`}
                onClick={(event) => open(event.currentTarget)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    open(event.currentTarget);
                  }
                }}
              >
                {segment.text}
              </mark>
            ) : (
              <span key={index}>{segment.text}</span>
            ),
          )}
        </div>
      ) : (
        <p>No description yet.</p>
      )}
    </article>
  );
}

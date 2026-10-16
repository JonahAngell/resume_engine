import React, { useEffect, useRef } from "react";
import { highlightSegments, type CompareJob, type MatchMark } from "./matchMarks";

export default function JobDocument({
  job,
  marks,
  activeIds,
  onActive,
}: {
  job: CompareJob | null;
  marks: MatchMark[];
  activeIds: string[];
  onActive: (ids: string[]) => void;
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

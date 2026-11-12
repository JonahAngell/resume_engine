import React from "react";

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** Run or re-run the AI reading of a posting, and say what it last found. Used on the Jobs page and in the Resume Editor. */
export default function AiAnalysisBar({
  analysis,
  pending,
  busy,
  running,
  onRun,
}: {
  analysis?: { current: boolean; model: string; analyzed_at: string; requirement_count: number } | null;
  pending?: number;
  busy: boolean;
  /** An analysis is running now. */
  running?: boolean;
  onRun: () => void;
}) {
  const stale = !!analysis && !analysis.current;
  return (
    <div className={`ai-analysis-bar${stale ? " stale" : ""}`}>
      <p>
        {!analysis
          ? "AI can read this posting for requirements the rules missed. Only the posting is sent, never your resume."
          : stale
            ? "The posting changed since the AI analysis. Run it again to use it."
            : `✦ AI analysis: ${analysis.requirement_count} requirements, ${formatDate(analysis.analyzed_at)}.`}
        {!!pending && !stale && ` ${pending} AI-found ${pending === 1 ? "requirement awaits" : "requirements await"} review.`}
      </p>
      <button type="button" className={analysis && !stale ? "" : "primary"} disabled={busy} onClick={onRun}>
        {running ? "Analysing…" : analysis ? "Re-analyse with AI" : "Analyse with AI"}
      </button>
    </div>
  );
}

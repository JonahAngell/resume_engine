import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import ScoreRing from "./ScoreRing";
import type { JobMatchState } from "./useJobMatch";
import type { AtsScore } from "./types";

export default function AtsTab({
  state,
  compositionId,
  revision,
  pageCount,
  onGoRequirements,
}: {
  state: JobMatchState;
  compositionId: string;
  revision: number;
  pageCount: number | null;
  onGoRequirements: () => void;
}) {
  const job = state.compareJob;
  const [score, setScore] = useState<AtsScore | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string[]>([]);
  const [showMethod, setShowMethod] = useState(false);
  const requested = useRef(false);

  const run = async () => {
    if (!job) return;
    requested.current = true;
    setLoading(true);
    setError("");
    try {
      setScore(
        await api<AtsScore>(`/api/job-descriptions/${job.id}/ats-score`, {
          method: "POST",
          body: JSON.stringify({ composition_id: compositionId, page_count: pageCount || null }),
        }),
      );
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    requested.current = false;
    setScore(null);
  }, [job?.id, compositionId]);

  // Once scored, keep the score current as the resume changes.
  useEffect(() => {
    if (requested.current) run();
  }, [revision, pageCount]);

  return (
    <div className="ats-tab">
      <div className="tab-intro">
        <p>
          Estimates how an applicant tracking system might rank this resume for {job ? <strong>{job.role || job.title}</strong> : "the job"}.
          Deterministic: the same resume always gets the same score.
        </p>
        {!score && (
          <button type="button" className="primary" disabled={loading || !job} onClick={run}>
            {loading ? "Scoring…" : "Score for ATS"}
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {score && (
        <>
          <div className="ats-summary">
            <ScoreRing value={score.score} label="ATS score" size={88} />
            <div>
              <p className={`ats-band band-${score.band.replace(" ", "-").toLowerCase()}`}>{score.band}</p>
              <p className="ai-meta">
                Out of 100{loading ? " · updating…" : ""}
              </p>
              <button type="button" className="link-button" disabled={loading} onClick={run}>
                Re-score
              </button>
            </div>
          </div>
          <ul className="ats-components">
            {score.components.map((item) => {
              const expanded = open.includes(item.id);
              return (
                <li key={item.id} className={expanded ? "open" : ""}>
                  <button
                    type="button"
                    className="ats-row"
                    aria-expanded={expanded}
                    onClick={() =>
                      setOpen((current) => (expanded ? current.filter((id) => id !== item.id) : [...current, item.id]))
                    }
                  >
                    <span className="ats-label">{item.label}</span>
                    <span className="ats-meter" aria-hidden="true">
                      <span style={{ width: `${Math.round(item.ratio * 100)}%` }} />
                    </span>
                    <span className="ats-points">
                      {Number.isInteger(item.earned) ? item.earned : item.earned.toFixed(1)}/{item.weight}
                    </span>
                  </button>
                  {expanded && (
                    <div className="ats-detail">
                      <p>{item.detail}</p>
                      {item.tips.length > 0 && (
                        <ul>
                          {item.tips.map((tip) => (
                            <li key={tip}>{tip}</li>
                          ))}
                        </ul>
                      )}
                      {(item.id === "keywords" || item.id === "requirements") && item.ratio < 1 && (
                        <button type="button" className="link-button" onClick={onGoRequirements}>
                          See missing requirements
                        </button>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          <button type="button" className="link-button" aria-expanded={showMethod} onClick={() => setShowMethod(!showMethod)}>
            {showMethod ? "Hide" : "How this score is calculated"}
          </button>
          {showMethod && (
            <table className="ats-method">
              <thead>
                <tr>
                  <th scope="col">Component</th>
                  <th scope="col">Points</th>
                  <th scope="col">Rule</th>
                </tr>
              </thead>
              <tbody>
                {score.methodology.map((item) => (
                  <tr key={item.id}>
                    <th scope="row">{item.label}</th>
                    <td>{item.weight}</td>
                    <td>
                      {item.rule}
                      <span className="ats-why">{item.why}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      <p className="ats-disclaimer" role="note">
        {score?.disclaimer ||
          "This is an estimate modeled on how common applicant tracking systems parse and rank resumes. Employers configure their systems differently, so your score in an employer's system may differ. It is not a guarantee of ranking or interview."}
      </p>
    </div>
  );
}

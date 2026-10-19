import React, { useEffect, useState } from "react";
import ChoiceList from "../ChoiceList";
import AtsTab from "./AtsTab";
import CoachTab from "./CoachTab";
import RequirementsTab, { RowActions, rowIds, rowKey } from "./RequirementsTab";
import ScoreRing from "./ScoreRing";
import type { JobMatchState } from "./useJobMatch";
import {
  groupLabel,
  headlineScore,
  type AssistRequest,
  type DashboardTab,
  type EligibilityGate,
  type JobMatch,
  type ScoreComponents,
} from "./types";

const TABS: [DashboardTab, string][] = [
  ["overview", "Overview"],
  ["requirements", "Requirements"],
  ["coach", "AI suggestions"],
  ["ats", "ATS score"],
];

const SCORE_LABELS: [keyof ScoreComponents, string][] = [
  ["required_coverage", "Required coverage"],
  ["preferred_coverage", "Preferred coverage"],
  ["responsibility_alignment", "Responsibility alignment"],
  ["domain_alignment", "Domain alignment"],
  ["tools_alignment", "Tools alignment"],
  ["evidence_quality", "Evidence quality"],
];

const GATE_LABELS: [string, string][] = [
  ["degree", "Degree"],
  ["years", "Years"],
  ["certification", "Certification"],
  ["schedule", "Schedule"],
  ["travel", "Travel"],
  ["work_location", "Location"],
  ["employment_type", "Employment"],
];

function keywordCounts(match: JobMatch) {
  const rows = [...match.required, ...match.preferred];
  return {
    found: rows.reduce((sum, row) => sum + row.keywords.filter((item) => item.found).length, 0),
    total: rows.reduce((sum, row) => sum + row.keywords.length, 0),
  };
}

function Overview({
  match,
  state,
  onTab,
  onFocus,
  onActive,
  onAssist,
}: {
  match: JobMatch;
  state: JobMatchState;
  onTab: (tab: DashboardTab) => void;
  onFocus: (key: string) => void;
  onActive: (ids: string[]) => void;
  onAssist: (request: AssistRequest) => void;
}) {
  const gaps = [...match.required, ...match.preferred]
    .filter((row) => !row.matched)
    .sort((left, right) => (left.group === right.group ? (right.weight || 0) - (left.weight || 0) : left.group === "required" ? -1 : 1))
    .slice(0, 3);
  const gates = GATE_LABELS.filter(([key]) => (match.eligibility?.[key]?.status || "not_stated") !== "not_stated");
  return (
    <div className="overview-tab">
      <section className="dash-card" aria-label="Top gaps">
        <h3>Top gaps</h3>
        {gaps.length === 0 ? (
          <p className="empty-state small">Every listed requirement is matched.</p>
        ) : (
          <ul className="gap-list">
            {gaps.map((row) => (
              <li key={rowKey(row)} onMouseEnter={() => onActive(rowIds(row))} onMouseLeave={() => onActive([])}>
                <div className="gap-head">
                  <span className={`badge group-${row.group}`}>{groupLabel(row.group)}</span>
                  <button type="button" className="link-button gap-title" onClick={() => onFocus(rowKey(row))}>
                    {row.keywords.map((item) => item.keyword).join(", ") || row.label || row.text}
                  </button>
                </div>
                <p className="gap-text">{row.text}</p>
                <RowActions row={row} state={state} onAssist={onAssist} compact />
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="dash-card" aria-label="Next steps">
        <h3>Next steps</h3>
        <div className="next-steps">
          <button type="button" onClick={() => onTab("coach")}>
            <strong>Get AI suggestions</strong>
            <span>Review the whole resume against this job.</span>
          </button>
          <button type="button" onClick={() => onTab("ats")}>
            <strong>Score for ATS</strong>
            <span>See how an applicant tracking system might rank it.</span>
          </button>
        </div>
      </section>
      {match.scores && (
        <section className="dash-card" aria-label="Score breakdown">
          <h3>Score breakdown</h3>
          <dl className="bar-list">
            {SCORE_LABELS.map(([key, label]) => {
              const value = Math.round((match.scores?.[key] || 0) * 100);
              return (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>
                    <span className="bar" aria-hidden="true">
                      <span style={{ width: `${value}%` }} />
                    </span>
                    <span>{value}%</span>
                  </dd>
                </div>
              );
            })}
          </dl>
        </section>
      )}
      {gates.length > 0 && (
        <section className="dash-card" aria-label="Eligibility">
          <h3>Eligibility</h3>
          <ul className="gate-list">
            {gates.map(([key, label]) => {
              const gate = match.eligibility?.[key] as EligibilityGate;
              return (
                <li key={key} className={`gate-${gate.status}`} title={gate.detail || undefined}>
                  <span>{label}</span>
                  <strong>{gate.status}</strong>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}

export type BuiltSummary = {
  status: string;
  detail: string;
  method: "ai" | "keywords";
  entry_count: number;
  bullet_count: number;
  entries: { section: string; label: string; bullets: number; reason: string }[];
};

function BuiltBanner({
  built,
  jobTitle,
  onDismiss,
}: {
  built: BuiltSummary;
  jobTitle: string;
  onDismiss?: () => void;
}) {
  const plural = (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;
  return (
    <section className="ai-built-banner" aria-label="How this resume was built">
      <p>
        <strong>
          {built.method === "ai" ? "Built with AI" : "Built by keyword match"}
          {jobTitle ? ` for ${jobTitle}` : ""}
        </strong>
        : {plural(built.entry_count, "entry", "entries")} and {plural(built.bullet_count, "bullet")} from your
        library. See the suggestions below for ways to strengthen the match.
      </p>
      {built.detail && <p>{built.detail}</p>}
      {built.entries.length > 0 && (
        <details>
          <summary>What was included</summary>
          <ul>
            {built.entries.map((entry, index) => (
              <li key={index}>
                {entry.label} · {plural(entry.bullets, "bullet")}
                {entry.reason ? ` — ${entry.reason}` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
      {onDismiss && (
        <div className="banner-actions">
          <button type="button" onClick={onDismiss}>
            Dismiss
          </button>
        </div>
      )}
    </section>
  );
}

export default function MatchDashboard({
  state,
  compositionId,
  revision,
  summaryVariantId,
  pageCount,
  tab,
  onTab,
  focus,
  onFocus,
  onActive,
  onAssist,
  onApplied,
  autoCoach = false,
  onAutoCoachDone,
  built = null,
  onDismissBuilt,
}: {
  state: JobMatchState;
  compositionId: string;
  revision: number;
  summaryVariantId: string | null;
  pageCount: number | null;
  tab: DashboardTab;
  onTab: (tab: DashboardTab) => void;
  focus: { key: string; nonce: number } | null;
  onFocus: (key: string) => void;
  onActive: (ids: string[]) => void;
  onAssist: (request: AssistRequest) => void;
  onApplied: (composition: any) => void;
  autoCoach?: boolean;
  onAutoCoachDone?: () => void;
  built?: BuiltSummary | null;
  onDismissBuilt?: () => void;
}) {
  const { match, jobs, loaded, jobId, error, selected } = state;
  const counts = match ? keywordCounts(match) : null;
  const [picking, setPicking] = useState(false);
  useEffect(() => setPicking(false), [jobId]);
  const tabs = match ? (
    <div className="dash-tabs" role="tablist" aria-label="Job match views">
      {TABS.map(([value, label]) => (
        <button
          key={value}
          type="button"
          role="tab"
          id={`dash-tab-${value}`}
          aria-selected={tab === value}
          aria-controls={`dash-panel-${value}`}
          className={tab === value ? "active" : ""}
          onClick={() => onTab(value)}
        >
          {label}
        </button>
      ))}
    </div>
  ) : null;
  return (
    <section className="match-dashboard" aria-label="Job match">
      <header className="dash-header">
        <div className="dash-picker">
          <span className="dash-eyebrow">Job match</span>
          {selected && !picking ? (
            <div className="dash-job">
              <strong title={selected.title}>{selected.title}</strong>
              <button type="button" className="link-button" onClick={() => setPicking(true)}>
                Change
              </button>
            </div>
          ) : loaded && jobs.length > 0 ? (
            <ChoiceList
              label="Job description"
              search="always"
              value={jobId}
              noMatch="No matching job descriptions."
              options={jobs.map((job) => ({ value: job.id, label: job.title }))}
              onChange={state.setJobId}
            />
          ) : null}
        </div>
        {match && counts && (
          <div className="dash-score">
            <ScoreRing value={headlineScore(match)} label="Match score" />
            <div className="dash-stats">
              <button type="button" onClick={() => onTab("requirements")}>
                <strong>
                  {match.required_matched}/{match.required_count}
                </strong>
                <span>Required</span>
              </button>
              <button type="button" onClick={() => onTab("requirements")}>
                <strong>
                  {match.preferred_matched}/{match.preferred_count}
                </strong>
                <span>Preferred</span>
              </button>
              <button type="button" onClick={() => onTab("requirements")}>
                <strong>
                  {counts.found}/{counts.total}
                </strong>
                <span>Keywords</span>
              </button>
            </div>
            <p className="dash-note">Match score: deterministic, never changed by AI.</p>
          </div>
        )}
        {tabs}
      </header>
      {error && (
        <div role="alert" className="error">
          {error}
          <button type="button" onClick={() => state.setError("")}>
            Dismiss
          </button>
        </div>
      )}
      {built && <BuiltBanner built={built} jobTitle={selected?.title || ""} onDismiss={onDismissBuilt} />}
      {!loaded ? (
        <p className="empty-state">Loading…</p>
      ) : jobs.length === 0 ? (
        <p className="empty-state">Save a job description on the Jobs page, then choose it here.</p>
      ) : !jobId ? (
        <p className="empty-state">Choose a job description to compare with this resume.</p>
      ) : !match ? (
        <p className="empty-state">{error ? "This resume could not be compared." : "Comparing this resume…"}</p>
      ) : (
        <>
          {/* Panels stay mounted so AI suggestions and the ATS score survive tab switches. */}
          <div className="dash-panel" role="tabpanel" id="dash-panel-overview" aria-labelledby="dash-tab-overview" hidden={tab !== "overview"}>
            <Overview match={match} state={state} onTab={onTab} onFocus={onFocus} onActive={onActive} onAssist={onAssist} />
          </div>
          <div className="dash-panel" role="tabpanel" id="dash-panel-requirements" aria-labelledby="dash-tab-requirements" hidden={tab !== "requirements"}>
            <RequirementsTab match={match} state={state} focus={focus} onActive={onActive} onAssist={onAssist} />
          </div>
          <div className="dash-panel" role="tabpanel" id="dash-panel-coach" aria-labelledby="dash-tab-coach" hidden={tab !== "coach"}>
            <CoachTab
              state={state}
              compositionId={compositionId}
              revision={revision}
              summaryVariantId={summaryVariantId}
              onApplied={onApplied}
              onAssist={onAssist}
              onActive={onActive}
              autoRun={autoCoach}
              onAutoRunDone={onAutoCoachDone}
            />
          </div>
          <div className="dash-panel" role="tabpanel" id="dash-panel-ats" aria-labelledby="dash-tab-ats" hidden={tab !== "ats"}>
            <AtsTab
              state={state}
              compositionId={compositionId}
              revision={revision}
              pageCount={pageCount}
              onGoRequirements={() => onTab("requirements")}
            />
          </div>
        </>
      )}
    </section>
  );
}

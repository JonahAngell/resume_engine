import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";
import ChoiceList from "./ChoiceList";
import { activeIdsForTerms, buildMatchMarks, type CompareJob, type MatchMark } from "./matchMarks";

type AddedRequirement = {
  group: "required" | "preferred";
  text: string;
};

type KeywordReview = {
  dismissed: string[];
  added: AddedRequirement[];
  matched: string[];
};

type JobDescription = {
  id: string;
  company: string;
  role: string;
  title: string;
  body: string;
  composition_id: string | null;
  keyword_review?: KeywordReview;
};

type KeywordEvidence = {
  source_requirement: string;
  matched_text: string;
  relation: string;
  section: string;
  confidence: number;
  explanation: string;
};

type RequirementKeyword = {
  keyword: string;
  found: boolean;
  where?: string;
  relation?: string;
  evidence?: KeywordEvidence | null;
};

type TagSuggestion = {
  keyword: string;
  bullet_id: string | null;
  bullet_excerpt: string;
  section: string;
  suggestion: string;
  line_id?: string;
};

function rowIds(row: Pick<RequirementRow, "kind" | "category" | "label" | "keywords">) {
  if (row.kind === "education" || row.kind === "degree" || row.category === "degree") {
    return activeIdsForTerms([row.label || ""]);
  }
  return activeIdsForTerms(row.keywords.map((item) => item.keyword));
}

function chipClass(item: Pick<RequirementKeyword, "found" | "relation">) {
  if (item.found) return "keyword-chip";
  if (item.relation === "cluster" || item.relation === "combination") return "keyword-chip related";
  return "keyword-chip missing";
}

const CATEGORY_LABEL: Record<string, string> = {
  tool: "Tools",
  domain: "Domain",
  methodology: "Methods",
  responsibility: "Responsibilities",
  soft_skill: "Soft skills",
  skill: "Skills",
  degree: "Education",
  education: "Education",
};

function groupedRows(rows: RequirementRow[]) {
  const order = ["tool", "domain", "methodology", "responsibility", "soft_skill", "skill"];
  const buckets = new Map<string, RequirementRow[]>();
  for (const row of rows) {
    const key = row.category || row.kind || "skill";
    buckets.set(key, [...(buckets.get(key) || []), row]);
  }
  return [...buckets.keys()]
    .sort((left, right) => {
      const leftIndex = order.indexOf(left);
      const rightIndex = order.indexOf(right);
      return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex);
    })
    .map((key) => [CATEGORY_LABEL[key] || key, buckets.get(key) || []] as const);
}

type RequirementRow = {
  text: string;
  group: string;
  kind?: string;
  category?: string;
  section?: string;
  weight?: number;
  label?: string;
  match_mode?: "any" | "all";
  matched: boolean;
  manual?: boolean;
  detail?: string;
  keywords: RequirementKeyword[];
  suggestions: TagSuggestion[];
};

type ScoreComponents = {
  required_coverage: number;
  preferred_coverage: number;
  responsibility_alignment: number;
  domain_alignment: number;
  tools_alignment: number;
  evidence_quality: number;
};

type EligibilityGate = {
  status: "pass" | "fail" | "unknown" | "not_stated";
  detail: string;
};

type JobMatch = {
  composition_id: string;
  required_count: number;
  required_matched: number;
  preferred_count: number;
  preferred_matched: number;
  required: RequirementRow[];
  preferred: RequirementRow[];
  responsibilities?: RequirementRow[];
  eligibility_rows?: RequirementRow[];
  scores?: ScoreComponents;
  eligibility?: Record<string, EligibilityGate>;
  families?: { id: string; label: string; confidence: number }[];
};

type QualGroup = "required" | "preferred" | "responsibilities" | "keywords";

type AiReview = {
  status: "ok" | "unavailable" | "rate_limited" | "invalid";
  detail: string;
  model: string;
  families: { label: string; confidence: number }[];
  requirements: { text: string; group: string; category: string; source_span: string }[];
  keywords: { keyword: string; category: string; source_span: string }[];
  semantic_candidates: {
    requirement: string;
    resume_span: string;
    section: string;
    confidence: number;
    rationale: string;
  }[];
  bullet_tags: {
    bullet: string;
    section: string;
    action: string;
    domain: string;
    skill: string;
    tool: string;
    outcome: string;
    metric: string;
  }[];
  suggestions: { requirement: string; resume_quote: string; suggestion: string }[];
};

const CATEGORY_LABELS: Record<string, string> = {
  tool: "Tool",
  domain: "Domain",
  responsibility: "Responsibility",
  methodology: "Methodology",
  credential: "Credential",
  degree: "Degree",
  experience_duration: "Experience duration",
  soft_skill: "Soft skill",
};

function categoryLabel(category: string) {
  return CATEGORY_LABELS[category] || category;
}

function findRequirement(match: JobMatch, text: string) {
  const key = text.trim().toLowerCase();
  return [...match.required, ...match.preferred, ...(match.responsibilities || [])].find(
    (row) => row.text.trim().toLowerCase() === key,
  );
}

function tagPairs(tags: AiReview["bullet_tags"][number]) {
  return (
    [
      ["Action", tags.action],
      ["Domain", tags.domain],
      ["Skill", tags.skill],
      ["Tool", tags.tool],
      ["Outcome", tags.outcome],
      ["Metric", tags.metric],
    ] as const
  ).filter(([, value]) => value);
}

function AiReviewBody({
  review,
  match,
  busy,
  onMark,
}: {
  review: AiReview;
  match: JobMatch;
  busy: boolean;
  onMark: (row: RequirementRow) => void;
}) {
  const empty =
    review.families.length === 0 &&
    review.requirements.length === 0 &&
    review.keywords.length === 0 &&
    review.semantic_candidates.length === 0 &&
    review.bullet_tags.length === 0 &&
    review.suggestions.length === 0;
  return (
    <div className="ai-review-body">
      {review.status !== "ok" && <p className="ai-meta">{review.detail}</p>}
      {review.status === "ok" && empty && (
        <p className="ai-meta">The model did not add anything beyond the current match.</p>
      )}
      {review.families.length > 0 && (
        <div>
          <h3>Job families</h3>
          <p className="job-families">
            {review.families.map((family) => (
              <span className="fact-badge location" key={family.label}>
                {family.label}
              </span>
            ))}
          </p>
        </div>
      )}
      {review.requirements.length > 0 && (
        <div>
          <h3>Requirement categories</h3>
          <ul>
            {review.requirements.map((row) => (
              <li key={`${row.group}-${row.text}`}>
                <strong>{categoryLabel(row.category)}. </strong>
                {row.text}
              </li>
            ))}
          </ul>
        </div>
      )}
      {review.keywords.length > 0 && (
        <div>
          <h3>Keywords</h3>
          <ul>
            {review.keywords.map((row) => (
              <li key={row.keyword}>
                <strong>{row.keyword}. </strong>
                {categoryLabel(row.category)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {review.semantic_candidates.length > 0 && (
        <div>
          <h3>Possible equivalents</h3>
          <ul>
            {review.semantic_candidates.map((row) => {
              const requirement = findRequirement(match, row.requirement);
              return (
                <li key={row.requirement}>
                  <p>
                    <strong>{row.requirement}. </strong>
                    {row.rationale} {Math.round(row.confidence * 100)}% confidence.
                  </p>
                  <p>“{row.resume_span}”</p>
                  {requirement && !requirement.matched && (
                    <button type="button" disabled={busy} onClick={() => onMark(requirement)}>
                      Mark as a match
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {review.bullet_tags.length > 0 && (
        <div>
          <h3>Bullet tags</h3>
          <ul>
            {review.bullet_tags.map((row) => (
              <li key={row.bullet}>
                <p>{row.bullet}</p>
                <p>{tagPairs(row).map(([label, value]) => `${label}: ${value}`).join(" · ")}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
      {review.suggestions.length > 0 && (
        <div>
          <h3>Rewrite suggestions</h3>
          <ul>
            {review.suggestions.map((row) => (
              <li key={`${row.requirement}-${row.resume_quote}`}>
                <p>
                  <strong>{row.requirement}. </strong>
                  {row.suggestion}
                </p>
                <p>“{row.resume_quote}”</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SuggestionOptions({
  suggestions,
  busy,
  activeIds,
  onAddTag,
  onActive,
}: {
  suggestions: TagSuggestion[];
  busy: boolean;
  activeIds: string[];
  onAddTag: (bulletId: string, keyword: string) => void;
  onActive: (ids: string[]) => void;
}) {
  return suggestions.map((suggestion, suggestionIndex) => (
    <div
      className="jobs-suggestion"
      key={`${suggestion.keyword}-${suggestion.line_id || suggestionIndex}`}
      onMouseEnter={(event) => {
        event.stopPropagation();
        onActive(activeIdsForTerms([suggestion.keyword]));
      }}
      onMouseLeave={() => onActive(activeIds)}
    >
      <p>
        {suggestion.keyword && <strong>{suggestion.keyword}. </strong>}
        {suggestion.suggestion}
      </p>
      {suggestion.bullet_excerpt && <p>“{suggestion.bullet_excerpt}”</p>}
      {suggestion.bullet_id && suggestion.keyword && (
        <button
          type="button"
          disabled={busy}
          onClick={() => onAddTag(suggestion.bullet_id as string, suggestion.keyword)}
        >
          Add tag
        </button>
      )}
    </div>
  ));
}

function QualStat({
  label,
  matched,
  count,
  noun,
  pressed,
  onClick,
}: {
  label: string;
  matched: number;
  count: number;
  noun: string;
  pressed: boolean;
  onClick: () => void;
}) {
  const pct = count ? Math.round((matched / count) * 100) : 0;
  const complete = count > 0 && matched === count;
  return (
    <button
      type="button"
      className={`qual-stat ${complete ? "ok" : count ? "partial" : ""} ${pressed ? "selected" : ""}`}
      aria-pressed={pressed}
      aria-expanded={pressed}
      onClick={onClick}
    >
      <div className="qual-stat-top">
        <span>{label}</span>
        <strong>{count ? `${matched}/${count}` : "—"}</strong>
      </div>
      <div className="qual-meter" aria-hidden="true">
        <span style={{ width: `${pct}%` }} />
      </div>
      <span className="qual-stat-note">
        {count ? `${pct}% of ${noun} matched` : `No ${noun}`}
      </span>
    </button>
  );
}

function RequirementList({
  title,
  rows,
  busy,
  onDismiss,
  onMark,
  onAddTag,
  onActive,
}: {
  title: string;
  rows: RequirementRow[];
  busy: boolean;
  onDismiss: (row: RequirementRow) => void;
  onMark: (row: RequirementRow) => void;
  onAddTag: (bulletId: string, keyword: string) => void;
  onActive: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const matched = rows.filter((row) => row.matched).length;
  const groups = groupedRows(rows);
  return (
    <section className="qual-group" aria-label={title}>
      <h3>
        {title}
        <span>
          {matched} matched, {rows.length - matched} missing
        </span>
      </h3>
      {rows.length === 0 ? (
        <p>None found in this description.</p>
      ) : (
        groups.map(([name, items]) => (
          <div key={name}>
            <h4 className="qual-kind">{name}</h4>
            <ul className="requirement-list">
              {items.map((row) => {
                const key = `${row.group}:${row.kind || "skill"}:${row.text}`;
                const expanded = !!open[key];
                const panelId = `qual-${row.group}-${name}-${items.indexOf(row)}`;
                const status = row.manual ? "Marked" : row.matched ? "Matched" : "Missing";
                return (
                  <li
                    className={`requirement-row ${row.matched ? "matched" : "missing"} ${expanded ? "open" : ""}`}
                    key={key}
                    onMouseEnter={() => onActive(rowIds(row))}
                    onMouseLeave={() => onActive([])}
                  >
                    <button
                      type="button"
                      className="qual-toggle"
                      aria-expanded={expanded}
                      aria-controls={panelId}
                      onClick={() => setOpen((current) => ({ ...current, [key]: !current[key] }))}
                    >
                      <span className="qual-chevron" aria-hidden="true" />
                      <span className="qual-keywords">
                        {row.match_mode === "any" && row.keywords.length > 1 && (
                          <span className="qual-any">Any of</span>
                        )}
                        {row.keywords.length > 0 ? (
                          row.keywords.map((item) => (
                            <span className={chipClass(item)} key={item.keyword} title={item.evidence?.explanation || ""}>
                              {item.keyword}
                            </span>
                          ))
                        ) : (
                          <span className="qual-label">{row.label || row.text}</span>
                        )}
                      </span>
                      <span className="requirement-status">{status}</span>
                    </button>
                    {expanded && (
                      <div className="qual-detail" id={panelId}>
                        <p>{row.text}</p>
                        {(row.kind === "education" || row.kind === "degree") && row.detail && <p>{row.detail}</p>}
                        {row.keywords
                          .filter((item) => item.evidence && !item.found)
                          .map((item) => (
                            <p key={item.keyword}>{item.evidence?.explanation}</p>
                          ))}
                        {!row.matched && (
                          <SuggestionOptions
                            suggestions={row.suggestions}
                            busy={busy}
                            activeIds={rowIds(row)}
                            onAddTag={onAddTag}
                            onActive={onActive}
                          />
                        )}
                        <div className="qual-actions">
                          <button type="button" disabled={busy} onClick={() => onMark(row)}>
                            {row.manual ? "Clear match" : "Mark as a match"}
                          </button>
                          <button
                            type="button"
                            className="danger-text"
                            disabled={busy}
                            onClick={() => onDismiss(row)}
                          >
                            Dismiss
                          </button>
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}

function KeywordMatchList({
  rows,
  busy,
  onAddTag,
  onActive,
}: {
  rows: RequirementRow[];
  busy: boolean;
  onAddTag: (bulletId: string, keyword: string) => void;
  onActive: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [filter, setFilter] = useState<"all" | "matched" | "missing">("all");
  const keywords = rows
    .flatMap((row) =>
      row.keywords.map((item) => ({
        ...item,
        group: row.group,
        kind: row.kind,
        detail: row.detail,
        requirement: row.text,
        suggestions: row.suggestions.filter((suggestion) => suggestion.keyword === item.keyword),
      })),
    )
    .sort((left, right) => Number(right.found) - Number(left.found));
  const found = keywords.filter((item) => item.found).length;
  const visible = keywords.filter((item) =>
    filter === "matched" ? item.found : filter === "missing" ? !item.found : true,
  );
  return (
    <section className="qual-group" aria-label="Keywords">
      <h3>
        Keywords
        <span>
          {found} matched, {keywords.length - found} missing
        </span>
      </h3>
      <div className="qual-filters" role="group" aria-label="Filter keywords">
        {(
          [
            ["all", "All"],
            ["matched", "Matched"],
            ["missing", "Missing"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={filter === value ? "active" : ""}
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {keywords.length === 0 ? (
        <p>No keywords were found in these qualifications.</p>
      ) : visible.length === 0 ? (
        <p>{filter === "matched" ? "No matched keywords." : "No missing keywords."}</p>
      ) : (
        <ul className="requirement-list">
          {visible.map((item) => {
            const key = `${item.group}:${item.keyword}:${item.requirement}`;
            const expanded = !!open[key];
            return (
              <li
                className={`requirement-row ${item.found ? "matched" : "missing"} ${expanded ? "open" : ""}`}
                key={key}
                onMouseEnter={() => onActive(activeIdsForTerms([item.keyword]))}
                onMouseLeave={() => onActive([])}
              >
                <button
                  type="button"
                  className="qual-toggle"
                  aria-expanded={expanded}
                  onClick={() => setOpen((current) => ({ ...current, [key]: !current[key] }))}
                >
                  <span className="qual-chevron" aria-hidden="true" />
                  <span className="qual-keywords">
                    <span className={chipClass(item)} title={item.evidence?.explanation || ""}>
                      {item.keyword}
                    </span>
                  </span>
                  <span className="requirement-status">{item.found ? "Matched" : "Missing"}</span>
                </button>
                {expanded && (
                  <div className="qual-detail">
                    <p>{item.requirement}</p>
                    {!item.found && (
                      <SuggestionOptions
                        suggestions={item.suggestions}
                        busy={busy}
                        activeIds={activeIdsForTerms([item.keyword])}
                        onAddTag={onAddTag}
                        onActive={onActive}
                      />
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

const SCORE_LABELS: [keyof ScoreComponents, string][] = [
  ["required_coverage", "Required coverage"],
  ["preferred_coverage", "Preferred coverage"],
  ["responsibility_alignment", "Responsibility alignment"],
  ["domain_alignment", "Domain alignment"],
  ["tools_alignment", "Tools alignment"],
  ["evidence_quality", "Evidence quality"],
];

function ScoreBoard({ scores }: { scores: ScoreComponents }) {
  return (
    <dl className="score-board">
      {SCORE_LABELS.map(([key, label]) => (
        <div key={key}>
          <dt>{label}</dt>
          <dd>{Math.round((scores[key] || 0) * 100)}%</dd>
        </div>
      ))}
    </dl>
  );
}

const GATE_LABELS: [string, string][] = [
  ["degree", "Degree"],
  ["years", "Years"],
  ["certification", "Certification"],
  ["schedule", "Schedule"],
  ["travel", "Travel"],
  ["work_location", "Location"],
  ["employment_type", "Employment"],
];

function EligibilityStrip({ eligibility }: { eligibility: Record<string, EligibilityGate> }) {
  return (
    <ul className="eligibility-strip">
      {GATE_LABELS.map(([key, label]) => {
        const gate = eligibility[key] || { status: "not_stated", detail: "" };
        const status = gate.status === "not_stated" ? "not stated" : gate.status;
        return (
          <li className={gate.status} key={key} title={gate.detail || undefined}>
            <span>{label}</span>
            <strong>{status}</strong>
          </li>
        );
      })}
    </ul>
  );
}

export default function JobMatchPanel({
  compositionId,
  revision,
  linkedJobId,
  reloadLibrary,
  active,
  onCompare,
  onActive,
}: {
  compositionId: string;
  revision: number;
  linkedJobId: string;
  reloadLibrary: () => Promise<void> | void;
  active: boolean;
  onCompare: (view: { job: CompareJob | null; marks: MatchMark[] }) => void;
  onActive: (ids: string[]) => void;
}) {
  const [jobs, setJobs] = useState<JobDescription[]>([]);
  const [jobId, setJobId] = useState("");
  const [match, setMatch] = useState<JobMatch | null>(null);
  const [qualGroup, setQualGroup] = useState<QualGroup | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [matchGeneration, setMatchGeneration] = useState(0);
  const [ai, setAi] = useState<AiReview | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const request = useRef(0);
  const manual = useRef(false);
  const selected = jobs.find((job) => job.id === jobId) || null;

  useEffect(() => {
    manual.current = false;
    setJobId("");
    setMatch(null);
    setQualGroup(null);
  }, [compositionId]);

  useEffect(() => {
    let cancelled = false;
    api<JobDescription[]>("/api/job-descriptions")
      .then((rows) => {
        if (!cancelled) {
          setJobs(rows);
          setLoaded(true);
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) {
          setError(reason.message);
          setLoaded(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (manual.current || jobs.length === 0) return;
    setJobId(jobs.some((job) => job.id === linkedJobId) ? linkedJobId : "");
  }, [jobs, compositionId, linkedJobId]);

  useEffect(() => {
    onActive([]);
  }, [active, qualGroup, jobId, onActive]);

  useEffect(() => {
    if (!active || !selected) {
      onCompare({ job: null, marks: [] });
      return;
    }
    onCompare({
      job: {
        id: selected.id,
        title: selected.title,
        company: selected.company,
        role: selected.role,
        body: selected.body,
      },
      marks: match
        ? buildMatchMarks([
            ...match.required,
            ...match.preferred,
            ...(match.responsibilities || []),
            ...(match.eligibility_rows || []),
          ])
        : [],
    });
  }, [active, selected, match, onCompare]);

  useEffect(() => {
    setMatch(null);
    setQualGroup(null);
    setAi(null);
  }, [jobId]);

  useEffect(() => {
    setAi(null);
  }, [compositionId, revision]);

  useEffect(() => {
    if (!active || !jobId) return;
    const token = ++request.current;
    let cancelled = false;
    api<JobMatch>(`/api/job-descriptions/${jobId}/match`, {
      method: "POST",
      body: JSON.stringify({ composition_id: compositionId }),
    })
      .then((result) => {
        if (!cancelled && token === request.current) setMatch(result);
      })
      .catch((reason: Error) => {
        if (!cancelled && token === request.current) setError(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, [active, jobId, compositionId, revision, matchGeneration]);

  const reviewOf = (job: JobDescription): KeywordReview => ({
    dismissed: job.keyword_review?.dismissed || [],
    added: job.keyword_review?.added || [],
    matched: job.keyword_review?.matched || [],
  });

  const saveReview = async (review: KeywordReview) => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const saved = await api<JobDescription>(`/api/job-descriptions/${selected.id}`, {
        method: "PUT",
        body: JSON.stringify({
          company: selected.company,
          role: selected.role,
          title: selected.title,
          body: selected.body,
          composition_id: compositionId,
          keyword_review: review,
        }),
      });
      setJobs((rows) => rows.map((row) => (row.id === saved.id ? saved : row)));
      setMatchGeneration((value) => value + 1);
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  };

  const dismissRequirement = (row: RequirementRow) => {
    if (!selected) return;
    const review = reviewOf(selected);
    if (review.dismissed.some((text) => text.trim().toLowerCase() === row.text.trim().toLowerCase()))
      return;
    saveReview({ ...review, dismissed: [...review.dismissed, row.text] });
  };

  const markRequirement = (row: RequirementRow) => {
    if (!selected) return;
    const review = reviewOf(selected);
    const key = row.text.trim().toLowerCase();
    const marked = review.matched.some((text) => text.trim().toLowerCase() === key);
    saveReview({
      ...review,
      matched: marked
        ? review.matched.filter((text) => text.trim().toLowerCase() !== key)
        : [...review.matched, row.text],
    });
  };

  const runAiReview = async () => {
    if (!jobId) return;
    setAiBusy(true);
    setError("");
    try {
      const result = await api<AiReview>(`/api/job-descriptions/${jobId}/ai-review`, {
        method: "POST",
        body: JSON.stringify({ composition_id: compositionId }),
      });
      setAi(result);
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setAiBusy(false);
    }
  };

  const addTag = async (bulletId: string, keyword: string) => {
    if (!selected || !keyword) return;
    setBusy(true);
    setError("");
    try {
      await api("/api/library-management/bulk", {
        method: "POST",
        body: JSON.stringify({
          ids: [bulletId],
          action: "add-tags",
          tag_names: [keyword],
        }),
      });
      await reloadLibrary();
      setMatchGeneration((value) => value + 1);
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="job-match-panel" aria-label="Job match">
      <h2>Job match</h2>
      <p className="job-match-intro">
        Choose a saved job description to see how this resume covers it.
      </p>
      {error && (
        <div role="alert" className="error">
          {error}
          <button onClick={() => setError("")}>Dismiss</button>
        </div>
      )}
      <div className="choice-field">
        <span>Job description</span>
        {loaded && jobs.length > 0 && (
          <ChoiceList
            label="Job description"
            search="always"
            value={jobId}
            noMatch="No matching job descriptions."
            options={jobs.map((job) => ({ value: job.id, label: job.title }))}
            onChange={(next) => {
              manual.current = true;
              setJobId(next);
              setError("");
            }}
          />
        )}
      </div>
      {!loaded ? (
        <p>Loading…</p>
      ) : jobs.length === 0 ? (
        <p>Save a job description on the Jobs page, then choose it here.</p>
      ) : !jobId ? (
        <p>Choose a job description to compare with this resume.</p>
      ) : !match ? (
        <p>{error ? "This resume could not be compared." : "Comparing this resume…"}</p>
      ) : (
        <>
          {(match.families || []).length > 0 && (
            <p className="job-families">
              {(match.families || []).map((family) => (
                <span className="fact-badge location" key={family.id}>
                  {family.label}
                </span>
              ))}
            </p>
          )}
          {match.scores && <ScoreBoard scores={match.scores} />}
          {match.eligibility && <EligibilityStrip eligibility={match.eligibility} />}
          <div className="ai-review">
            <button type="button" onClick={runAiReview} disabled={aiBusy || busy}>
              {aiBusy ? "Reviewing…" : "Review with AI"}
            </button>
            {ai && (
              <AiReviewBody review={ai} match={match} busy={busy || aiBusy} onMark={markRequirement} />
            )}
          </div>
          {match.required_count === 0 &&
            match.preferred_count === 0 &&
            (match.responsibilities || []).length === 0 && (
            <p>No qualifications were found.</p>
          )}
          {(match.required_count > 0 ||
            match.preferred_count > 0 ||
            (match.responsibilities || []).length > 0) && (
            <div className="qual-board">
              <div className="qual-stats">
                <QualStat
                  label="Required"
                  matched={match.required_matched}
                  count={match.required_count}
                  noun="required"
                  pressed={qualGroup === "required"}
                  onClick={() =>
                    setQualGroup((current) => (current === "required" ? null : "required"))
                  }
                />
                <QualStat
                  label="Preferred"
                  matched={match.preferred_matched}
                  count={match.preferred_count}
                  noun="preferred"
                  pressed={qualGroup === "preferred"}
                  onClick={() =>
                    setQualGroup((current) =>
                      current === "preferred" ? null : "preferred",
                    )
                  }
                />
                {(match.responsibilities || []).length > 0 && (
                  <QualStat
                    label="Responsibilities"
                    matched={(match.responsibilities || []).filter((row) => row.matched).length}
                    count={(match.responsibilities || []).length}
                    noun="responsibilities"
                    pressed={qualGroup === "responsibilities"}
                    onClick={() =>
                      setQualGroup((current) =>
                        current === "responsibilities" ? null : "responsibilities",
                      )
                    }
                  />
                )}
                <QualStat
                  label="Keywords"
                  matched={[...match.required, ...match.preferred].reduce(
                    (sum, row) => sum + row.keywords.filter((item) => item.found).length,
                    0,
                  )}
                  count={[...match.required, ...match.preferred].reduce(
                    (sum, row) => sum + row.keywords.length,
                    0,
                  )}
                  noun="keywords"
                  pressed={qualGroup === "keywords"}
                  onClick={() =>
                    setQualGroup((current) => (current === "keywords" ? null : "keywords"))
                  }
                />
              </div>
              {qualGroup === "required" && (
                <RequirementList
                  title="Required"
                  rows={match.required}
                  busy={busy}
                  onDismiss={dismissRequirement}
                  onMark={markRequirement}
                  onAddTag={addTag}
                  onActive={onActive}
                />
              )}
              {qualGroup === "preferred" && (
                <RequirementList
                  title="Preferred"
                  rows={match.preferred}
                  busy={busy}
                  onDismiss={dismissRequirement}
                  onMark={markRequirement}
                  onAddTag={addTag}
                  onActive={onActive}
                />
              )}
              {qualGroup === "responsibilities" && (
                <RequirementList
                  title="Responsibilities"
                  rows={match.responsibilities || []}
                  busy={busy}
                  onDismiss={dismissRequirement}
                  onMark={markRequirement}
                  onAddTag={addTag}
                  onActive={onActive}
                />
              )}
              {qualGroup === "keywords" && (
                <KeywordMatchList
                  rows={[...match.required, ...match.preferred]}
                  busy={busy}
                  onAddTag={addTag}
                  onActive={onActive}
                />
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

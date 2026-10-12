import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";
import ChoiceList from "./ChoiceList";

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

type RequirementKeyword = {
  keyword: string;
  found: boolean;
  where?: string;
};

type TagSuggestion = {
  keyword: string;
  bullet_id: string | null;
  bullet_excerpt: string;
  section: string;
  suggestion: string;
  line_id?: string;
};

export type ResumeHighlight = {
  terms: string[];
  lines: string[];
  excerpts: string[];
};

export const emptyHighlight: ResumeHighlight = { terms: [], lines: [], excerpts: [] };

function lineIds(suggestions: TagSuggestion[]) {
  return suggestions.map((item) => item.line_id).filter((id): id is string => Boolean(id));
}

function excerpts(suggestions: TagSuggestion[]) {
  return suggestions.map((item) => item.bullet_excerpt).filter(Boolean);
}

function suggestionHighlight(suggestions: TagSuggestion[], terms: string[] = []): ResumeHighlight {
  return { terms, lines: lineIds(suggestions), excerpts: excerpts(suggestions) };
}

type RequirementRow = {
  text: string;
  group: string;
  kind?: "skill" | "education";
  label?: string;
  matched: boolean;
  manual?: boolean;
  detail?: string;
  keywords: RequirementKeyword[];
  suggestions: TagSuggestion[];
};

type JobMatch = {
  composition_id: string;
  required_count: number;
  required_matched: number;
  preferred_count: number;
  preferred_matched: number;
  required: RequirementRow[];
  preferred: RequirementRow[];
};

type QualGroup = "required" | "preferred" | "keywords";

function foundKeywords(row: RequirementRow) {
  const terms = row.keywords.filter((item) => item.found).map((item) => item.keyword);
  if (row.kind === "education" && row.matched && row.detail && !row.detail.startsWith("This resume")) {
    terms.push(...row.detail.split(", ").map((part) => part.trim()).filter(Boolean));
  }
  return terms;
}

function SuggestionOptions({
  suggestions,
  busy,
  rowTerms,
  onAddTag,
  onHighlight,
}: {
  suggestions: TagSuggestion[];
  busy: boolean;
  rowTerms: string[];
  onAddTag: (bulletId: string, keyword: string) => void;
  onHighlight: (highlight: ResumeHighlight) => void;
}) {
  return suggestions.map((suggestion, suggestionIndex) => (
    <div
      className="jobs-suggestion"
      key={`${suggestion.keyword}-${suggestion.line_id || suggestionIndex}`}
      onMouseEnter={(event) => {
        event.stopPropagation();
        onHighlight({
          terms: [],
          lines: suggestion.line_id ? [suggestion.line_id] : [],
          excerpts: suggestion.bullet_excerpt ? [suggestion.bullet_excerpt] : [],
        });
      }}
      onMouseLeave={() => onHighlight(suggestionHighlight(suggestions, rowTerms))}
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
  onHighlight,
}: {
  title: string;
  rows: RequirementRow[];
  busy: boolean;
  onDismiss: (row: RequirementRow) => void;
  onMark: (row: RequirementRow) => void;
  onAddTag: (bulletId: string, keyword: string) => void;
  onHighlight: (highlight: ResumeHighlight) => void;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const matched = rows.filter((row) => row.matched).length;
  const groups = (
    [
      ["Skills", rows.filter((row) => row.kind !== "education")],
      ["Education", rows.filter((row) => row.kind === "education")],
    ] as const
  ).filter(([, items]) => items.length > 0);
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
                    onMouseEnter={() =>
                      onHighlight(
                        row.matched
                          ? { terms: foundKeywords(row), lines: [], excerpts: [] }
                          : suggestionHighlight(row.suggestions, foundKeywords(row)),
                      )
                    }
                    onMouseLeave={() => onHighlight(emptyHighlight)}
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
                        {row.keywords.length > 0 ? (
                          row.keywords.map((item) => (
                            <span
                              className={`keyword-chip ${item.found ? "" : "missing"}`}
                              key={item.keyword}
                            >
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
                        {row.kind === "education" && row.detail && <p>{row.detail}</p>}
                        {!row.matched && (
                          <SuggestionOptions
                            suggestions={row.suggestions}
                            busy={busy}
                            rowTerms={foundKeywords(row)}
                            onAddTag={onAddTag}
                            onHighlight={onHighlight}
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
  onHighlight,
}: {
  rows: RequirementRow[];
  busy: boolean;
  onAddTag: (bulletId: string, keyword: string) => void;
  onHighlight: (highlight: ResumeHighlight) => void;
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
                onMouseEnter={() =>
                  onHighlight(
                    item.found
                      ? {
                          terms: foundKeywords({
                            keywords: [item],
                            kind: item.kind,
                            matched: true,
                            detail: item.detail,
                          } as RequirementRow),
                          lines: [],
                          excerpts: [],
                        }
                      : suggestionHighlight(item.suggestions),
                  )
                }
                onMouseLeave={() => onHighlight(emptyHighlight)}
              >
                <button
                  type="button"
                  className="qual-toggle"
                  aria-expanded={expanded}
                  onClick={() => setOpen((current) => ({ ...current, [key]: !current[key] }))}
                >
                  <span className="qual-chevron" aria-hidden="true" />
                  <span className="qual-keywords">
                    <span className={`keyword-chip ${item.found ? "" : "missing"}`}>{item.keyword}</span>
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
                        rowTerms={[]}
                        onAddTag={onAddTag}
                        onHighlight={onHighlight}
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

export default function JobMatchPanel({
  compositionId,
  revision,
  linkedJobId,
  reloadLibrary,
  active,
  onHighlight,
}: {
  compositionId: string;
  revision: number;
  linkedJobId: string;
  reloadLibrary: () => Promise<void> | void;
  active: boolean;
  onHighlight: (highlight: ResumeHighlight) => void;
}) {
  const [jobs, setJobs] = useState<JobDescription[]>([]);
  const [jobId, setJobId] = useState("");
  const [match, setMatch] = useState<JobMatch | null>(null);
  const [qualGroup, setQualGroup] = useState<QualGroup | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [matchGeneration, setMatchGeneration] = useState(0);
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
    if (!active) onHighlight(emptyHighlight);
    return () => onHighlight(emptyHighlight);
  }, [active, qualGroup, jobId, onHighlight]);

  useEffect(() => {
    setMatch(null);
    setQualGroup(null);
  }, [jobId]);

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
          {match.required_count === 0 && match.preferred_count === 0 && (
            <p>No qualifications were found.</p>
          )}
          {(match.required_count > 0 || match.preferred_count > 0) && (
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
                  onHighlight={onHighlight}
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
                  onHighlight={onHighlight}
                />
              )}
              {qualGroup === "keywords" && (
                <KeywordMatchList
                  rows={[...match.required, ...match.preferred]}
                  busy={busy}
                  onAddTag={addTag}
                  onHighlight={onHighlight}
                />
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

import React, { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import AiAnalysisBar from "./AiAnalysisBar";
import { AppIcon } from "./AppIcon";
import { confirmDialog } from "./ConfirmDialog";
import JobDescriptionFields, { emptyJobDraft, type JobDraft } from "./JobDescriptionFields";
import compactLogo from "./assets/logo-compact.png";
import { highlightSegments, matchMarkId, type MatchMark } from "./matchMarks";
import type { AiAnalysisSummary, KeywordReview } from "./match/types";

type JobDescription = {
  id: string;
  company: string;
  role: string;
  title: string;
  body: string;
  composition_id: string | null;
  salary?: string;
  locations?: string[];
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  keyword_review?: KeywordReview;
  ai_analysis?: AiAnalysisSummary | null;
};

type AnalysisRow = {
  text: string;
  kind?: string;
  label?: string;
  match_mode?: "any" | "all";
  keywords: string[];
  source?: "rules" | "ai";
  ai_pending?: boolean;
  ai_confirmed?: boolean;
};

type JobAnalysis = {
  required: AnalysisRow[];
  preferred: AnalysisRow[];
  responsibilities?: AnalysisRow[];
  eligibility?: AnalysisRow[];
};

type Draft = JobDraft;
const emptyDraft = emptyJobDraft;

function FactBadges({ locations, salary }: { locations?: string[]; salary?: string }) {
  const places = locations || [];
  if (!salary && places.length === 0) return null;
  return (
    <span className="posting-facts">
      {places.map((place) => (
        <span className="fact-badge location" key={place}>
          {place}
        </span>
      ))}
      {salary && <span className="fact-badge salary">{salary}</span>}
    </span>
  );
}

const formatDate = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "Unavailable";

type PostingBlock =
  | { kind: "paragraph"; lead: string; text: string }
  | { kind: "list"; items: string[] };

type PostingSection = { title: string; blocks: PostingBlock[] };

const NAMED_HEADING =
  /^(?:job summary|role overview|key responsibilities|about the role(?:\s*(?:&|and)\s*(?:the )?team)?|about the team|about us|responsibilities|what you(?:'|’)ll do|who you are|the role|the team|the opportunity|required qualifications|basic qualifications|minimum qualifications|minimum requirements|preferred qualifications|you will have(?:\s*\/\s*required(?:\s+qualifications)?)?|skills\s*(?:&|and)\s*experience|required education|education|benefits|overview|compensation|duties)$/i;

const SECTION_TOPIC =
  /\b(?:summary|overview|responsibilities|responsibility|qualifications|qualification|requirements|requirement|skills|experience|education|benefits|about|duties|compensation|preferred|required|minimum|basic)\b/i;

function cleanHeadingLine(line: string) {
  return line
    .trim()
    .replace(/^#{1,6}\s+/, "")
    .replace(/^\*\*(.+)\*\*$/, "$1")
    .replace(/^\d+[.)]\s+/, "");
}

function headingText(line: string) {
  return line.replace(/[:\s]+$/, "").trim();
}

function leadSplit(line: string) {
  const match = line.match(/^([A-Z][^:]{1,42}):\s+(\S[\s\S]*)$/);
  if (!match) return null;
  const lead = match[1].trim();
  if (lead.split(/\s+/).length > 6 || NAMED_HEADING.test(lead)) return null;
  return { lead, text: match[2].trim() };
}

function isSectionHeading(line: string) {
  // A bullet is an item, even one that mentions "experience" or "skills".
  if (leadSplit(line) || isBullet(line.trim())) return false;
  const text = headingText(cleanHeadingLine(line));
  if (!text || text.length > 80) return false;
  const words = text.split(/\s+/);
  if (words.length > 8) return false;
  if (words.length > 4 && /[.?!]/.test(text)) return false;
  if (NAMED_HEADING.test(text)) return true;
  const letters = text.replace(/[^A-Za-z]/g, "");
  if (letters.length >= 4 && letters === letters.toUpperCase()) return true;
  if (words.length <= 8 && SECTION_TOPIC.test(text) && !/[.?!]/.test(text)) return true;
  if (
    words.length >= 2 &&
    words.length <= 6 &&
    !/[.?!,:]/.test(text) &&
    words.every(
      (word) => /^[A-Z0-9&]/.test(word) || /^(?:and|of|the|a|to|for|in|on|with)$/i.test(word),
    )
  ) {
    return true;
  }
  return /:$/.test(line.trim()) && words.length <= 6;
}

function isBullet(line: string) {
  return /^(?:[-*•●–]|\d+[.)])\s+\S/.test(line);
}

function stripBullet(line: string) {
  return line.replace(/^(?:[-*•●–]|\d+[.)])\s+/, "").trim();
}

function looksLikeItem(line: string) {
  if (leadSplit(line) || /^[a-z(]/.test(line)) return false;
  const words = line.split(/\s+/).length;
  return words >= 3 && words <= 35;
}

function previewTitle(text: string) {
  const words = text.replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
  if (words.length === 0) return "Description";
  const phrase = words.slice(0, 6).join(" ");
  return words.length > 6 ? `${phrase}…` : phrase;
}

function blocksFromLines(lines: string[]): PostingBlock[] {
  const filled = lines.map((line) => line.trim()).filter(Boolean);
  const kinds = filled.map((line) =>
    isBullet(line) ? "bullet" : looksLikeItem(line) ? "item" : "prose",
  );
  for (let index = 0; index < kinds.length; index += 1) {
    if (kinds[index] !== "item") continue;
    const neighbors = [kinds[index - 1], kinds[index + 1]];
    if (!neighbors.some((kind) => kind === "item" || kind === "bullet")) kinds[index] = "prose";
  }
  const blocks: PostingBlock[] = [];
  let paragraph = "";
  let list: string[] | null = null;
  const flushParagraph = () => {
    const text = paragraph.replace(/\s+/g, " ").trim();
    paragraph = "";
    if (!text) return;
    const lead = leadSplit(text);
    blocks.push(lead ? { kind: "paragraph", ...lead } : { kind: "paragraph", lead: "", text });
  };
  const flushList = () => {
    if (list?.length) blocks.push({ kind: "list", items: list });
    list = null;
  };
  filled.forEach((line, index) => {
    if (kinds[index] === "prose") {
      flushList();
      if (paragraph && !/[.!?:"”]$/.test(paragraph) && /^[a-z(]/.test(line)) paragraph += ` ${line}`;
      else {
        flushParagraph();
        paragraph = line;
      }
      return;
    }
    flushParagraph();
    list = list || [];
    list.push(stripBullet(line));
  });
  flushParagraph();
  flushList();
  return blocks;
}

function looseSections(body: string): PostingSection[] {
  const chunks = body
    .split(/\n\s*\n/)
    .map((chunk) => chunk.trim())
    .filter(Boolean);
  const source = chunks.length ? chunks : [body.trim()].filter(Boolean);
  return source.map((chunk) => {
    const lines = chunk.split("\n");
    const first = lines[0]?.trim() || "";
    if (lines.length > 1 && isSectionHeading(first)) {
      return {
        title: headingText(cleanHeadingLine(first)),
        blocks: blocksFromLines(lines.slice(1)),
      };
    }
    const blocks = blocksFromLines(lines);
    const text = blocks[0]?.kind === "list" ? blocks[0].items[0] : blocks[0]?.text || first;
    return { title: previewTitle(text), blocks };
  }).filter((section) => section.blocks.length > 0);
}

function postingSections(body: string): PostingSection[] {
  const text = body.replace(/\r\n/g, "\n").trim();
  if (!text) return [];
  const sections: PostingSection[] = [];
  let title = "";
  let bucket: string[] = [];
  let sawHeading = false;
  const flush = () => {
    const blocks = blocksFromLines(bucket);
    bucket = [];
    if (!blocks.length) {
      title = "";
      return;
    }
    const label =
      title ||
      previewTitle(blocks[0].kind === "list" ? blocks[0].items[0] || "" : blocks[0].text);
    sections.push({ title: label, blocks });
    title = "";
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (line && isSectionHeading(line)) {
      flush();
      sawHeading = true;
      title = headingText(cleanHeadingLine(line));
      continue;
    }
    bucket.push(raw);
  }
  flush();
  if (!sawHeading) return looseSections(text);
  return sections;
}

/** One highlight per keyword. A term only AI found keeps the AI style; the rules finding it too wins. */
function postingMarks(analysis: JobAnalysis | null): MatchMark[] {
  if (!analysis) return [];
  const marks = new Map<string, MatchMark>();
  const rows = [...analysis.required, ...analysis.preferred, ...(analysis.responsibilities || [])];
  for (const row of rows) {
    for (const term of row.keywords) {
      const id = matchMarkId(term);
      if (!id) continue;
      const ai = row.source === "ai";
      const current = marks.get(id);
      if (current) current.ai = !!current.ai && ai;
      else marks.set(id, { id, kind: "match", terms: [term], lineIds: [], excerpts: [], ai });
    }
  }
  return [...marks.values()];
}

function Highlighted({ text, marks }: { text: string; marks: MatchMark[] }) {
  if (!marks.length) return <>{text}</>;
  return (
    <>
      {highlightSegments(text, marks).map((segment, index) =>
        segment.mark ? (
          <mark
            key={index}
            className={`posting-hit${segment.mark.ai ? " ai" : ""}`}
            title={segment.mark.ai ? "Keyword found by AI" : "Keyword"}
          >
            {segment.text}
          </mark>
        ) : (
          <React.Fragment key={index}>{segment.text}</React.Fragment>
        ),
      )}
    </>
  );
}

function PostingView({ body, marks = [] }: { body: string; marks?: MatchMark[] }) {
  const sections = useMemo(() => postingSections(body), [body]);
  const [open, setOpen] = useState<Record<number, boolean>>({ 0: true });
  useEffect(() => {
    setOpen({ 0: true });
  }, [body]);
  if (sections.length === 0) return <p>No description yet.</p>;
  return (
    <div className="posting">
      {sections.map((section, index) => {
        const expanded = !!open[index];
        return (
          <section
            className={`posting-section ${expanded ? "open" : ""}`}
            key={`${section.title}-${index}`}
          >
            <button
              type="button"
              className="posting-toggle"
              aria-expanded={expanded}
              onClick={() => setOpen((current) => ({ ...current, [index]: !current[index] }))}
            >
              <span className="qual-chevron" aria-hidden="true" />
              <span>{section.title}</span>
            </button>
            {expanded && (
              <div className="posting-body">
                {section.blocks.map((block, blockIndex) =>
                  block.kind === "list" ? (
                    <ul key={blockIndex}>
                      {block.items.map((item, itemIndex) => (
                        <li key={`${itemIndex}-${item}`}>
                          <Highlighted text={item} marks={marks} />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p key={blockIndex}>
                      {block.lead && (
                        <strong>
                          <Highlighted text={block.lead} marks={marks} />.{" "}
                        </strong>
                      )}
                      <Highlighted text={block.text} marks={marks} />
                    </p>
                  ),
                )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}


function KeywordGroups({
  analysis,
  busy,
  onAccept,
  onDismiss,
}: {
  analysis: JobAnalysis;
  busy: boolean;
  onAccept: (row: AnalysisRow) => void;
  onDismiss: (row: AnalysisRow) => void;
}) {
  const groups = (
    [
      ["Required", analysis.required],
      ["Preferred", analysis.preferred],
      ["Responsibilities", analysis.responsibilities || []],
    ] as const
  ).filter(([, rows]) => rows.length > 0);
  const eligibility = analysis.eligibility || [];
  if (groups.length === 0 && eligibility.length === 0) {
    return <p>No qualifications were found in this description.</p>;
  }
  return (
    <div className="keyword-groups">
      {eligibility.length > 0 && (
        <section aria-label="Eligibility">
          <h3>Eligibility</h3>
          <ul className="requirement-list">
            {eligibility.map((row) => (
              <li className="requirement-row" key={`${row.kind || "gate"}:${row.text}`}>
                <span className="qual-label">{row.label || row.text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {groups.map(([title, rows]) => (
        <section key={title} aria-label={title}>
          <h3>{title}</h3>
          <ul className="requirement-list">
            {rows.map((row) => (
              <li className={`requirement-row${row.ai_pending ? " ai-pending" : ""}`} key={`${row.kind || "skill"}:${row.text}`} title={row.text}>
                <span className="qual-keywords">
                  {row.match_mode === "any" && row.keywords.length > 1 && (
                    <span className="qual-any">Any of</span>
                  )}
                  {row.keywords.length > 0 ? (
                    row.keywords.map((keyword) => (
                      <span className="keyword-chip plain" key={keyword}>
                        {keyword}
                      </span>
                    ))
                  ) : (
                    <span className="qual-label">{row.label || row.text}</span>
                  )}
                </span>
                {row.source === "ai" && (
                  <span
                    className={`ai-badge${row.ai_pending ? " pending" : ""}`}
                    title={row.ai_pending ? "Found by AI. Counts at half weight until you accept it." : "Found by AI and accepted."}
                  >
                    ✦ AI
                  </span>
                )}
                {row.ai_pending && (
                  <span className="ai-row-actions">
                    <button type="button" className="link-button" disabled={busy} onClick={() => onAccept(row)}>
                      Accept
                    </button>
                    <button type="button" className="link-button danger-text" disabled={busy} onClick={() => onDismiss(row)}>
                      Dismiss
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export default function JobsPage({
  onHome,
  onLibrary,
  onBin,
}: {
  onHome: () => void;
  onLibrary: () => void;
  onBin: () => void;
}) {
  const [jobs, setJobs] = useState<JobDescription[]>([]);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [editing, setEditing] = useState<JobDescription | null>(null);
  const [creating, setCreating] = useState(false);
  const [analysis, setAnalysis] = useState<JobAnalysis | null>(null);
  const [describing, setDescribing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const request = useRef(0);

  const load = async () => {
    const rows = await api<JobDescription[]>("/api/job-descriptions");
    setJobs(rows);
    setLoaded(true);
    return rows;
  };

  const loadAnalysis = async (jobId: string, token: number) => {
    try {
      const result = await api<JobAnalysis>(`/api/job-descriptions/${jobId}/analysis`);
      if (token === request.current) setAnalysis(result);
    } catch (reason: any) {
      if (token === request.current) setError(reason.message);
    }
  };

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
        if (!cancelled) setError(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = jobs.filter((job) =>
    [job.title, job.company, job.role, job.body].some((value) =>
      (value || "").toLowerCase().includes(query.trim().toLowerCase()),
    ),
  );

  const openJob = (job: JobDescription) => {
    const token = ++request.current;
    setCreating(false);
    setDescribing(false);
    setEditing(job);
    setDraft({
      company: job.company,
      role: job.role,
      title: job.title,
      body: job.body,
    });
    setAnalysis(null);
    setError("");
    loadAnalysis(job.id, token);
  };

  const save = async () => {
    const payload = {
      company: draft.company,
      role: draft.role,
      title: draft.title,
      body: draft.body,
      composition_id: editing?.composition_id || null,
    };
    const saved = editing
      ? await api<JobDescription>(`/api/job-descriptions/${editing.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        })
      : await api<JobDescription>("/api/job-descriptions", {
          method: "POST",
          body: JSON.stringify(payload),
        });
    const token = ++request.current;
    setEditing(saved);
    setCreating(false);
    setDescribing(false);
    setDraft({
      company: saved.company,
      role: saved.role,
      title: saved.title,
      body: saved.body,
    });
    await load();
    await loadAnalysis(saved.id, token);
    return saved;
  };

  const sameText = (left: string, right: string) => left.trim().toLowerCase() === right.trim().toLowerCase();

  /** Accept or dismiss an AI-found requirement. Saved in the job's keyword review, like the editor does. */
  const reviewAi = async (row: AnalysisRow, action: "accept" | "dismiss") => {
    if (!editing) return;
    const current = editing.keyword_review || { dismissed: [], added: [], matched: [], skipped: [] };
    const field = action === "accept" ? "ai_accepted" : "dismissed";
    const list = current[field] || [];
    if (list.some((text) => sameText(text, row.text))) return;
    setBusy(true);
    setError("");
    try {
      const saved = await api<JobDescription>(`/api/job-descriptions/${editing.id}`, {
        method: "PUT",
        body: JSON.stringify({
          company: editing.company,
          role: editing.role,
          title: editing.title,
          body: editing.body,
          composition_id: editing.composition_id,
          keyword_review: { ...current, [field]: [...list, row.text] },
        }),
      });
      setEditing(saved);
      setJobs((rows) => rows.map((job) => (job.id === saved.id ? { ...job, ...saved } : job)));
      await loadAnalysis(saved.id, ++request.current);
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  };

  /** Only on request: the posting (never a resume) is read by AI and the result saved on the job. */
  const runAiAnalysis = async () => {
    if (!editing) return;
    setBusy(true);
    setAnalysing(true);
    setError("");
    try {
      const result = await api<{ status: string; detail: string; job: JobDescription }>(
        `/api/job-descriptions/${editing.id}/ai-analysis`,
        { method: "POST" },
      );
      setEditing(result.job);
      setJobs((rows) => rows.map((job) => (job.id === result.job.id ? { ...job, ...result.job } : job)));
      if (result.status !== "ok") setError(result.detail);
      else await loadAnalysis(result.job.id, ++request.current);
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setAnalysing(false);
      setBusy(false);
    }
  };

  const marks = useMemo(() => postingMarks(analysis), [analysis]);
  const aiPending = analysis
    ? [...analysis.required, ...analysis.preferred, ...(analysis.responsibilities || [])].filter((row) => row.ai_pending).length
    : 0;

  const archive = async (job: JobDescription) => {
    const confirmed = await confirmDialog({
      title: "Archive job description?",
      message: `${job.title} will be removed from this list.`,
      confirmLabel: "Archive",
      danger: true,
    });
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/job-descriptions/${job.id}/archive`, { method: "POST" });
      if (editing?.id === job.id) {
        setEditing(null);
        setCreating(false);
        setAnalysis(null);
        setDraft(emptyDraft());
      }
      await load();
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="home-shell">
      <aside className="home-rail" aria-label="Primary navigation">
        <nav className="rail-nav">
          <button className="rail-link" onClick={onHome}>
            <AppIcon name="home" />
            Home
          </button>
          <button className="rail-link" onClick={onLibrary}>
            <AppIcon name="library" />
            Library
          </button>
          <button className="rail-link active" aria-current="page">
            <AppIcon name="jobs" />
            Jobs
          </button>
          <button className="rail-link" onClick={onBin}>
            <AppIcon name="bin" />
            Bin
          </button>
        </nav>
      </aside>
      <section className="home-content">
        <div className="jobs-page">
          {error && (
            <div role="alert" className="error home-error">
              {error}
              <button onClick={() => setError("")}>Dismiss</button>
            </div>
          )}
          <header className="library-page-header">
            <div className="library-title">
              <img src={compactLogo} alt="" />
              <div>
                <h1>Job descriptions</h1>
                <p>Save a posting and review the keywords pulled from its qualifications.</p>
              </div>
            </div>
            {!creating && !editing && (
              <>
                <label className="library-search">
                  <AppIcon name="search" />
                  <span className="sr-only">Search job descriptions</span>
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search job descriptions…"
                  />
                </label>
                <button
                  className="primary-action"
                  onClick={() => {
                    setCreating(true);
                    setDescribing(true);
                    setEditing(null);
                    setDraft(emptyDraft());
                    setAnalysis(null);
                    setError("");
                  }}
                >
                  + New job description
                </button>
              </>
            )}
          </header>
          {!creating && !editing && (
            <>
              <div className="library-title-row">
                <h2>Saved descriptions ({visible.length})</h2>
              </div>
              {!loaded ? (
                <p>Loading…</p>
              ) : visible.length === 0 ? (
                <div className="empty-state">
                  <strong>
                    {query ? "No matching job descriptions" : "No job descriptions yet"}
                  </strong>
                  <span>
                    {query
                      ? "Try a different search."
                      : "Paste a posting to extract its keywords."}
                  </span>
                </div>
              ) : (
                <div className="resume-table" role="table" aria-label="Job descriptions">
                  <div className="resume-table-head" role="row">
                    <span role="columnheader">Title</span>
                    <span role="columnheader">Company</span>
                    <span role="columnheader">Role</span>
                    <span role="columnheader">Last Modified</span>
                    <span aria-hidden="true" />
                  </div>
                  {visible.map((job) => (
                    <div className="resume-table-row" role="row" key={job.id}>
                      <button
                        className="resume-name"
                        onClick={() => openJob(job)}
                        role="cell"
                      >
                        <AppIcon name="jobs" aria-hidden="true" />
                        <span className="resume-name-copy">
                          <span>{job.title}</span>
                          <FactBadges locations={job.locations} salary={job.salary} />
                        </span>
                      </button>
                      <span role="cell">{job.company || "—"}</span>
                      <span role="cell">{job.role || "—"}</span>
                      <span role="cell">{formatDate(job.updated_at)}</span>
                      <span role="cell">
                        <button
                          className="danger-text"
                          aria-label={`Archive ${job.title}`}
                          onClick={() => archive(job)}
                        >
                          Archive
                        </button>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
          {(creating || editing) && (
            <>
              <button
                className="jobs-back"
                onClick={() => {
                  setCreating(false);
                  setEditing(null);
                  setAnalysis(null);
                  setDraft(emptyDraft());
                }}
              >
                ← All job descriptions
              </button>
              <div className="jobs-detail">
                <section className="jobs-panel">
                  {describing ? (
                    <form
                      onSubmit={(event) => {
                        event.preventDefault();
                        setBusy(true);
                        setError("");
                        save()
                          .catch((reason: Error) => setError(reason.message))
                          .finally(() => setBusy(false));
                      }}
                    >
                      <h2>{editing ? "Edit job description" : "New job description"}</h2>
                      <JobDescriptionFields draft={draft} setDraft={setDraft} />
                      <div className="form-actions">
                        <button type="submit" disabled={busy || !draft.body.trim()}>
                          Save
                        </button>
                        {editing && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => {
                              setDraft({
                                company: editing.company,
                                role: editing.role,
                                title: editing.title,
                                body: editing.body,
                              });
                              setDescribing(false);
                            }}
                          >
                            Cancel
                          </button>
                        )}
                        {editing && (
                          <button
                            type="button"
                            className="danger-text"
                            onClick={() => archive(editing)}
                          >
                            Archive
                          </button>
                        )}
                      </div>
                    </form>
                  ) : (
                    <>
                      <div className="posting-head">
                        <div>
                          <h2>{editing?.title || "Job description"}</h2>
                          <p className="posting-meta">
                            {[editing?.company, editing?.role].filter(Boolean).join(" · ") ||
                              "No company or role"}
                          </p>
                          <FactBadges locations={editing?.locations} salary={editing?.salary} />
                        </div>
                        <button
                          type="button"
                          className="posting-edit"
                          aria-label="Edit job description"
                          onClick={() => setDescribing(true)}
                        >
                          <AppIcon name="pencil" />
                        </button>
                      </div>
                      <PostingView body={editing?.body || ""} marks={marks} />
                      {editing && (
                        <button
                          type="button"
                          className="danger-text"
                          onClick={() => archive(editing)}
                        >
                          Archive
                        </button>
                      )}
                    </>
                  )}
                </section>
                <section className="jobs-panel" aria-live="polite">
                  <h2>Keywords</h2>
                  {editing && !describing && (
                    <AiAnalysisBar analysis={editing.ai_analysis} pending={aiPending} busy={busy} running={analysing} onRun={runAiAnalysis} />
                  )}
                  {!editing ? (
                    <p>Save the description to see its keywords.</p>
                  ) : !analysis ? (
                    <p>{error ? "Keywords could not be read." : "Reading keywords from this description…"}</p>
                  ) : (
                    <KeywordGroups
                      analysis={analysis}
                      busy={busy}
                      onAccept={(row) => reviewAi(row, "accept")}
                      onDismiss={(row) => reviewAi(row, "dismiss")}
                    />
                  )}
                </section>
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}

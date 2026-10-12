import React, { useState } from "react";
import { api } from "./api";
import { AppIcon, type AppIconName } from "./AppIcon";
import MonthYearField from "./MonthYearField";
import primaryLogo from "./assets/logo-primary-480.png";

export type ImportEntry = {
  id: string;
  section: string;
  included: boolean;
  source_text: string;
  low_confidence: string[];
  organization: string;
  title: string;
  name: string;
  subtitle: string;
  location: string;
  date_label: string;
  start_year: number | null;
  start_month: number | null;
  end_year: number | null;
  end_month: number | null;
  is_current: boolean;
  bullets: string[];
  institution: string;
  college_school: string;
  degree_type: string;
  degree_major: string;
  graduation_year: number | null;
  graduation_month: number | null;
  display_date: string;
  tools: string[];
  body: string;
};

export type ImportDraft = {
  profile: {
    label: string;
    name: string;
    phone: string;
    email: string;
    linkedin_label: string;
    linkedin_url: string;
    included: boolean;
    low_confidence: string[];
  };
  summary: {
    name: string;
    body: string;
    included: boolean;
    low_confidence: string[];
  };
  entries: ImportEntry[];
  leftover: string;
  notices: string[];
};

const ENTRY_SECTIONS: [string, string, AppIconName][] = [
  ["employment", "Employment", "experience"],
  ["leadership", "Leadership", "leadership"],
  ["project", "Projects", "projects"],
  ["education", "Education", "education"],
  ["skills", "Skills", "skills"],
  ["interests", "Interests", "interests"],
];

const DASHBOARD: [string, string, AppIconName][] = [
  ["all", "All", "all-items"],
  ["profile", "Profile", "profile"],
  ["summary", "Summary", "details"],
  ...ENTRY_SECTIONS,
  ["unmapped", "Unmapped", "document"],
];

const ACCEPT = ".pdf,.docx,.csv,.zip,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/csv,application/zip";
const LINKEDIN_PDF_HELP =
  "Open your LinkedIn profile, choose Resources, then Save to PDF. Upload that file.";
const LINKEDIN_DATA_HELP =
  "On LinkedIn, open Me, then Settings & Privacy, then Data privacy. Under How LinkedIn uses your data, choose Get a copy of your data. Pick Want something in particular, select Profile, Positions, Education, and Skills, then Request archive. LinkedIn emails a download link within a few minutes. Upload the ZIP from that email, or upload the CSV files inside it. The larger full-archive download also works; only those four files are read.";

function message(payload: any, status: number) {
  const detail = payload?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((item) => item?.msg || "Could not import that file.").join(" ");
  return `Request failed: ${status}`;
}

async function previewImport(file: File): Promise<ImportDraft> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/library/import/preview", { method: "POST", body });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(message(payload, response.status));
  return payload;
}

function blankEntry(section: string): ImportEntry {
  return {
    id: crypto.randomUUID(),
    section,
    included: true,
    source_text: "",
    low_confidence: [],
    organization: "",
    title: "",
    name: "",
    subtitle: "",
    location: "",
    date_label: "",
    start_year: null,
    start_month: null,
    end_year: null,
    end_month: null,
    is_current: false,
    bullets: [],
    institution: "",
    college_school: "",
    degree_type: "",
    degree_major: "",
    graduation_year: null,
    graduation_month: null,
    display_date: "",
    tools: [],
    body: "",
  };
}

function allowedFile(file: File) {
  return /\.(pdf|docx|csv|zip)$/i.test(file.name);
}

function sectionIcon(section: string): AppIconName {
  return DASHBOARD.find(([key]) => key === section)?.[2] || "document";
}

function entryTitle(entry: ImportEntry) {
  if (entry.section === "employment" || entry.section === "leadership")
    return [entry.organization, entry.title].filter(Boolean).join(" — ") || "Untitled";
  if (entry.section === "education") return entry.institution || "Untitled school";
  if (entry.section === "skills") return entry.name || "Skill group";
  if (entry.section === "interests") return entry.body || "Interest";
  return entry.name || "Untitled project";
}

function entryDate(entry: ImportEntry) {
  if (entry.section === "education") return entry.display_date;
  if (entry.section === "skills" || entry.section === "interests") return "";
  return entry.date_label;
}

function includedCount(draft: ImportDraft, key: string) {
  if (key === "profile") return draft.profile.included ? 1 : 0;
  if (key === "summary") return draft.summary.included ? 1 : 0;
  if (key === "unmapped") return draft.leftover.trim() ? 1 : 0;
  if (key === "all")
    return (
      (draft.profile.included ? 1 : 0) +
      (draft.summary.included ? 1 : 0) +
      draft.entries.filter((entry) => entry.included && entry.section !== "skip").length
    );
  return draft.entries.filter((entry) => entry.section === key && entry.included).length;
}

export default function ImportResumeDialog({
  close,
  onImported,
  onLibrary,
  onJobs,
  onBin,
}: {
  close: () => void;
  onImported: (compositionId: string, warnings: string[]) => Promise<void> | void;
  onLibrary: () => void;
  onJobs: () => void;
  onBin: () => void;
}) {
  const [help, setHelp] = useState(false);
  const [pdfOpen, setPdfOpen] = useState(true);
  const [dataOpen, setDataOpen] = useState(true);
  const [drag, setDrag] = useState(false);
  const [draft, setDraft] = useState<ImportDraft | null>(null);
  const [view, setView] = useState("all");
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [openRecords, setOpenRecords] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const upload = async (file: File | undefined) => {
    if (!file) return;
    if (!allowedFile(file)) {
      setError("Upload a PDF, Word document (.docx), CSV, or ZIP.");
      return;
    }
    setError("");
    setBusy("Reading file…");
    try {
      setDraft(await previewImport(file));
      setView("all");
      setCollapsed([]);
      setOpenRecords({});
    } catch (reason: any) {
      setError(reason.message || "Could not read that file.");
    } finally {
      setBusy("");
    }
  };

  const commit = async () => {
    if (!draft) return;
    setError("");
    setBusy("Adding to library…");
    try {
      const result = await api<{ composition_id: string; warnings: string[] }>(
        "/api/library/import/commit",
        { method: "POST", body: JSON.stringify(draft) },
      );
      await onImported(result.composition_id, result.warnings || []);
    } catch (reason: any) {
      setError(reason.message || "Could not add these records.");
      setBusy("");
    }
  };

  const patchEntry = (id: string, patch: Partial<ImportEntry>) => {
    setDraft((current) =>
      current
        ? {
            ...current,
            entries: current.entries.map((entry) =>
              entry.id === id ? { ...entry, ...patch } : entry,
            ),
          }
        : current,
    );
  };

  const addEntry = (section: string) => {
    const entry = blankEntry(section);
    setOpenRecords((current) => ({ ...current, [entry.id]: true }));
    setCollapsed((current) => current.filter((key) => key !== section));
    setDraft((current) =>
      current ? { ...current, entries: [...current.entries, entry] } : current,
    );
  };

  const recordOpen = (id: string, flagged: boolean) =>
    id in openRecords ? openRecords[id] : flagged;

  const toggleRecord = (id: string, flagged: boolean) =>
    setOpenRecords((current) => ({ ...current, [id]: !recordOpen(id, flagged) }));

  const showSection = (key: string) => {
    if (!draft) return false;
    if (view !== "all" && view !== key) return false;
    if (view === key) return true;
    if (key === "profile" || key === "summary") return true;
    if (key === "unmapped") return Boolean(draft.leftover.trim());
    return draft.entries.some((entry) => entry.section === key);
  };

  return (
    <main className="home-shell">
      <aside className="home-rail" aria-label="Primary navigation">
        <nav className="rail-nav">
          <button type="button" className="rail-link" onClick={close}>
            <AppIcon name="home" />
            Home
          </button>
          <button type="button" className="rail-link" onClick={onLibrary}>
            <AppIcon name="library" />
            Library
          </button>
          <button type="button" className="rail-link" onClick={onJobs}>
            <AppIcon name="jobs" />
            Jobs
          </button>
          <button type="button" className="rail-link" onClick={onBin}>
            <AppIcon name="bin" />
            Bin
          </button>
        </nav>
      </aside>
      <section className="home-content import-workspace">
        <header className="import-page-header">
          <img src={primaryLogo} alt="" className="import-logo" />
          <div className="import-page-heading">
            <div>
              <h1>Import Existing Resume</h1>
              <p>
                {draft
                  ? "Review what will be added to your library."
                  : "Upload a resume or a LinkedIn export."}
              </p>
            </div>
            {!draft && (
              <button type="button" onClick={close}>
                Back
              </button>
            )}
          </div>
        </header>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {!draft ? (
          <UploadStep
            drag={drag}
            setDrag={setDrag}
            busy={busy}
            help={help}
            setHelp={setHelp}
            pdfOpen={pdfOpen}
            setPdfOpen={setPdfOpen}
            dataOpen={dataOpen}
            setDataOpen={setDataOpen}
            upload={upload}
          />
        ) : (
          <div className="import-review">
            {draft.notices.map((notice) => (
              <p key={notice} role="status" className="import-notice">
                {notice}
              </p>
            ))}
            <div className="import-layout">
              <aside className="library-sections" aria-label="Import sections">
                <h2>Import</h2>
                {DASHBOARD.map(([key, label, icon]) => (
                  <button
                    type="button"
                    key={key}
                    aria-pressed={view === key}
                    onClick={() => {
                      setView(key);
                      setCollapsed((current) => current.filter((item) => item !== key));
                    }}
                  >
                    <span>
                      <AppIcon name={icon} />
                      {label}
                    </span>
                    <strong>{includedCount(draft, key)}</strong>
                  </button>
                ))}
              </aside>
              <div className="import-sections">
                {showSection("profile") && (
                  <SectionBox
                    title="Profile"
                    icon="profile"
                    count={includedCount(draft, "profile")}
                    open={!collapsed.includes("profile")}
                    onToggle={() =>
                      setCollapsed((current) =>
                        current.includes("profile")
                          ? current.filter((key) => key !== "profile")
                          : [...current, "profile"],
                      )
                    }
                  >
                    <RecordCard
                      title={draft.profile.name || "Profile"}
                      meta={draft.profile.label}
                      icon="profile"
                      included={draft.profile.included}
                      open={recordOpen("profile", draft.profile.low_confidence.length > 0)}
                      onToggle={() =>
                        toggleRecord("profile", draft.profile.low_confidence.length > 0)
                      }
                      onIncluded={(included) =>
                        setDraft({ ...draft, profile: { ...draft.profile, included } })
                      }
                    >
                      <div className="form-grid">
                        <TextField
                          label="Profile name"
                          value={draft.profile.label}
                          low={draft.profile.low_confidence.includes("label")}
                          onChange={(label) =>
                            setDraft({ ...draft, profile: { ...draft.profile, label } })
                          }
                        />
                        <TextField
                          label="Name"
                          value={draft.profile.name}
                          low={draft.profile.low_confidence.includes("name")}
                          onChange={(name) =>
                            setDraft({ ...draft, profile: { ...draft.profile, name } })
                          }
                        />
                        <TextField
                          label="Email"
                          value={draft.profile.email}
                          low={draft.profile.low_confidence.includes("email")}
                          onChange={(email) =>
                            setDraft({ ...draft, profile: { ...draft.profile, email } })
                          }
                        />
                        <TextField
                          label="Phone"
                          value={draft.profile.phone}
                          low={draft.profile.low_confidence.includes("phone")}
                          onChange={(phone) =>
                            setDraft({ ...draft, profile: { ...draft.profile, phone } })
                          }
                        />
                        <TextField
                          label="LinkedIn text"
                          value={draft.profile.linkedin_label}
                          onChange={(linkedin_label) =>
                            setDraft({
                              ...draft,
                              profile: { ...draft.profile, linkedin_label },
                            })
                          }
                        />
                        <TextField
                          label="LinkedIn URL"
                          value={draft.profile.linkedin_url}
                          full
                          onChange={(linkedin_url) =>
                            setDraft({
                              ...draft,
                              profile: { ...draft.profile, linkedin_url },
                            })
                          }
                        />
                      </div>
                    </RecordCard>
                  </SectionBox>
                )}
                {showSection("summary") && (
                  <SectionBox
                    title="Summary"
                    icon="details"
                    count={includedCount(draft, "summary")}
                    open={!collapsed.includes("summary")}
                    onToggle={() =>
                      setCollapsed((current) =>
                        current.includes("summary")
                          ? current.filter((key) => key !== "summary")
                          : [...current, "summary"],
                      )
                    }
                  >
                    <RecordCard
                      title={draft.summary.name || "Summary"}
                      meta=""
                      icon="details"
                      included={draft.summary.included}
                      open={recordOpen("summary", draft.summary.low_confidence.length > 0)}
                      onToggle={() =>
                        toggleRecord("summary", draft.summary.low_confidence.length > 0)
                      }
                      onIncluded={(included) =>
                        setDraft({ ...draft, summary: { ...draft.summary, included } })
                      }
                    >
                      <div className="form-grid">
                        <TextField
                          label="Summary name"
                          value={draft.summary.name}
                          onChange={(name) =>
                            setDraft({ ...draft, summary: { ...draft.summary, name } })
                          }
                        />
                        <label className="full">
                          Summary
                          <textarea
                            value={draft.summary.body}
                            onChange={(event) =>
                              setDraft({
                                ...draft,
                                summary: { ...draft.summary, body: event.target.value },
                              })
                            }
                          />
                        </label>
                      </div>
                    </RecordCard>
                  </SectionBox>
                )}
                {ENTRY_SECTIONS.filter(([key]) => showSection(key)).map(([key, label, icon]) => (
                  <SectionBox
                    key={key}
                    title={label}
                    icon={icon}
                    count={includedCount(draft, key)}
                    open={!collapsed.includes(key)}
                    onToggle={() =>
                      setCollapsed((current) =>
                        current.includes(key)
                          ? current.filter((item) => item !== key)
                          : [...current, key],
                      )
                    }
                  >
                    <div className="entry-list">
                      {draft.entries
                        .filter((entry) => entry.section === key)
                        .map((entry) => (
                          <EntryCard
                            key={entry.id}
                            entry={entry}
                            open={recordOpen(entry.id, entry.low_confidence.length > 0)}
                            onToggle={() =>
                              toggleRecord(entry.id, entry.low_confidence.length > 0)
                            }
                            onChange={(patch) => patchEntry(entry.id, patch)}
                            onRemove={() =>
                              setDraft({
                                ...draft,
                                entries: draft.entries.filter((item) => item.id !== entry.id),
                              })
                            }
                          />
                        ))}
                    </div>
                    {draft.entries.every((entry) => entry.section !== key) && (
                      <p className="library-note">Nothing in this section yet.</p>
                    )}
                    <button type="button" onClick={() => addEntry(key)}>
                      + Add
                    </button>
                  </SectionBox>
                ))}
                {showSection("unmapped") && (
                  <SectionBox
                    title="Unmapped"
                    icon="document"
                    count={includedCount(draft, "unmapped")}
                    open={!collapsed.includes("unmapped")}
                    onToggle={() =>
                      setCollapsed((current) =>
                        current.includes("unmapped")
                          ? current.filter((key) => key !== "unmapped")
                          : [...current, "unmapped"],
                      )
                    }
                  >
                    {draft.leftover.trim() ? (
                      <pre className="import-source">{draft.leftover}</pre>
                    ) : (
                      <p className="library-note">No unmapped text.</p>
                    )}
                  </SectionBox>
                )}
                <div className="form-actions">
                  <button type="button" onClick={() => setDraft(null)} disabled={!!busy}>
                    Back
                  </button>
                  <button
                    type="button"
                    className="primary-action"
                    onClick={commit}
                    disabled={!!busy}
                  >
                    {busy || "Add to library"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

function UploadStep({
  drag,
  setDrag,
  busy,
  help,
  setHelp,
  pdfOpen,
  setPdfOpen,
  dataOpen,
  setDataOpen,
  upload,
}: {
  drag: boolean;
  setDrag: (value: boolean) => void;
  busy: string;
  help: boolean;
  setHelp: (value: boolean | ((open: boolean) => boolean)) => void;
  pdfOpen: boolean;
  setPdfOpen: (value: boolean) => void;
  dataOpen: boolean;
  setDataOpen: (value: boolean) => void;
  upload: (file: File | undefined) => void;
}) {
  const input = React.useRef<HTMLInputElement>(null);
  return (
    <>
      <div className="import-upload-row">
        <div
          className={drag ? "import-drop drag" : "import-drop"}
          onDragOver={(event) => {
            event.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDrag(false);
            upload(event.dataTransfer.files[0]);
          }}
        >
          <p>Drop a PDF, Word document, or LinkedIn export here.</p>
          <button type="button" onClick={() => input.current?.click()} disabled={!!busy}>
            {busy || "Choose file"}
          </button>
          <input
            ref={input}
            type="file"
            accept={ACCEPT}
            hidden
            aria-label="Resume file"
            onChange={(event) => {
              upload(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </div>
        <button
          type="button"
          className="import-help-button"
          aria-label="How to download your LinkedIn profile"
          aria-expanded={help}
          aria-controls="import-linkedin-help"
          onClick={() => setHelp((open) => !open)}
        >
          ?
        </button>
      </div>
      {help && (
        <div id="import-linkedin-help" className="import-help-sections">
          <SectionBox
            title="Save your profile as a PDF"
            icon="document"
            open={pdfOpen}
            onToggle={() => setPdfOpen(!pdfOpen)}
          >
            <p>{LINKEDIN_PDF_HELP}</p>
          </SectionBox>
          <SectionBox
            title="Download your profile data"
            icon="document"
            open={dataOpen}
            onToggle={() => setDataOpen(!dataOpen)}
          >
            <p>{LINKEDIN_DATA_HELP}</p>
          </SectionBox>
        </div>
      )}
    </>
  );
}

function SectionBox({
  title,
  icon,
  count,
  open,
  onToggle,
  children,
}: {
  title: string;
  icon: AppIconName;
  count?: number;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <article className={`section-card ${open ? "expanded" : "collapsed"}`}>
      <div className="section-card-header">
        <span className="section-icon">
          <AppIcon name={icon} />
        </span>
        <strong>{title}</strong>
        {count !== undefined && <span className="item-count">{count}</span>}
        <button
          type="button"
          className="section-chevron"
          aria-expanded={open}
          aria-label={`${open ? "Collapse" : "Expand"} ${title}`}
          onClick={onToggle}
        >
          <span aria-hidden="true">
            <AppIcon name="chevron" />
          </span>
        </button>
      </div>
      {open && <div className="section-card-body">{children}</div>}
    </article>
  );
}

function RecordCard({
  title,
  meta,
  icon,
  included,
  open,
  onToggle,
  onIncluded,
  children,
}: {
  title: string;
  meta: string;
  icon: AppIconName;
  included: boolean;
  open: boolean;
  onToggle: () => void;
  onIncluded: (included: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <article className={`entry-card${included ? "" : " left-out"}`}>
      <div className="entry-card-header import-entry-header">
        <span className="section-icon">
          <AppIcon name={icon} />
        </span>
        <div>
          <div className="entry-title-row">
            <strong>{title}</strong>
          </div>
          {meta && (
            <div className="entry-meta">
              <span>{meta}</span>
            </div>
          )}
        </div>
        <label className="visibility-toggle">
          <input
            type="checkbox"
            role="switch"
            aria-checked={included}
            checked={included}
            onChange={(event) => onIncluded(event.target.checked)}
          />
          <span className="sr-only">{included ? "Leave out" : "Add"} {title}</span>
        </label>
        <button
          type="button"
          className="section-chevron"
          aria-expanded={open}
          aria-label={`${open ? "Collapse" : "Expand"} ${title}`}
          onClick={onToggle}
        >
          <span aria-hidden="true">
            <AppIcon name="chevron" />
          </span>
        </button>
      </div>
      {open && <div className="entry-card-body">{children}</div>}
    </article>
  );
}

function TextField({
  label,
  value,
  onChange,
  low = false,
  full = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  low?: boolean;
  full?: boolean;
}) {
  return (
    <label className={`${full ? "full" : ""} ${low ? "low" : ""}`.trim()}>
      {label}
      <input
        value={value}
        aria-invalid={low || undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function EntryCard({
  entry,
  open,
  onToggle,
  onChange,
  onRemove,
}: {
  entry: ImportEntry;
  open: boolean;
  onToggle: () => void;
  onChange: (patch: Partial<ImportEntry>) => void;
  onRemove: () => void;
}) {
  const low = (key: string) => entry.low_confidence.includes(key);
  const dates = (
    <>
      <MonthYearField
        label="Start"
        year={entry.start_year}
        month={entry.start_month}
        onChange={({ year, month }) => onChange({ start_year: year, start_month: month })}
      />
      <MonthYearField
        label="End"
        year={entry.end_year}
        month={entry.end_month}
        disabled={entry.is_current}
        onChange={({ year, month }) => onChange({ end_year: year, end_month: month })}
      />
      <label className="choice">
        <input
          type="checkbox"
          checked={entry.is_current}
          onChange={(event) =>
            onChange({
              is_current: event.target.checked,
              end_year: event.target.checked ? null : entry.end_year,
              end_month: event.target.checked ? null : entry.end_month,
            })
          }
        />
        Current role
      </label>
      <TextField
        label="Display date"
        value={entry.date_label}
        low={low("start_year")}
        onChange={(date_label) => onChange({ date_label })}
      />
    </>
  );
  return (
    <RecordCard
      title={entryTitle(entry)}
      meta={entryDate(entry)}
      icon={sectionIcon(entry.section)}
      included={entry.included}
      open={open}
      onToggle={onToggle}
      onIncluded={(included) => onChange({ included })}
    >
      {entry.low_confidence.length > 0 && (
        <p className="import-notice">Check the highlighted fields.</p>
      )}
      <div className="section-choices" role="group" aria-label="Section">
        {ENTRY_SECTIONS.map(([value, label, icon]) => (
          <button
            type="button"
            key={value}
            aria-pressed={entry.section === value}
            onClick={() => onChange({ section: value })}
          >
            <AppIcon name={icon} />
            {label}
          </button>
        ))}
      </div>
      <div className="form-grid">
        {(entry.section === "employment" || entry.section === "leadership") && (
          <>
            <TextField
              label="Organization"
              value={entry.organization}
              low={low("organization")}
              onChange={(organization) => onChange({ organization })}
            />
            <TextField
              label="Title"
              value={entry.title}
              low={low("title")}
              onChange={(title) => onChange({ title })}
            />
            <TextField
              label="Location"
              value={entry.location}
              onChange={(location) => onChange({ location })}
            />
            {dates}
          </>
        )}
        {entry.section === "project" && (
          <>
            <TextField
              label="Project name"
              value={entry.name}
              low={low("name")}
              onChange={(name) => onChange({ name })}
            />
            <TextField
              label="Subtitle"
              value={entry.subtitle}
              onChange={(subtitle) => onChange({ subtitle })}
            />
            <TextField
              label="Location"
              value={entry.location}
              onChange={(location) => onChange({ location })}
            />
            {dates}
          </>
        )}
        {entry.section === "education" && (
          <>
            <TextField
              label="Institution"
              value={entry.institution}
              low={low("institution")}
              onChange={(institution) => onChange({ institution })}
            />
            <TextField
              label="School"
              value={entry.college_school}
              onChange={(college_school) => onChange({ college_school })}
            />
            <TextField
              label="Location"
              value={entry.location}
              onChange={(location) => onChange({ location })}
            />
            <TextField
              label="Degree type"
              value={entry.degree_type}
              onChange={(degree_type) => onChange({ degree_type })}
            />
            <TextField
              label="Major"
              value={entry.degree_major}
              onChange={(degree_major) => onChange({ degree_major })}
            />
            <MonthYearField
              label="Graduation"
              year={entry.graduation_year}
              month={entry.graduation_month}
              onChange={({ year, month }) =>
                onChange({ graduation_year: year, graduation_month: month })
              }
            />
            <TextField
              label="Display date"
              value={entry.display_date}
              low={low("graduation_year")}
              onChange={(display_date) => onChange({ display_date })}
            />
          </>
        )}
        {entry.section === "skills" && (
          <>
            <TextField
              label="Group name"
              value={entry.name}
              onChange={(name) => onChange({ name })}
            />
            <ListField
              label="Skills"
              values={entry.tools}
              onChange={(tools) => onChange({ tools })}
            />
          </>
        )}
        {entry.section === "interests" && (
          <TextField
            label="Interest"
            value={entry.body}
            full
            onChange={(body) => onChange({ body })}
          />
        )}
      </div>
      {["employment", "leadership", "project", "education"].includes(entry.section) && (
        <ListField
          label="Bullets"
          values={entry.bullets}
          onChange={(bullets) => onChange({ bullets })}
        />
      )}
      {entry.source_text && <OriginalText text={entry.source_text} />}
      <button type="button" onClick={onRemove}>
        Remove
      </button>
    </RecordCard>
  );
}

function OriginalText({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <SectionBox title="Original text" icon="document" open={open} onToggle={() => setOpen(!open)}>
      <pre className="import-source">{text}</pre>
    </SectionBox>
  );
}

function ListField({
  label,
  values,
  onChange,
}: {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  return (
    <div className="full">
      <span>{label}</span>
      {values.map((value, index) => (
        <div className="import-bullet" key={`${label}-${index}`}>
          <textarea
            value={value}
            aria-label={`${label} ${index + 1}`}
            onChange={(event) =>
              onChange(values.map((item, itemIndex) => (itemIndex === index ? event.target.value : item)))
            }
          />
          <button
            type="button"
            onClick={() => onChange(values.filter((_, itemIndex) => itemIndex !== index))}
          >
            Remove
          </button>
        </div>
      ))}
      <button type="button" onClick={() => onChange([...values, ""])}>
        Add {label === "Bullets" ? "bullet" : "skill"}
      </button>
    </div>
  );
}

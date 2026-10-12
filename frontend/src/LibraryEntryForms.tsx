import React from "react";
import MonthYearField from "./MonthYearField";

export type LibraryEntryKind =
  | "employment"
  | "project"
  | "education"
  | "leadership"
  | "tool-group"
  | "interest"
  | "custom-section"
  | "custom-entry"
  | "profile"
  | "summary";
export const blankDrafts: Record<LibraryEntryKind, any> = {
  employment: {
    kind: "employment",
    organization: "",
    title: "",
    location: "",
    date_label: "",
    start_year: null,
    start_month: null,
    end_year: null,
    end_month: null,
    is_current: false,
    bullets: [],
  },
  project: {
    kind: "project",
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
  },
  education: {
    institution: "",
    college_school: "",
    location: "",
    degree_type: "",
    degree_major: "",
    graduation_year: null,
    graduation_month: null,
    display_date: "",
  },
  leadership: {
    kind: "leadership",
    organization: "",
    title: "",
    location: "",
    date_label: "",
    start_year: null,
    start_month: null,
    end_year: null,
    end_month: null,
    is_current: false,
    bullets: [],
  },
  "tool-group": { name: "" },
  interest: { body: "" },
  "custom-section": { title: "", layout: "list" },
  profile: {
    label: "",
    name: "",
    phone: "",
    email: "",
    linkedin_label: "",
    linkedin_url: "",
  },
  summary: { name: "", body: "" },
  "custom-entry": {
    section_id: "",
    primary_text: "",
    secondary_text: "",
    location: "",
    date_label: "",
    start_year: null,
    start_month: null,
    end_year: null,
    end_month: null,
    is_current: false,
  },
};
export const cloneBlankDraft = (kind: LibraryEntryKind) =>
  structuredClone(blankDrafts[kind]);

const GRADUATION_MONTHS = [
  "january",
  "february",
  "march",
  "april",
  "may",
  "june",
  "july",
  "august",
  "september",
  "october",
  "november",
  "december",
];

function parseGraduationLabel(value: string) {
  const text = value.trim();
  const yearMatch = text.match(/\b(?:19|20)\d{2}\b/);
  if (!yearMatch) return null;
  const lower = text.toLowerCase();
  const named = GRADUATION_MONTHS.findIndex((name) => lower.includes(name));
  const numeric = text.match(
    /\b(0?[1-9]|1[0-2])\s*[/-]\s*(?:19|20)\d{2}\b/,
  );
  const month = named >= 0 ? named + 1 : numeric ? Number(numeric[1]) : null;
  return { year: Number(yearMatch[0]), month };
}

// Older education rows keep the degree line and graduation text in `degree`
// and `graduation_date`. The form edits the split fields.
export function hydrateEducationDraft(draft: any) {
  if (!draft || typeof draft !== "object") return draft;
  const next = { ...draft };
  let changed = false;
  const degreeType = String(next.degree_type || "").trim();
  const degreeMajor = String(next.degree_major || "").trim();
  const legacyDegree = String(next.degree || "").trim();
  if (!degreeType && !degreeMajor && legacyDegree) {
    const comma = legacyDegree.indexOf(",");
    if (comma > 0) {
      next.degree_type = legacyDegree.slice(0, comma).trim();
      next.degree_major = legacyDegree.slice(comma + 1).trim();
    } else next.degree_major = legacyDegree;
    changed = true;
  }
  const legacyDate = String(next.graduation_date || "").trim();
  if (!String(next.display_date || "").trim() && legacyDate) {
    next.display_date = legacyDate;
    changed = true;
  }
  if (!next.graduation_year) {
    const parsed = parseGraduationLabel(
      String(next.display_date || next.graduation_date || ""),
    );
    if (parsed) {
      next.graduation_year = parsed.year;
      if (!next.graduation_month && parsed.month)
        next.graduation_month = parsed.month;
      changed = true;
    }
  }
  return changed ? next : draft;
}
export function profilePayload(draft: any) {
  return {
    label: (draft.label || "").trim(),
    name: (draft.name || "").trim(),
    phone: (draft.phone || "").trim(),
    email: (draft.email || "").trim(),
    linkedin_label: (draft.linkedin_label || "").trim(),
    linkedin_url: (draft.linkedin_url || "").trim(),
  };
}
export function profileWriteError(draft: any) {
  const next = profilePayload(draft);
  if (!next.label) return "Profile name is required.";
  if (!next.name) return "Name is required.";
  if (
    next.email &&
    (!next.email.includes("@") ||
      next.email.startsWith("@") ||
      next.email.endsWith("@"))
  )
    return "Enter a valid email address.";
  if (
    next.linkedin_url &&
    !next.linkedin_url.toLowerCase().startsWith("http://") &&
    !next.linkedin_url.toLowerCase().startsWith("https://")
  )
    return "LinkedIn URL must start with http:// or https://.";
  return "";
}
export function ProfileFieldsForm({
  draft,
  setDraft,
}: {
  draft: any;
  setDraft: (next: any) => void;
}) {
  const field = (
    key: string,
    label: string,
    required = false,
    full = false,
  ) => (
    <label className={full ? "full" : undefined}>
      {label}
      {required ? " *" : ""}
      <input
        value={draft[key] || ""}
        maxLength={key === "label" ? 120 : key === "name" ? 200 : 300}
        onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
      />
    </label>
  );
  return (
    <div className="form-grid">
      {field("label", "Profile name", true)}
      {field("name", "Name", true)}
      {field("email", "Email")}
      {field("phone", "Phone")}
      {field("linkedin_label", "LinkedIn text")}
      {field("linkedin_url", "LinkedIn URL", false, true)}
    </div>
  );
}
export function LibraryEntryForm({
  kind,
  draft,
  setDraft,
  error,
}: {
  kind: LibraryEntryKind;
  draft: any;
  setDraft: (x: any) => void;
  error?: string;
}) {
  const educationStamp = React.useRef("");
  React.useLayoutEffect(() => {
    if (kind !== "education" || !draft) return;
    const mark = `${draft.id ?? ""}|${draft.degree || ""}|${draft.graduation_date || ""}`;
    if (educationStamp.current === mark) return;
    educationStamp.current = mark;
    const next = hydrateEducationDraft(draft);
    if (next !== draft) setDraft(next);
  }, [kind, draft, setDraft]);
  if (kind === "profile")
    return <ProfileFieldsForm draft={draft} setDraft={setDraft} />;
  const field = (name: string, label: string) => (
    <label>
      {label}
      <input
        value={draft[name] ?? ""}
        onChange={(e) => setDraft({ ...draft, [name]: e.target.value })}
      />
      {error && error.toLowerCase().includes(name.replaceAll("_", " ")) ? (
        <span role="alert">{error}</span>
      ) : null}
    </label>
  );
  const dates = (
    <>
      <MonthYearField
        label="Start"
        year={draft.start_year}
        month={draft.start_month}
        onChange={({ year, month }) =>
          setDraft({ ...draft, start_year: year, start_month: month })
        }
      />
      <MonthYearField
        label="End"
        year={draft.end_year}
        month={draft.end_month}
        disabled={!!draft.is_current}
        onChange={({ year, month }) =>
          setDraft({ ...draft, end_year: year, end_month: month })
        }
      />
      <label className="choice">
        <input
          type="checkbox"
          checked={!!draft.is_current}
          onChange={(e) =>
            setDraft({
              ...draft,
              is_current: e.target.checked,
              end_year: e.target.checked ? null : draft.end_year,
              end_month: e.target.checked ? null : draft.end_month,
            })
          }
        />
        Current / ongoing
      </label>
      {field("date_label", "Display-date override")}
    </>
  );
  if (kind === "employment" || kind === "leadership")
    return (
      <div className="form-grid">
        {field("organization", "Organization")}
        {field(
          "title",
          kind === "leadership" ? "Leadership title" : "Job title",
        )}
        {field("location", "Location")}
        {dates}
      </div>
    );
  if (kind === "project")
    return (
      <div className="form-grid">
        {field("name", "Project name")}
        {field("subtitle", "Subtitle")}
        {field("location", "Location")}
        {dates}
      </div>
    );
  if (kind === "education")
    return (
      <div className="form-grid">
        {field("institution", "Institution")}
        {field("college_school", "College or school")}
        {field("degree_type", "Degree type")}
        {field("degree_major", "Degree or major")}
        {field("location", "Location")}
        <MonthYearField
          label="Graduation"
          year={draft.graduation_year}
          month={draft.graduation_month}
          onChange={({ year, month }) =>
            setDraft({
              ...draft,
              graduation_year: year,
              graduation_month: month,
            })
          }
        />
        {field("display_date", "Display-date override")}
      </div>
    );
  if (kind === "summary")
    return (
      <div className="form-grid">
        {field("name", "Summary name")}
        <label className="full">
          Summary
          <textarea
            value={draft.body || ""}
            rows={6}
            onChange={(event) =>
              setDraft({ ...draft, body: event.target.value })
            }
          />
        </label>
      </div>
    );
  if (kind === "tool-group")
    return <div className="form-grid">{field("name", "Group name")}</div>;
  if (kind === "interest")
    return <div className="form-grid">{field("body", "Interest")}</div>;
  if (kind === "custom-section")
    return (
      <div className="form-grid">
        {field("title", "Section title")}
        <div className="choice-field">
          <span id="custom-layout-label">Layout</span>
          <div
            className="layout-choices"
            role="group"
            aria-labelledby="custom-layout-label"
          >
            {(
              [
                ["list", "List"],
                ["compact", "Compact"],
                ["dated", "Dated"],
                ["experience", "Experience"],
              ] as const
            ).map(([value, label]) => (
              <button
                type="button"
                key={value}
                aria-pressed={(draft.layout || "list") === value}
                onClick={() => setDraft({ ...draft, layout: value })}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  return (
    <div className="form-grid">
      {field("primary_text", "Primary text")}
      {field("secondary_text", "Secondary text")}
      {field("location", "Location")}
      {dates}
    </div>
  );
}

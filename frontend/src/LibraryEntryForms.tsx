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
  | "custom-entry";
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
  if (kind === "tool-group")
    return <div className="form-grid">{field("name", "Group name")}</div>;
  if (kind === "interest")
    return <div className="form-grid">{field("body", "Interest")}</div>;
  if (kind === "custom-section")
    return (
      <div className="form-grid">
        {field("title", "Section title")}
        <label>
          Layout
          <select
            value={draft.layout}
            onChange={(e) => setDraft({ ...draft, layout: e.target.value })}
          >
            {["list", "compact", "dated", "experience"].map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
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

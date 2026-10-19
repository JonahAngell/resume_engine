import React from "react";

export type JobDraft = {
  company: string;
  role: string;
  title: string;
  body: string;
};

export const emptyJobDraft = (): JobDraft => ({
  company: "",
  role: "",
  title: "",
  body: "",
});

/** Company, role, title, and posting fields shared by the Jobs page and New Resume. */
export default function JobDescriptionFields({
  draft,
  setDraft,
}: {
  draft: JobDraft;
  setDraft: (next: JobDraft) => void;
}) {
  return (
    <div className="form-grid">
      <label>
        Company
        <input
          value={draft.company}
          maxLength={200}
          onChange={(event) => setDraft({ ...draft, company: event.target.value })}
        />
      </label>
      <label>
        Role
        <input
          value={draft.role}
          maxLength={200}
          onChange={(event) => setDraft({ ...draft, role: event.target.value })}
        />
      </label>
      <label className="full">
        Title
        <input
          value={draft.title}
          maxLength={300}
          placeholder="Optional. Defaults to company and role."
          onChange={(event) => setDraft({ ...draft, title: event.target.value })}
        />
      </label>
      <label className="full">
        Job description
        <textarea
          required
          value={draft.body}
          maxLength={50000}
          onChange={(event) => setDraft({ ...draft, body: event.target.value })}
        />
      </label>
    </div>
  );
}

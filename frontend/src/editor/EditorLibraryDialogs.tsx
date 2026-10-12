import { useState } from "react";
import {
  LibraryEntryForm,
  cloneBlankDraft,
  hydrateEducationDraft,
  profilePayload,
  profileWriteError,
  type LibraryEntryKind,
} from "../LibraryEntryForms";
import {
  LibraryEditDialog,
  LibraryPickerDialog,
  ManageSkillsDialog,
} from "./LibraryPickerDialog";

const FORM_KIND: Record<string, LibraryEntryKind> = {
  education: "education",
  projects: "project",
  work_experience: "employment",
  leadership: "leadership",
  tool_groups: "tool-group",
  personal_interests: "interest",
};
const ENTRY_SOURCE: Record<string, string> = {
  education: "education",
  projects: "projects",
  work_experience: "employment",
  leadership: "leadership",
  tool_groups: "tool_groups",
  personal_interests: "interests",
};
const ENTRY_TITLE: Record<string, (item: any) => string> = {
  education: (item) => item.institution,
  projects: (item) => item.name,
  work_experience: (item) => item.organization,
  leadership: (item) => item.organization,
  tool_groups: (item) => item.name,
  personal_interests: (item) => item.body,
};
const ENTRY_DETAIL: Record<string, (item: any) => string> = {
  education: (item) =>
    [item.degree_type, item.degree_major].filter(Boolean).join(", "),
  projects: (item) => item.subtitle || "",
  work_experience: (item) => item.title || "",
  leadership: (item) => item.title || "",
  tool_groups: (item) =>
    `${(item.items || []).filter((skill: any) => !skill.archived_at).length} skills`,
  personal_interests: () => "",
};

export function bulletChoices(rows: any[], placed: Set<string>) {
  const grouped = new Map<string, any[]>();
  for (const row of rows || []) {
    if (row.archived_at || row.variant_archived_at || !row.variant_id) continue;
    const id = String(row.id);
    if (placed.has(id)) continue;
    const list = grouped.get(id) || [];
    list.push(row);
    grouped.set(id, list);
  }
  return [...grouped.values()].flatMap((variants) =>
    variants.map((variant) => ({
      id: `${variant.id}:${variant.variant_id}`,
      bullet_id: variant.id,
      variant_id: variant.variant_id,
      body: variant.body,
      variant_name: variant.variant_name,
    })),
  );
}

function libraryItems(lib: any, section: string, included: string[]) {
  const source = lib[ENTRY_SOURCE[section]] || [];
  const taken = new Set(included);
  return source.filter(
    (item: any) => !item.archived_at && !taken.has(String(item.id)),
  );
}

function entryDraft(section: string, item?: any) {
  const kind = FORM_KIND[section];
  const draft = item ? { ...cloneBlankDraft(kind), ...item } : cloneBlankDraft(kind);
  delete draft.bullets;
  delete draft.id;
  return kind === "education" && item ? hydrateEducationDraft(draft) : draft;
}

function BulletEditDialog({
  initial,
  close,
  onSave,
}: {
  initial: string;
  close: () => void;
  onSave: (body: string) => Promise<void>;
}) {
  const [body, setBody] = useState(initial);
  return (
    <LibraryEditDialog
      title="Edit bullet"
      close={close}
      note="This updates the library wording and this resume. Other resumes keep their saved wording until they refresh it."
      onSave={async () => {
        if (!body.trim()) throw new Error("Bullet text is required.");
        await onSave(body.trim());
      }}
    >
      <label>
        Bullet
        <textarea
          rows={4}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
      </label>
    </LibraryEditDialog>
  );
}

function EditRecordDialog({
  title,
  kind,
  initial,
  close,
  onSave,
  note,
}: {
  title: string;
  kind: LibraryEntryKind;
  initial: any;
  close: () => void;
  onSave: (draft: any) => Promise<void>;
  note?: string;
}) {
  const [draft, setDraft] = useState(initial);
  return (
    <LibraryEditDialog title={title} close={close} note={note} onSave={() => onSave(draft)}>
      <LibraryEntryForm kind={kind} draft={draft} setDraft={setDraft} />
    </LibraryEditDialog>
  );
}

export function EditorLibraryDialogs({
  dialog,
  close,
  lib,
  includedIds,
  parentBullets,
  placedBulletIds,
  actions,
}: {
  dialog: any;
  close: () => void;
  lib: any;
  includedIds: (section: string) => string[];
  parentBullets: (section: string, parentId: string) => any[];
  placedBulletIds: Set<string>;
  actions: {
    pickProfile: (id: string) => Promise<void>;
    createProfile: (draft: any) => Promise<void>;
    saveProfile: (id: string, draft: any) => Promise<void>;
    pickSummary: (id: string | null) => Promise<void>;
    createSummary: (draft: any) => Promise<void>;
    saveSummary: (id: string, draft: any) => Promise<void>;
    pickEntry: (section: string, item: any, replaceId?: string) => Promise<void>;
    createEntry: (section: string, draft: any) => Promise<void>;
    saveEntry: (section: string, id: string, draft: any) => Promise<void>;
    pickBullet: (
      section: string,
      parentId: string,
      choice: any,
      placementId?: string,
    ) => Promise<void>;
    createBullet: (section: string, parentId: string, body: string) => Promise<void>;
    saveBullet: (placement: any, body: string) => Promise<void>;
    pickInterest: (item: any, replaceId?: string) => Promise<void>;
    createInterest: (draft: any) => Promise<void>;
    saveInterest: (id: string, draft: any) => Promise<void>;
    addSkill: (groupId: string, name: string) => Promise<void>;
    renameSkill: (groupId: string, id: string, name: string) => Promise<void>;
    archiveSkill: (id: string) => Promise<void>;
  };
}) {
  if (!dialog) return null;
  if (dialog.mode === "pick-profile") {
    const items = (lib.profiles || []).filter((item: any) => !item.archived_at);
    return (
      <LibraryPickerDialog
        title="Choose a profile"
        close={close}
        items={items}
        labelOf={(item) => item.name}
        detailOf={(item) => item.label}
        createLabel="Add profile"
        initialDraft={cloneBlankDraft("profile")}
        renderCreate={(draft, setDraft) => (
          <LibraryEntryForm kind="profile" draft={draft} setDraft={setDraft} />
        )}
        onPick={(item) => actions.pickProfile(item.id)}
        onCreate={async (draft) => {
          const message = profileWriteError(draft);
          if (message) throw new Error(message);
          await actions.createProfile(profilePayload(draft));
        }}
      />
    );
  }
  if (dialog.mode === "edit-profile") {
    return (
      <EditRecordDialog
        title="Edit profile"
        kind="profile"
        initial={{ ...dialog.item }}
        close={close}
        onSave={async (draft) => {
          const message = profileWriteError(draft);
          if (message) throw new Error(message);
          await actions.saveProfile(dialog.item.id, profilePayload(draft));
        }}
      />
    );
  }
  if (dialog.mode === "pick-summary") {
    const items = [
      { id: "", name: "No summary", body: "Leave this section empty" },
      ...(lib.summary_variants || []).filter((item: any) => !item.archived_at),
    ];
    return (
      <LibraryPickerDialog
        title="Choose a summary"
        close={close}
        items={items}
        labelOf={(item) => item.name}
        detailOf={(item) => item.body}
        createLabel="Add summary"
        initialDraft={cloneBlankDraft("summary")}
        renderCreate={(draft, setDraft) => (
          <LibraryEntryForm kind="summary" draft={draft} setDraft={setDraft} />
        )}
        onPick={(item) => actions.pickSummary(item.id || null)}
        onCreate={async (draft) => {
          if (!draft.name?.trim() || !draft.body?.trim())
            throw new Error("Summary name and text are required.");
          await actions.createSummary({
            name: draft.name.trim(),
            body: draft.body.trim(),
          });
        }}
      />
    );
  }
  if (dialog.mode === "edit-summary") {
    return (
      <EditRecordDialog
        title="Edit summary"
        kind="summary"
        initial={{ name: dialog.item.name, body: dialog.item.body }}
        close={close}
        onSave={async (draft) => {
          if (!draft.name?.trim() || !draft.body?.trim())
            throw new Error("Summary name and text are required.");
          await actions.saveSummary(dialog.item.id, {
            name: draft.name.trim(),
            body: draft.body.trim(),
          });
        }}
      />
    );
  }
  if (dialog.mode === "pick-entry" || dialog.mode === "pick-interest") {
    const section =
      dialog.mode === "pick-interest" ? "personal_interests" : dialog.section;
    const included = includedIds(section);
    const noun =
      section === "tool_groups"
        ? "skill group"
        : section === "personal_interests"
          ? "interest"
          : section.replaceAll("_", " ");
    return (
      <LibraryPickerDialog
        title={dialog.replaceId ? `Replace ${noun}` : `Add ${noun}`}
        close={close}
        items={libraryItems(lib, section, included)}
        labelOf={ENTRY_TITLE[section]}
        detailOf={ENTRY_DETAIL[section]}
        createLabel={`Add ${noun}`}
        initialDraft={entryDraft(section)}
        renderCreate={(draft, setDraft) => (
          <LibraryEntryForm
            kind={FORM_KIND[section]}
            draft={draft}
            setDraft={setDraft}
          />
        )}
        onPick={(item) =>
          section === "personal_interests"
            ? actions.pickInterest(item, dialog.replaceId)
            : actions.pickEntry(section, item, dialog.replaceId)
        }
        onCreate={(draft) =>
          section === "personal_interests"
            ? actions.createInterest(draft)
            : actions.createEntry(section, draft)
        }
      />
    );
  }
  if (dialog.mode === "edit-entry" || dialog.mode === "edit-interest") {
    const section =
      dialog.mode === "edit-interest" ? "personal_interests" : dialog.section;
    return (
      <EditRecordDialog
        title={`Edit ${ENTRY_TITLE[section](dialog.item)}`}
        kind={FORM_KIND[section]}
        initial={entryDraft(section, dialog.item)}
        close={close}
        onSave={(draft) =>
          section === "personal_interests"
            ? actions.saveInterest(dialog.item.id, draft)
            : actions.saveEntry(section, dialog.item.id, draft)
        }
      />
    );
  }
  if (dialog.mode === "pick-bullet") {
    const placed = new Set(placedBulletIds);
    if (dialog.currentBulletId) placed.delete(String(dialog.currentBulletId));
    const choices = bulletChoices(
      parentBullets(dialog.section, dialog.parentId),
      placed,
    );
    return (
      <LibraryPickerDialog
        title={dialog.placementId ? "Replace bullet" : "Add bullet"}
        close={close}
        items={choices}
        labelOf={(item) => item.body}
        detailOf={(item) => item.variant_name}
        createLabel="Add bullet"
        initialDraft={{ body: "" }}
        renderCreate={(draft, setDraft) => (
          <label>
            Bullet
            <textarea
              rows={4}
              value={draft.body}
              onChange={(event) =>
                setDraft({ ...draft, body: event.target.value })
              }
            />
          </label>
        )}
        onPick={(item) =>
          actions.pickBullet(
            dialog.section,
            dialog.parentId,
            item,
            dialog.placementId,
          )
        }
        onCreate={async (draft) => {
          if (!draft.body?.trim()) throw new Error("Bullet text is required.");
          await actions.createBullet(dialog.section, dialog.parentId, draft.body.trim());
        }}
      />
    );
  }
  if (dialog.mode === "edit-bullet") {
    return (
      <BulletEditDialog
        initial={dialog.placement.wording_snapshot || ""}
        close={close}
        onSave={(body) => actions.saveBullet(dialog.placement, body)}
      />
    );
  }
  if (dialog.mode === "manage-skills") {
    const group = (lib.tool_groups || []).find(
      (item: any) => item.id === dialog.groupId,
    );
    if (!group) return null;
    return (
      <ManageSkillsDialog
        group={group}
        close={close}
        onAdd={(name) => actions.addSkill(group.id, name)}
        onRename={(id, name) => actions.renameSkill(group.id, id, name)}
        onArchive={(id) => actions.archiveSkill(id)}
      />
    );
  }
  return null;
}

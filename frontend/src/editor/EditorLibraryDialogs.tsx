import { useState } from "react";
import ModalShell from "../ModalShell";
import {
  AiDraftPanel,
  JobSelect,
  LibraryReviewDialog,
  PickBadges,
  ReviewBanner,
  acceptAiWording,
  conflictMessage,
  useVariantPick,
  type AiDraft,
  type AiJobContext,
} from "./AiBulletTools";
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
  placementId,
  ai,
  close,
  onSave,
}: {
  initial: string;
  placementId: string;
  ai?: AiJobContext;
  close: () => void;
  onSave: (body: string) => Promise<void | false>;
}) {
  const [body, setBody] = useState(initial);
  const [aiDraft, setAiDraft] = useState<{ draft: AiDraft; model: string } | null>(null);
  return (
    <LibraryEditDialog
      title="Edit bullet"
      close={close}
      note={
        aiDraft
          ? "AI wording is saved as a new variant for this resume. Other resumes aren't changed."
          : "Choose how to keep this wording when you save."
      }
      onSave={async () => {
        if (!body.trim()) throw new Error("Bullet text is required.");
        if (body.trim() === initial.trim()) return;
        if (aiDraft && ai) {
          try {
            await ai.onApplied(
              await acceptAiWording(ai, placementId, aiDraft.draft, body, aiDraft.model),
            );
          } catch (reason) {
            throw new Error(conflictMessage(reason));
          }
          return;
        }
        return onSave(body.trim());
      }}
    >
      {ai && <ReviewBanner ai={ai} />}
      <label>
        Bullet
        <textarea
          rows={4}
          value={body}
          onChange={(event) => {
            setBody(event.target.value);
            if (!event.target.value.trim()) setAiDraft(null);
          }}
        />
      </label>
      {aiDraft && (
        <p className="ai-meta">
          From AI: {aiDraft.draft.name}.{" "}
          <button
            type="button"
            className="link-button"
            onClick={() => {
              setAiDraft(null);
              setBody(initial);
            }}
          >
            Undo
          </button>
        </p>
      )}
      {ai && (
        <section className="ai-panel" aria-label="AI wording">
          <h3 className="assist-section">
            <span aria-hidden="true">✦</span> AI wording
          </h3>
          <JobSelect ai={ai} />
          <AiDraftPanel
            ai={ai}
            placementId={placementId}
            selected={aiDraft?.draft.body}
            onPick={(draft, model) => {
              setAiDraft({ draft, model });
              setBody(draft.body);
            }}
          />
        </section>
      )}
    </LibraryEditDialog>
  );
}

function BulletSwitchDialog({
  ai,
  placement,
  choices,
  close,
  onPick,
  onCreate,
}: {
  ai?: AiJobContext;
  placement?: any;
  choices: any[];
  close: () => void;
  onPick: (choice: any) => Promise<void>;
  onCreate: (body: string) => Promise<void>;
}) {
  const replacing = !!placement;
  const [tab, setTab] = useState<"library" | "ai" | "create">("library");
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [aiDraft, setAiDraft] = useState<{ draft: AiDraft; model: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { result, loading, error: rankError } = useVariantPick(
    ai || ({ jobId: "" } as AiJobContext),
    ai && replacing ? [String(placement.id)] : null,
  );
  const slot = result?.slots[0];
  const ranked = new Map((slot?.candidates || []).map((item) => [item.variant_id, item]));
  const needle = query.trim().toLowerCase();
  const rows = [
    ...(slot?.candidates.filter((item) => !item.current).map((item) => ({ ...item, id: `${item.bullet_id}:${item.variant_id}`, variant_name: item.name })) || []),
    ...choices.filter(
      (item) => !ranked.has(String(item.variant_id)) && String(item.variant_id) !== String(placement?.variant_id),
    ),
  ].filter((item) => !needle || `${item.body} ${item.variant_name || ""}`.toLowerCase().includes(needle));
  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await work();
      close();
    } catch (reason: any) {
      setError(conflictMessage(reason));
    } finally {
      setBusy(false);
    }
  };
  const tabs: [typeof tab, string][] = [
    ["library", "Choose from Library"],
    ...(ai && replacing ? ([["ai", "New wording with AI"]] as [typeof tab, string][]) : []),
    ["create", "Write new"],
  ];
  return (
    <ModalShell
      title={replacing ? "Switch bullet" : "Add bullet"}
      close={close}
      className="library-picker bullet-switch-dialog"
    >
      {ai && <ReviewBanner ai={ai} />}
      {replacing && (
        <blockquote className="assist-original">{placement.wording_snapshot}</blockquote>
      )}
      <div
        className="picker-tabs"
        role="tablist"
        style={{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)` }}
      >
        {tabs.map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "library" && (
        <>
          {ai && replacing && (
            <div className="switch-rank-bar">
              <JobSelect ai={ai} label="Rank for job" />
              {loading && <span className="ai-meta" role="status">Ranking…</span>}
              {!loading && result && (
                <span className="ai-meta">
                  {result.status !== "ok"
                    ? result.detail
                    : result.method === "ai"
                      ? "Ranked by AI fit and job keywords."
                      : "Ranked by job keywords."}
                </span>
              )}
              {rankError && <span className="ai-meta">{rankError}</span>}
            </div>
          )}
          {slot && !slot.recommend && slot.candidates.length > 1 && (
            <p className="ai-meta">The wording on your resume is already the best match for this job.</p>
          )}
          <label>
            Search
            <input value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
          <div className="picker-results">
            {rows.length ? (
              rows.map((item: any) => {
                const rank = ranked.get(String(item.variant_id));
                return (
                  <button
                    type="button"
                    key={item.id}
                    className={`entry-picker-result ${rank && slot?.recommend && rank.key === slot.best_key ? "pick-best" : ""}`}
                    disabled={busy}
                    onClick={() =>
                      run(() =>
                        onPick({ bullet_id: item.bullet_id, variant_id: item.variant_id }),
                      )
                    }
                  >
                    <strong>{item.body}</strong>
                    <span>
                      {item.variant_name}
                      {String(item.bullet_id) === String(placement?.bullet_id) ? " · variant of this bullet" : ""}
                    </span>
                    {rank && (
                      <PickBadges
                        option={rank}
                        method={result?.method || "keywords"}
                        best={rank.key === slot?.best_key && slot?.recommend}
                      />
                    )}
                    {rank?.reason && <small className="ai-meta">{rank.reason}</small>}
                  </button>
                );
              })
            ) : (
              <p className="library-note">
                {needle
                  ? "Nothing in the library matches."
                  : "No other saved wording for this entry yet."}
                {ai && replacing && (
                  <>
                    {" "}
                    <button type="button" className="link-button" onClick={() => setTab("ai")}>
                      Write new wording with AI
                    </button>
                  </>
                )}
              </p>
            )}
          </div>
        </>
      )}
      {tab === "ai" && ai && replacing && (
        <>
          <JobSelect ai={ai} />
          <AiDraftPanel
            ai={ai}
            placementId={String(placement.id)}
            selected={aiDraft?.draft.body}
            onPick={(next, model) => {
              setAiDraft({ draft: next, model });
              setDraft(next.body);
            }}
          />
          {aiDraft && (
            <label>
              Wording to use
              <textarea rows={3} value={draft} onChange={(event) => setDraft(event.target.value)} />
            </label>
          )}
          <p className="library-note">Saved as a new variant of this bullet for this resume. Other resumes aren't changed.</p>
          <div className="form-actions">
            <button type="button" onClick={close}>
              Cancel
            </button>
            <button
              type="button"
              className="primary"
              disabled={busy || !aiDraft || !draft.trim()}
              onClick={() =>
                run(async () => {
                  await ai.onApplied(
                    await acceptAiWording(ai, String(placement.id), aiDraft!.draft, draft, aiDraft!.model),
                  );
                })
              }
            >
              Use this wording
            </button>
          </div>
        </>
      )}
      {tab === "create" && (
        <>
          <label>
            Bullet
            <textarea rows={4} value={draft} onChange={(event) => setDraft(event.target.value)} />
          </label>
          <div className="form-actions">
            <button type="button" onClick={close}>
              Cancel
            </button>
            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  if (!draft.trim()) throw new Error("Bullet text is required.");
                  await onCreate(draft.trim());
                })
              }
            >
              Save to library
            </button>
          </div>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </ModalShell>
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
  onSave: (draft: any) => Promise<void | false>;
  note?: string;
}) {
  const [draft, setDraft] = useState(initial);
  return (
    <LibraryEditDialog
      title={title}
      close={close}
      note={note}
      onSave={async () => {
        if (JSON.stringify(draft) === JSON.stringify(initial)) return;
        return onSave(draft);
      }}
    >
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
  ai,
}: {
  ai?: AiJobContext;
  dialog: any;
  close: () => void;
  lib: any;
  includedIds: (section: string) => string[];
  parentBullets: (section: string, parentId: string) => any[];
  placedBulletIds: Set<string>;
  actions: {
    pickProfile: (id: string) => Promise<void>;
    createProfile: (draft: any) => Promise<void>;
    saveProfile: (id: string, draft: any) => Promise<void | false>;
    pickSummary: (id: string | null) => Promise<void>;
    createSummary: (draft: any) => Promise<void>;
    saveSummary: (id: string, draft: any) => Promise<void | false>;
    pickEntry: (section: string, item: any, replaceId?: string) => Promise<void>;
    createEntry: (section: string, draft: any) => Promise<void>;
    saveEntry: (section: string, id: string, draft: any) => Promise<void | false>;
    pickBullet: (
      section: string,
      parentId: string,
      choice: any,
      placementId?: string,
    ) => Promise<void>;
    createBullet: (section: string, parentId: string, body: string) => Promise<void>;
    saveBullet: (placement: any, body: string) => Promise<void | false>;
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
        note="Choose how to keep this change when you save."
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
        note="Choose how to keep this change when you save."
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
        note={
          section === "personal_interests" || section === "tool_groups"
            ? undefined
            : "Choose how to keep this change when you save."
        }
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
      <BulletSwitchDialog
        ai={ai}
        placement={dialog.placement}
        choices={choices}
        close={close}
        onPick={(item) =>
          actions.pickBullet(
            dialog.section,
            dialog.parentId,
            item,
            dialog.placementId,
          )
        }
        onCreate={(body) => actions.createBullet(dialog.section, dialog.parentId, body)}
      />
    );
  }
  if (dialog.mode === "edit-bullet") {
    return (
      <BulletEditDialog
        initial={dialog.placement.wording_snapshot || ""}
        placementId={String(dialog.placement.id)}
        ai={ai}
        close={close}
        onSave={(body) => actions.saveBullet(dialog.placement, body)}
      />
    );
  }
  if (dialog.mode === "ai-review" && ai) {
    return <LibraryReviewDialog ai={ai} close={close} />;
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

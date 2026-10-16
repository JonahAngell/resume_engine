import { useState, type ReactNode } from "react";
import { AppIcon } from "../AppIcon";
import ModalShell from "../ModalShell";

const LIBRARY_NOTE =
  "This updates the library record. Other resumes that use it will update too.";

export function RecordActions({
  name,
  onEdit,
  onReplace,
  onRemove,
}: {
  name: string;
  onEdit?: () => void;
  onReplace?: () => void;
  onRemove?: () => void;
}) {
  return (
    <span className="record-actions">
      {onEdit && (
        <button type="button" aria-label={`Edit ${name}`} onClick={onEdit}>
          <AppIcon name="pencil" />
        </button>
      )}
      {onReplace && (
        <button
          type="button"
          aria-label={`Replace ${name}`}
          onClick={onReplace}
        >
          <AppIcon name="replace" />
        </button>
      )}
      {onRemove && (
        <button
          type="button"
          aria-label={`Remove ${name} from this resume`}
          onClick={onRemove}
        >
          <AppIcon name="bin" />
        </button>
      )}
    </span>
  );
}

export function LibraryEditDialog({
  title,
  close,
  children,
  onSave,
  note = LIBRARY_NOTE,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
  onSave: () => Promise<void | false>;
  note?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await onSave();
      if (result !== false) close();
    } catch (e: any) {
      setError(e.message || "Could not save this library record");
    } finally {
      setBusy(false);
    }
  };
  return (
    <ModalShell title={title} close={close}>
      <p className="library-note">{note}</p>
      {children}
      {error && <p role="alert">{error}</p>}
      <div className="form-actions">
        <button type="button" onClick={close}>
          Cancel
        </button>
        <button type="button" className="primary" disabled={busy} onClick={save}>
          Save
        </button>
      </div>
    </ModalShell>
  );
}

export function LibraryPickerDialog({
  title,
  close,
  items,
  labelOf,
  detailOf,
  createLabel,
  initialDraft,
  renderCreate,
  onPick,
  onCreate,
  extra,
}: {
  title: string;
  close: () => void;
  items: any[];
  labelOf: (item: any) => string;
  detailOf?: (item: any) => string;
  createLabel: string;
  initialDraft: any;
  renderCreate: (draft: any, setDraft: (next: any) => void) => ReactNode;
  onPick: (item: any) => Promise<void>;
  onCreate: (draft: any) => Promise<void>;
  extra?: ReactNode;
}) {
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<"library" | "create">("library");
  const [draft, setDraft] = useState(initialDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const needle = query.trim().toLowerCase();
  const shown = items.filter((item) => {
    const hay = `${labelOf(item)} ${detailOf?.(item) || ""}`.toLowerCase();
    return !needle || hay.includes(needle);
  });
  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await work();
      close();
    } catch (e: any) {
      setError(e.message || "Could not update this resume");
    } finally {
      setBusy(false);
    }
  };
  return (
    <ModalShell title={title} close={close} className="library-picker">
      <div className="picker-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "library"}
          onClick={() => setTab("library")}
        >
          Choose from Library
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "create"}
          onClick={() => setTab("create")}
        >
          {createLabel}
        </button>
      </div>
      {tab === "library" ? (
        <>
          <label>
            Search
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <div className="picker-results">
            {shown.length ? (
              shown.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className="entry-picker-result"
                  disabled={busy}
                  onClick={() => run(() => onPick(item))}
                >
                  <strong>{labelOf(item)}</strong>
                  {detailOf?.(item) && <span>{detailOf(item)}</span>}
                </button>
              ))
            ) : (
              <p className="library-note">Nothing in the library matches.</p>
            )}
          </div>
          {extra}
        </>
      ) : (
        <>
          {renderCreate(draft, setDraft)}
          <div className="form-actions">
            <button type="button" onClick={close}>
              Cancel
            </button>
            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={() => run(() => onCreate(draft))}
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

export function ManageSkillsDialog({
  group,
  close,
  onAdd,
  onRename,
  onArchive,
}: {
  group: { id: string; name: string; items?: any[] };
  close: () => void;
  onAdd: (name: string) => Promise<void>;
  onRename: (id: string, name: string) => Promise<void>;
  onArchive: (id: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const skills = (group.items || []).filter((item) => !item.archived_at);
  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e: any) {
      setError(e.message || "Could not update this skill group");
    } finally {
      setBusy(false);
    }
  };
  return (
    <ModalShell title={`Skills in ${group.name}`} close={close}>
      <p className="library-note">
        Adding or removing a skill changes the library group. Resumes that
        include the group pick up new skills until you hide them.
      </p>
      <div className="picker-results">
        {skills.map((skill) => (
          <div className="skill-manage-row" key={skill.id}>
            <input
              aria-label={`Skill name for ${skill.name}`}
              value={drafts[skill.id] ?? skill.name}
              onChange={(event) =>
                setDrafts({ ...drafts, [skill.id]: event.target.value })
              }
            />
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                run(() => onRename(skill.id, drafts[skill.id] ?? skill.name))
              }
            >
              Save
            </button>
            <button
              type="button"
              aria-label={`Remove ${skill.name} from this group`}
              disabled={busy}
              onClick={() => run(() => onArchive(skill.id))}
            >
              <AppIcon name="bin" />
            </button>
          </div>
        ))}
        {!skills.length && (
          <p className="library-note">This group has no skills yet.</p>
        )}
      </div>
      <label>
        New skill
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      {error && <p role="alert">{error}</p>}
      <div className="form-actions">
        <button type="button" onClick={close}>
          Done
        </button>
        <button
          type="button"
          className="primary"
          disabled={busy || !name.trim()}
          onClick={() =>
            run(async () => {
              await onAdd(name.trim());
              setName("");
            })
          }
        >
          Add skill
        </button>
      </div>
    </ModalShell>
  );
}

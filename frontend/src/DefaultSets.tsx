import React, { useState } from "react";
import { api } from "./api";
import { confirmDialog } from "./ConfirmDialog";

export type DefaultSet = {
  id: string;
  name: string;
  description?: string;
  is_default: boolean;
  entry_count: number;
  bullet_count: number;
};
export type SetMember = {
  set_id: string;
  item_type: string;
  item_id: string;
  variant_id: string | null;
};
export type VariantOption = { id: string; label: string };

const activeSets = (lib: any): DefaultSet[] => lib.default_sets || [];
const membersOf = (lib: any): SetMember[] => lib.default_set_members || [];
const clip = (text: string, size = 70) =>
  text.length > size ? `${text.slice(0, size - 1)}…` : text;

export function bulletVariantOptions(variants: any[]): VariantOption[] {
  return variants
    .filter((v: any) => !v.archived_at && !v.variant_archived_at)
    .map((v: any) => ({
      id: v.variant_id || v.id,
      label: `${v.variant_name || v.name || "Variant"}: ${clip(v.body || "")}`,
    }));
}

async function saveMemberships(
  itemType: string,
  itemId: string,
  memberships: { set_id: string; variant_id: string | null }[],
) {
  await api("/api/default-sets/memberships", {
    method: "PUT",
    body: JSON.stringify({ item_type: itemType, item_id: itemId, memberships }),
  });
}

/** Which defaults sets one record belongs to, with the wording each set uses. */
export function SetMembershipEditor({
  lib,
  itemType,
  itemId,
  label,
  variants,
  reloadLibrary,
  setError,
}: {
  lib: any;
  itemType: string;
  itemId: string;
  label?: string;
  variants?: VariantOption[];
  reloadLibrary: () => Promise<any>;
  setError: (message: string) => void;
}) {
  const sets = activeSets(lib);
  const current = membersOf(lib).filter(
    (m) => m.item_type === itemType && m.item_id === itemId,
  );
  const [busy, setBusy] = useState(false);
  const change = async (next: { set_id: string; variant_id: string | null }[]) => {
    setBusy(true);
    try {
      await saveMemberships(itemType, itemId, next);
      await reloadLibrary();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const membership = current.map((m) => ({ set_id: m.set_id, variant_id: m.variant_id }));
  if (!sets.length)
    return (
      <p className="set-empty">
        No defaults sets yet. Create one under Defaults sets in this Library.
      </p>
    );
  return (
    <fieldset className="set-membership" disabled={busy} aria-busy={busy}>
      {label && <legend>{label}</legend>}
      {sets.map((set) => {
        const row = current.find((m) => m.set_id === set.id);
        return (
          <div className="set-membership-row" key={set.id}>
            <label>
              <input
                type="checkbox"
                checked={!!row}
                onChange={(event) =>
                  change(
                    event.target.checked
                      ? [...membership, { set_id: set.id, variant_id: null }]
                      : membership.filter((m) => m.set_id !== set.id),
                  )
                }
              />
              {set.name}
            </label>
            {row && variants && variants.length > 1 && (
              <select
                aria-label={`Wording for ${set.name}`}
                value={row.variant_id || ""}
                onChange={(event) =>
                  change(
                    membership.map((m) =>
                      m.set_id === set.id
                        ? { ...m, variant_id: event.target.value || null }
                        : m,
                    ),
                  )
                }
              >
                <option value="">Default wording</option>
                {variants.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            )}
          </div>
        );
      })}
    </fieldset>
  );
}

/** The Defaults sets section of the Library: create, rename, default, archive, and contents. */
export function DefaultSetResults({
  lib,
  reloadLibrary,
  setError,
  query,
}: {
  lib: any;
  reloadLibrary: () => Promise<any>;
  setError: (message: string) => void;
  query: string;
}) {
  const [name, setName] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);
  const run = async (fn: () => Promise<any>) => {
    try {
      await fn();
      await reloadLibrary();
    } catch (e: any) {
      setError(e.message);
    }
  };
  const sets = activeSets(lib).filter((set) =>
    set.name.toLowerCase().includes(query.trim().toLowerCase()),
  );
  return (
    <div className="default-sets">
      <form
        className="default-set-create"
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim()) return;
          run(async () => {
            await api("/api/default-sets", {
              method: "POST",
              body: JSON.stringify({ name: name.trim() }),
            });
            setName("");
          });
        }}
      >
        <label>
          <span className="sr-only">New defaults set name</span>
          <input
            value={name}
            maxLength={120}
            placeholder="New defaults set, e.g. Engineering"
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <button type="submit" className="primary" disabled={!name.trim()}>
          Create set
        </button>
      </form>
      <p className="set-hint">
        Add records to a set from each entry's or bullet's <strong>Defaults sets</strong> tab.
        Each set can use different wording for the same bullet.
      </p>
      {!sets.length ? (
        <div className="library-state">
          <strong>No defaults sets</strong>
          <span>Create a set, then choose which records and wording it includes.</span>
        </div>
      ) : (
        <div className="default-set-list">
          {sets.map((set) => (
            <article key={set.id} className="default-set-card">
              <header>
                {renaming?.id === set.id ? (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      run(async () => {
                        await api(`/api/default-sets/${set.id}`, {
                          method: "PUT",
                          body: JSON.stringify({ name: renaming.name, description: set.description || "" }),
                        });
                        setRenaming(null);
                      });
                    }}
                  >
                    <input
                      aria-label="Set name"
                      value={renaming.name}
                      maxLength={120}
                      onChange={(event) => setRenaming({ id: set.id, name: event.target.value })}
                    />
                    <button type="submit" disabled={!renaming.name.trim()}>
                      Save
                    </button>
                    <button type="button" onClick={() => setRenaming(null)}>
                      Cancel
                    </button>
                  </form>
                ) : (
                  <strong>{set.name}</strong>
                )}
                {set.is_default && <span className="status-badge default">Default</span>}
              </header>
              <p>
                {set.entry_count} {set.entry_count === 1 ? "record" : "records"} ·{" "}
                {set.bullet_count} {set.bullet_count === 1 ? "bullet" : "bullets"}
              </p>
              <div className="form-actions">
                <button
                  type="button"
                  aria-expanded={open === set.id}
                  onClick={() => setOpen(open === set.id ? null : set.id)}
                >
                  {open === set.id ? "Hide contents" : "Contents"}
                </button>
                <button type="button" onClick={() => setRenaming({ id: set.id, name: set.name })}>
                  Rename
                </button>
                {!set.is_default && (
                  <button
                    type="button"
                    onClick={() => run(() => api(`/api/default-sets/${set.id}/default`, { method: "POST" }))}
                  >
                    Make default
                  </button>
                )}
                <button
                  type="button"
                  className="danger-text"
                  onClick={async () => {
                    if (
                      !(await confirmDialog({
                        title: "Archive defaults set",
                        message: `Archive “${set.name}”? Resumes already made from it stay as they are.`,
                        confirmLabel: "Archive",
                        danger: true,
                      }))
                    )
                      return;
                    run(() =>
                      api(`/api/default-sets/${set.id}/archive`, {
                        method: "POST",
                        body: JSON.stringify({ archived: true }),
                      }),
                    );
                  }}
                >
                  Archive
                </button>
              </div>
              {open === set.id && (
                <SetContents lib={lib} set={set} run={run} />
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

const ENTRY_GROUPS: [string, string, (lib: any) => any[], (row: any) => string][] = [
  ["content_item", "Experience", (lib) => lib.employment || [], (r) => r.title || r.organization || r.name],
  ["content_item", "Projects", (lib) => lib.projects || [], (r) => r.name || r.title],
  ["content_item", "Leadership", (lib) => lib.leadership || [], (r) => r.title || r.organization || r.name],
  ["education_item", "Education", (lib) => lib.education || [], (r) => r.institution],
  ["tool_group", "Skills", (lib) => lib.tool_groups || [], (r) => r.name],
  ["interest", "Interests", (lib) => lib.interests || [], (r) => r.body],
  ["custom_section", "Custom sections", (lib) => lib.custom_sections || [], (r) => r.title],
];

function bulletsOf(row: any) {
  const seen = new Map<string, string>();
  for (const line of row.bullets || []) {
    if (line.archived_at) continue;
    if (!seen.has(line.id) || line.is_default) seen.set(line.id, line.body || "");
  }
  return seen;
}

function SetContents({
  lib,
  set,
  run,
}: {
  lib: any;
  set: DefaultSet;
  run: (fn: () => Promise<any>) => Promise<void>;
}) {
  const members = membersOf(lib).filter((m) => m.set_id === set.id);
  const has = (type: string, id: string) =>
    members.some((m) => m.item_type === type && m.item_id === id);
  const others = (type: string, id: string) =>
    membersOf(lib)
      .filter((m) => m.item_type === type && m.item_id === id && m.set_id !== set.id)
      .map((m) => ({ set_id: m.set_id, variant_id: m.variant_id }));
  const toggle = (type: string, id: string, on: boolean, variant: string | null = null) =>
    run(() =>
      saveMemberships(type, id, [
        ...others(type, id),
        ...(on ? [{ set_id: set.id, variant_id: variant }] : []),
      ]),
    );
  const summary = members.find((m) => m.item_type === "summary")?.item_id || "";
  const profile = members.find((m) => m.item_type === "profile");
  const summaries = (lib.summary_variants || []).filter((s: any) => !s.archived_at);
  const profiles = (lib.profiles || []).filter((p: any) => !p.archived_at);
  const wordingName = (bulletRow: any[], variantId: string | null) =>
    variantId
      ? bulletRow.find((v: any) => v.variant_id === variantId)?.variant_name || "Chosen wording"
      : "Default wording";
  return (
    <div className="set-contents">
      <label>
        Summary
        <select
          value={summary}
          onChange={(event) => {
            const next = event.target.value;
            run(async () => {
              if (summary) await saveMemberships("summary", summary, others("summary", summary));
              if (next)
                await saveMemberships("summary", next, [
                  ...others("summary", next),
                  { set_id: set.id, variant_id: null },
                ]);
            });
          }}
        >
          <option value="">No summary</option>
          {summaries.map((s: any) => (
            <option key={s.id} value={s.id}>
              {s.name}: {clip(s.body || "", 60)}
            </option>
          ))}
        </select>
      </label>
      {profiles.length > 0 && (
        <label>
          Profile
          <select
            value={profile ? `${profile.item_id}|${profile.variant_id || ""}` : ""}
            onChange={(event) => {
              const [id, variant] = event.target.value.split("|");
              run(async () => {
                if (profile)
                  await saveMemberships("profile", profile.item_id, others("profile", profile.item_id));
                if (id)
                  await saveMemberships("profile", id, [
                    ...others("profile", id),
                    { set_id: set.id, variant_id: variant || null },
                  ]);
              });
            }}
          >
            <option value="">Default profile</option>
            {profiles.flatMap((p: any) => [
              <option key={p.id} value={`${p.id}|`}>
                {p.label || p.name}
              </option>,
              ...(p.field_variants || [])
                .filter((v: any) => !v.archived_at && !v.is_default)
                .map((v: any) => (
                  <option key={v.id} value={`${p.id}|${v.id}`}>
                    {p.label || p.name} · {v.name}
                  </option>
                )),
            ])}
          </select>
        </label>
      )}
      {ENTRY_GROUPS.map(([type, title, rows, name]) => {
        const active = rows(lib).filter((r: any) => !r.archived_at);
        if (!active.length) return null;
        return (
          <fieldset key={title} className="set-group">
            <legend>{title}</legend>
            {active.map((row: any) => {
              const included = has(type, row.id);
              const bullets = bulletsOf(row);
              return (
                <div key={row.id} className="set-entry">
                  <label>
                    <input
                      type="checkbox"
                      checked={included}
                      onChange={(event) => toggle(type, row.id, event.target.checked)}
                    />
                    {name(row) || "Untitled"}
                  </label>
                  {included && bullets.size > 0 && (
                    <ul>
                      {[...bullets].map(([id, body]) => {
                        const member = members.find((m) => m.item_type === "bullet" && m.item_id === id);
                        const variants = (row.bullets || []).filter((l: any) => l.id === id);
                        return (
                          <li key={id}>
                            <label>
                              <input
                                type="checkbox"
                                checked={!!member}
                                onChange={(event) => toggle("bullet", id, event.target.checked)}
                              />
                              {clip(body, 110)}
                            </label>
                            {member && variants.length > 1 && (
                              <span className="set-wording">{wordingName(variants, member.variant_id)}</span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              );
            })}
          </fieldset>
        );
      })}
    </div>
  );
}

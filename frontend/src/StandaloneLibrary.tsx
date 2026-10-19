import { AppIcon } from "./AppIcon";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import ModalShell from "./ModalShell";
import { confirmDialog } from "./ConfirmDialog";
import { SectionHelp } from "./SectionHelp";
import { bulletCoaching } from "./resumeCoaching";
import compactLogo from "./assets/logo-compact.png";
import {
  LibraryEntryForm,
  LibraryEntryKind,
  cloneBlankDraft,
  hydrateEducationDraft,
  profilePayload,
  profileWriteError,
} from "./LibraryEntryForms";
import ChoiceList from "./ChoiceList";
import {
  DefaultSetResults,
  SetMembershipEditor,
  bulletVariantOptions,
} from "./DefaultSets";

type Status = "active" | "archived" | "all";
type View = "list" | "card";
const SECTIONS = [
  ["", "All Items", "all-items"],
  ["default-sets", "Defaults sets", "library"],
  ["profile", "Profile", "profile"],
  ["experience", "Experience", "experience"],
  ["projects", "Projects", "projects"],
  ["education", "Education", "education"],
  ["leadership", "Leadership", "leadership"],
  ["skills", "Skills", "skills"],
  ["interests", "Interests", "interests"],
  ["custom", "Custom Sections", "custom-sections"],
] as const;
const DEFAULT_PAGE_SIZE = 8;
const MIN_LIST_ROW_HEIGHT = 56;
const TARGET_CARD_HEIGHT = 190;
const sectionIconName = (section: string) =>
  SECTIONS.find(([key]) => key === section)?.[2] || "custom-sections";
const sectionLabel = (section: string) =>
  SECTIONS.find(([key]) => key === section)?.[1] || section;

export default function StandaloneLibrary({
  lib,
  onHome,
  onBin,
  onJobs,
  onOpenResume,
  reloadLibrary,
  onReturnToResume,
}: any) {
  const [query, setQuery] = useState("");
  const initialTarget = useMemo(() => {
    try {
      return JSON.parse(
        sessionStorage.getItem("resume-engine-library-target") || "null",
      );
    } catch {
      return null;
    }
  }, []);
  const [section, setSection] = useState(initialTarget?.sectionKey || "");
  const [contentView, setContentView] = useState<"entries" | "bullets">(
    () =>
      initialTarget?.contentView ||
      (localStorage.getItem("resume-engine-library-content-view") === "bullets"
        ? "bullets"
        : "entries"),
  );
  const [entryDetail, setEntryDetail] = useState<any>(null);
  const [entryConfirmed, setEntryConfirmed] = useState<any>(null);
  const [entryTab, setEntryTab] = useState<
    "details" | "bullets" | "variants" | "usage" | "sets"
  >("details");
  const [createKind, setCreateKind] = useState<LibraryEntryKind | null>(
    initialTarget?.createKind || null,
  );
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [status, setStatus] = useState<Status>("active");
  const [view, setView] = useState<View>(() =>
    localStorage.getItem("resume-engine-library-view") === "card"
      ? "card"
      : "list",
  );
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [data, setData] = useState<any>({
    items: [],
    page: 1,
    total_items: 0,
    total_pages: 0,
  });
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const [confirmed, setConfirmed] = useState<any>(null);
  const [tab, setTab] = useState("details");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [bulkDialog, setBulkDialog] = useState<"tag" | "move" | "set" | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const resultsRef = useRef<HTMLElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const paginationRef = useRef<HTMLElement>(null);
  const measureFrame = useRef<number | null>(null);
  const load = async (requested = page) => {
    setBusy(true);
    setError("");
    try {
      if (section === "default-sets") {
        setData({ items: [], total_items: 0, total_pages: 1, page: 1 });
        setSelected([]);
        setDetail(null);
        return;
      }
      const params = new URLSearchParams({
        q: query,
        status,
        section,
        page: String(requested),
        page_size: String(pageSize),
      });
      const bulletSections = SECTIONS.map(([key]) => key).filter(
        (key) => key && key !== section && key !== "default-sets",
      );
      const [items, bulletTotals] = await Promise.all([
        api<any>(`/api/library-management/items?${params}`),
        Promise.all(
          bulletSections.map(async (key) => {
            const countParams = new URLSearchParams({
              q: query,
              status,
              section: key,
              page: "1",
              page_size: "1",
            });
            const row = await api<any>(
              `/api/library-management/items?${countParams}`,
            );
            return [key, row.total_items || 0] as const;
          }),
        ),
      ]);
      if (items.total_pages && requested > items.total_pages)
        return load(items.total_pages);
      const nextCounts: Record<string, number> = {};
      for (const [key, total] of bulletTotals) nextCounts[key] = total;
      if (section) nextCounts[section] = items.total_items || 0;
      nextCounts.all = SECTIONS.reduce(
        (sum, [key]) => (key ? sum + (nextCounts[key] || 0) : sum),
        0,
      );
      setData(items);
      setCounts(nextCounts);
      setPage(items.page);
      setSelected((x) =>
        x.filter((id) => items.items.some((r: any) => r.id === id)),
      );
      if (detail && !items.items.some((r: any) => r.id === detail.id)) {
        setDetail(null);
        setConfirmed(null);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    load(1);
  }, [query, section, status, pageSize]);
  useEffect(() => {
    const panel = resultsRef.current;
    if (!panel || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      if (measureFrame.current !== null)
        cancelAnimationFrame(measureFrame.current);
      measureFrame.current = requestAnimationFrame(() => {
        const viewport = viewportRef.current;
        if (
          !viewport ||
          viewport.clientHeight <= 0 ||
          viewport.clientWidth <= 0
        )
          return;
        let next = DEFAULT_PAGE_SIZE;
        if (view === "list") {
          const header = viewport.querySelector<HTMLElement>(
            ".library-table-head",
          );
          const available = Math.max(
            MIN_LIST_ROW_HEIGHT,
            viewport.clientHeight - (header?.offsetHeight || 40),
          );
          next = Math.floor(available / MIN_LIST_ROW_HEIGHT);
        } else {
          const styles = getComputedStyle(viewport);
          const minCardWidth = 220;
          const gap =
            Number.parseFloat(styles.columnGap || styles.gap || "10") || 10;
          const columns = Math.max(
            1,
            Math.floor((viewport.clientWidth + gap) / (minCardWidth + gap)),
          );
          const rows = Math.max(
            1,
            Math.floor(viewport.clientHeight / TARGET_CARD_HEIGHT),
          );
          next = columns * rows;
        }
        next = Math.min(100, Math.max(1, next));
        setPageSize((current) => (current === next ? current : next));
      });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(panel);
    measure();
    return () => {
      observer.disconnect();
      if (measureFrame.current !== null)
        cancelAnimationFrame(measureFrame.current);
    };
  }, [view, !!detail, selected.length]);
  const inspect = async (row: any) => {
    try {
      const d = await api<any>(`/api/library-management/items/${row.id}`);
      setDetail(d);
      setConfirmed(structuredClone(d));
      setTab("details");
      requestAnimationFrame(() => headingRef.current?.focus());
    } catch (e: any) {
      setError(e.message);
    }
  };
  const chooseView = (v: View) => {
    setPage(1);
    setView(v);
    localStorage.setItem("resume-engine-library-view", v);
  };
  const mutate = async (fn: () => Promise<any>) => {
    setBusy(true);
    try {
      await fn();
      await load(page);
      if (detail) await inspect(detail);
      await reloadLibrary();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const bulk = (action: string, extra: any = {}) =>
    mutate(() =>
      api("/api/library-management/bulk", {
        method: "POST",
        body: JSON.stringify({ ids: selected, action, ...extra }),
      }),
    ).then(() => setSelected([]));
  const rangeStart = data.total_items ? (page - 1) * pageSize + 1 : 0,
    rangeEnd = Math.min(page * pageSize, data.total_items);
  const pages = useMemo(
    () =>
      Array.from({ length: data.total_pages || 0 }, (_, i) => i + 1).filter(
        (n) => Math.abs(n - page) <= 2,
      ),
    [data.total_pages, page],
  );
  const entryMode =
    section !== "default-sets" &&
    (section === "profile" || (section !== "" && contentView === "entries"));
  const sectionCounts = useMemo(() => {
    if (!entryMode) return counts;
    const next: Record<string, number> = {};
    let all = 0;
    for (const [key] of SECTIONS) {
      if (!key) continue;
      const n = entriesFor(lib, key).filter((row: any) =>
        entryMatches(row, query, status),
      ).length;
      next[key] = n;
      all += n;
    }
    next.all = all;
    return next;
  }, [entryMode, counts, lib, query, status]);
  return (
    <main className="library-shell">
      <aside className="home-rail library-rail" aria-label="Primary navigation">
        <nav className="rail-nav">
          <button className="rail-link" onClick={onHome}>
            <AppIcon name="home" />
            Home
          </button>
          <button className="rail-link active" aria-current="page">
            <AppIcon name="library" />
            Library
          </button>
          <button className="rail-link" onClick={onJobs}>
            <AppIcon name="jobs" />
            Jobs
          </button>
          <button className="rail-link" onClick={onBin}>
            <AppIcon name="bin" />
            Bin
          </button>
        </nav>
      </aside>
      <section className="library-workspace">
        <header className="library-page-header">
          {sessionStorage.getItem("resume-engine-return-target") && (
            <button className="library-back" onClick={onReturnToResume}>
              ← Back to{" "}
              {JSON.parse(
                sessionStorage.getItem("resume-engine-return-target") || "{}",
              ).resumeName || "resume"}
            </button>
          )}
          <div className="library-title">
            <img src={compactLogo} alt="" />
            <div>
              <h1>Reusable Library</h1>
              <p>Manage reusable content and bullet variants</p>
            </div>
          </div>
          <label className="library-search">
            <AppIcon name="search" />
            <span className="sr-only">Search library</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search library…"
            />
          </label>
          <div className="library-add-menu">
            <button
              className="primary library-add"
              aria-haspopup="menu"
              aria-expanded={addMenuOpen}
              onClick={() => setAddMenuOpen(!addMenuOpen)}
            >
              ＋ Add New ▾
            </button>
            {addMenuOpen && (
              <div role="menu" className="library-create-menu">
                {[
                  ["Bullet", null],
                  ["Experience", "employment"],
                  ["Project", "project"],
                  ["Education", "education"],
                  ["Leadership", "leadership"],
                  ["Skill Group", "tool-group"],
                  ["Interest", "interest"],
                  ["Profile", "profile"],
                  ["Custom Section", "custom-section"],
                  ["Custom Entry", "custom-entry"],
                ].map(([label, kind]: any) => (
                  <button
                    role="menuitem"
                    key={label}
                    onClick={() => {
                      setAddMenuOpen(false);
                      if (kind) setCreateKind(kind);
                      else setCreateOpen(true);
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </header>
        {error && (
          <div className="library-error" role="alert">
            {error}
            <button onClick={() => setError("")}>Dismiss</button>
          </div>
        )}
        {selected.length > 0 && (
          <div className="bulk-bar" aria-live="polite">
            <strong>{selected.length} selected</strong>
            <button
              onClick={() =>
                bulk(status === "archived" ? "restore" : "archive")
              }
            >
              {status === "archived" ? "Restore" : "Archive"}
            </button>
            <button onClick={() => setBulkDialog("tag")}>Tag</button>
            <button onClick={() => setBulkDialog("move")}>Move Section</button>
            <button onClick={() => setBulkDialog("set")}>Defaults set</button>
            <button onClick={() => setSelected([])}>Clear</button>
          </div>
        )}
        <div className="library-layout">
          <aside className="library-sections" aria-label="Library sections">
            <h2>Library Sections</h2>
            {SECTIONS.map(([key, label, icon]) => (
              <button
                key={key}
                aria-pressed={section === key}
                onClick={() => {
                  setSection(key);
                  setPage(1);
                  setEntryDetail(null);
                  if (key === "" ) setContentView("bullets");
                  if (key === "profile") setContentView("entries");
                }}
              >
                <span>
                  <AppIcon name={icon} />
                  {label}
                </span>
                <strong>
                  {key === "default-sets"
                    ? (lib.default_sets || []).length
                    : sectionCounts[key || "all"] || 0}
                </strong>
              </button>
            ))}
            <div className="library-tip">
              <AppIcon name="tip" />
              <div>
                <strong>Tip</strong>
                <p>
                  Reusable items can be used in any resume. Archiving an item
                  keeps it in your library but hides it from selection.
                </p>
              </div>
            </div>
          </aside>
          <section
            className="library-results"
            ref={resultsRef}
            aria-label="Library results"
            aria-busy={busy}
          >
            <div className="library-result-toolbar" ref={toolbarRef}>
              {section !== "" &&
                section !== "profile" &&
                section !== "default-sets" && (
                <div
                  className="view-toggle content-toggle"
                  role="group"
                  aria-label="Content view"
                >
                  <button
                    aria-pressed={contentView === "entries"}
                    onClick={() => {
                      setContentView("entries");
                      localStorage.setItem(
                        "resume-engine-library-content-view",
                        "entries",
                      );
                    }}
                  >
                    Entries
                  </button>
                  <button
                    aria-pressed={contentView === "bullets"}
                    onClick={() => {
                      setContentView("bullets");
                      localStorage.setItem(
                        "resume-engine-library-content-view",
                        "bullets",
                      );
                    }}
                  >
                    Bullets
                  </button>
                </div>
              )}
              <div className="view-toggle">
                <button
                  aria-pressed={view === "list"}
                  onClick={() => chooseView("list")}
                >
                  <AppIcon name="list-view" />
                  List View
                </button>
                <button
                  aria-pressed={view === "card"}
                  onClick={() => chooseView("card")}
                >
                  <AppIcon name="card-view" />
                  Card View
                </button>
              </div>
              <div className="library-filters">
                <div className="view-toggle" role="group" aria-label="Status filter">
                  {(
                    [
                      ["active", "Active"],
                      ["archived", "Archived"],
                      ["all", "All"],
                    ] as const
                  ).map(([key, label]) => (
                    <button
                      type="button"
                      key={key}
                      aria-pressed={status === key}
                      onClick={() => setStatus(key)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="library-results-viewport" ref={viewportRef}>
              {section === "default-sets" ? (
                <DefaultSetResults
                  lib={lib}
                  query={query}
                  reloadLibrary={reloadLibrary}
                  setError={setError}
                />
              ) : entryMode ? (
                <EntryResults
                  lib={lib}
                  section={section}
                  query={query}
                  status={status}
                  view={view}
                  selectedId={entryDetail?.id}
                  onSelect={(x: any) => {
                    const row = hydrateEducationDraft(structuredClone(x));
                    setEntryDetail(row);
                    setEntryConfirmed(structuredClone(row));
                    setEntryTab("details");
                  }}
                />
              ) : busy && !data.items.length ? (
                <div className="library-state" role="status">
                  Loading Library…
                </div>
              ) : !data.items.length ? (
                <div className="library-state">
                  <strong>
                    {query ? "No matching records" : "No Library records"}
                  </strong>
                  <span>
                    {query
                      ? "Try another search or filter."
                      : "Use Add New to create reusable content."}
                  </span>
                </div>
              ) : view === "list" ? (
                <div className="library-table" role="table">
                  <div className="library-table-head" role="row">
                    <span></span>
                    <span>Content</span>
                    <span>Section</span>
                    <span>Parent / Context</span>
                    <span>Variants</span>
                    <span>Last Modified</span>
                  </div>
                  {data.items.map((r: any) => (
                    <div
                      role="row"
                      className={`library-table-row ${detail?.id === r.id ? "selected" : ""} ${r.archived_at ? "archived" : ""}`}
                      key={r.id}
                    >
                      <input
                        aria-label={`Select ${r.body}`}
                        type="checkbox"
                        checked={selected.includes(r.id)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, r.id]
                              : selected.filter((x) => x !== r.id),
                          )
                        }
                      />
                      <button
                        role="cell"
                        className="library-item-open"
                        onClick={() => inspect(r)}
                      >
                        <strong>{r.body || "No active wording"}</strong>
                        <span>
                          {(r.tags || [])
                            .map((t: any) => t.display_name)
                            .join(" · ")}
                        </span>
                        {r.archived_at && <em>Archived</em>}
                      </button>
                      <span
                        role="cell"
                        className={`library-section-pill ${r.section}`}
                      >
                        <AppIcon name={sectionIconName(r.section)} />
                        {sectionLabel(r.section)}
                      </span>
                      <span role="cell">{r.parent_context || "—"}</span>
                      <span role="cell">{r.variant_count}</span>
                      <span role="cell">
                        {new Date(r.updated_at).toLocaleDateString()}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="library-cards">
                  {data.items.map((r: any) => (
                    <article
                      className={`${detail?.id === r.id ? "selected" : ""} ${r.archived_at ? "archived" : ""}`}
                      key={r.id}
                    >
                      <input
                        aria-label={`Select ${r.body}`}
                        type="checkbox"
                        checked={selected.includes(r.id)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, r.id]
                              : selected.filter((x) => x !== r.id),
                          )
                        }
                      />
                      <button onClick={() => inspect(r)}>
                        <strong>{r.body || "No active wording"}</strong>
                        <span className="library-card-meta">
                          <span className={`library-section-pill ${r.section}`}>
                            <AppIcon name={sectionIconName(r.section)} />
                            {sectionLabel(r.section)}
                          </span>
                          <span className="card-variant-count">
                            {r.variant_count}{" "}
                            {r.variant_count === 1 ? "variant" : "variants"}
                          </span>
                        </span>
                        <span>{r.parent_context || "No parent context"}</span>
                        {r.archived_at && <em>Archived</em>}
                      </button>
                    </article>
                  ))}
                </div>
              )}
            </div>
            {!entryMode && section !== "default-sets" && (
              <nav
                ref={paginationRef}
                className="library-pagination"
                aria-label="Library results pages"
              >
                <span>
                  Showing {rangeStart}–{rangeEnd} of {data.total_items} items
                </span>
                <button
                  disabled={!data.has_previous}
                  onClick={() => load(page - 1)}
                >
                  Previous
                </button>
                {pages.map((n) => (
                  <button
                    key={n}
                    aria-current={n === page ? "page" : undefined}
                    onClick={() => load(n)}
                  >
                    {n}
                  </button>
                ))}
                <button
                  disabled={!data.has_next}
                  onClick={() => load(page + 1)}
                >
                  Next
                </button>
              </nav>
            )}
          </section>
          <aside className="library-details" aria-label="Library details">
            {entryMode ? (
              <EntryDetails
                lib={lib}
                section={section}
                detail={entryDetail}
                confirmed={entryConfirmed}
                tab={entryTab}
                setTab={setEntryTab}
                setDetail={setEntryDetail}
                reloadLibrary={reloadLibrary}
                onOpenResume={onOpenResume}
                onOpenBullet={(id: string) => {
                  setContentView("bullets");
                  localStorage.setItem(
                    "resume-engine-library-content-view",
                    "bullets",
                  );
                  const row = { id };
                  inspect(row);
                }}
                error={error}
                setError={setError}
              />
            ) : !detail ? (
              <div className="library-state">
                <strong>Select a Library item</strong>
                <span>Details, variants, and usage will appear here.</span>
              </div>
            ) : (
              <>
                <div className="detail-heading">
                  <h2 ref={headingRef} tabIndex={-1}>
                    <AppIcon name="details" />
                    Bullet Details
                  </h2>
                  <button
                    aria-label="Close details"
                    onClick={() => {
                      setDetail(null);
                      setConfirmed(null);
                    }}
                  >
                    ×
                  </button>
                </div>
                <div
                  className="detail-tabs"
                  role="tablist"
                  aria-label="Bullet detail views"
                >
                  {["details", "variants", "usage", "sets"].map((x) => (
                    <button
                      role="tab"
                      key={x}
                      aria-selected={tab === x}
                      onClick={() => setTab(x)}
                    >
                      {x === "sets"
                        ? "Defaults sets"
                        : x[0].toUpperCase() + x.slice(1)}
                      {x === "variants"
                        ? ` (${detail.variants.length})`
                        : x === "usage"
                          ? ` (${detail.usage.length})`
                          : ""}
                    </button>
                  ))}
                </div>
                {tab === "details" && (
                  <div className="detail-form">
                    <label>
                      Bullet Text
                      <textarea
                        value={detail.body}
                        onChange={(e) =>
                          setDetail({ ...detail, body: e.target.value })
                        }
                      />
                    </label>
                    <div className="choice-field">
                      <span>Section</span>
                      <SectionSelect
                        value={detail.section}
                        onChange={(next) =>
                          setDetail({
                            ...detail,
                            section: next,
                            parent_id: detail.parent_options?.some(
                              (x: any) =>
                                x.id === detail.parent_id && x.section === next,
                            )
                              ? detail.parent_id
                              : null,
                            parent_type: detail.parent_options?.some(
                              (x: any) =>
                                x.id === detail.parent_id && x.section === next,
                            )
                              ? detail.parent_type
                              : null,
                            parent_context:
                              detail.parent_options?.find(
                                (x: any) =>
                                  x.id === detail.parent_id &&
                                  x.section === next,
                              )?.label || "",
                          })
                        }
                      />
                    </div>
                    <div className="choice-field">
                      <span>Parent / Context</span>
                      <ChoiceList
                        label="Parent or context"
                        value={detail.parent_id || ""}
                        options={[
                          { value: "", label: "No parent" },
                          ...(detail.parent_options || [])
                            .filter((x: any) => x.section === detail.section)
                            .map((x: any) => ({
                              value: x.id,
                              label: x.label,
                            })),
                        ]}
                        onChange={(next) => {
                          const selectedParent = (
                            detail.parent_options || []
                          ).find((x: any) => x.id === next);
                          setDetail({
                            ...detail,
                            parent_id: selectedParent?.id || null,
                            parent_type: selectedParent?.type || null,
                            parent_context: selectedParent?.label || "",
                          });
                        }}
                      />
                    </div>
                    <label>
                      Tags
                      <span className="tag-chip-list" aria-label="Current tags">
                        {(detail.tags || []).map((tag: any) => (
                          <span
                            className="tag-chip"
                            key={tag.normalized_name || tag.display_name}
                          >
                            {tag.display_name}
                            <button
                              type="button"
                              aria-label={`Remove tag ${tag.display_name}`}
                              onClick={() =>
                                setDetail({
                                  ...detail,
                                  tags: detail.tags.filter(
                                    (x: any) =>
                                      (x.normalized_name ||
                                        x.display_name.toLowerCase()) !==
                                      (tag.normalized_name ||
                                        tag.display_name.toLowerCase()),
                                  ),
                                })
                              }
                            >
                              ×
                            </button>
                          </span>
                        ))}
                      </span>
                      <input
                        aria-label="Add tag"
                        placeholder="Add tag and press Enter"
                        value={detail.tagDraft || ""}
                        onChange={(e) =>
                          setDetail({ ...detail, tagDraft: e.target.value })
                        }
                        onKeyDown={(e) => {
                          if (e.key !== "Enter" && e.key !== ",") return;
                          e.preventDefault();
                          const name = (detail.tagDraft || "").trim();
                          if (
                            !name ||
                            (detail.tags || []).some(
                              (x: any) =>
                                x.display_name.toLowerCase() ===
                                name.toLowerCase(),
                            )
                          )
                            return;
                          setDetail({
                            ...detail,
                            tagDraft: "",
                            tags: [
                              ...(detail.tags || []),
                              {
                                display_name: name,
                                normalized_name: name.toLowerCase(),
                              },
                            ],
                          });
                        }}
                      />
                    </label>
                    <p>
                      Last modified{" "}
                      {new Date(detail.updated_at).toLocaleString()}
                    </p>
                    <div className="form-actions detail-actions">
                      <button
                        className="primary detail-save"
                        onClick={() =>
                          mutate(async () => {
                            const def =
                              detail.variants.find(
                                (x: any) => x.is_default && !x.archived_at,
                              ) ||
                              detail.variants.find((x: any) => !x.archived_at);
                            if (def && def.body !== detail.body)
                              await api(`/api/library/variants/${def.id}`, {
                                method: "PUT",
                                body: JSON.stringify({
                                  name: def.name,
                                  body: detail.body,
                                }),
                              });
                            await api(
                              `/api/library-management/items/${detail.id}/tags`,
                              {
                                method: "PUT",
                                body: JSON.stringify({
                                  names: detail.tags.map(
                                    (x: any) => x.display_name,
                                  ),
                                }),
                              },
                            );
                            if (detail.section !== confirmed.section)
                              await api("/api/library-management/bulk", {
                                method: "POST",
                                body: JSON.stringify({
                                  ids: [detail.id],
                                  action: "move-section",
                                  section: detail.section,
                                }),
                              });
                            if (
                              detail.parent_id !== confirmed.parent_id ||
                              detail.section !== confirmed.section
                            )
                              await api(
                                `/api/library-management/items/${detail.id}/parent`,
                                {
                                  method: "PUT",
                                  body: JSON.stringify({
                                    parent_id: detail.parent_id || null,
                                    parent_type: detail.parent_id
                                      ? "content_item"
                                      : null,
                                  }),
                                },
                              );
                          })
                        }
                      >
                        Save Changes
                      </button>
                      <button
                        className="detail-cancel"
                        onClick={() => setDetail(structuredClone(confirmed))}
                      >
                        Cancel
                      </button>
                      <button
                        className="danger-text detail-archive"
                        onClick={() =>
                          mutate(() =>
                            api("/api/library-management/bulk", {
                              method: "POST",
                              body: JSON.stringify({
                                ids: [detail.id],
                                action: detail.archived_at
                                  ? "restore"
                                  : "archive",
                                tag_names: [],
                              }),
                            }),
                          ).then(() => setDetail(null))
                        }
                      >
                        {detail.archived_at ? "Restore Item" : "Archive Item"}
                      </button>
                    </div>
                  </div>
                )}
                {tab === "variants" && (
                  <Variants detail={detail} mutate={mutate} />
                )}{" "}
                {tab === "usage" && (
                  <Usage rows={detail.usage} onOpenResume={onOpenResume} />
                )}
                {tab === "sets" && (
                  <SetMembershipEditor
                    lib={lib}
                    itemType="bullet"
                    itemId={detail.id}
                    label="Include this bullet in"
                    variants={bulletVariantOptions(detail.variants || [])}
                    reloadLibrary={reloadLibrary}
                    setError={setError}
                  />
                )}
              </>
            )}
          </aside>
        </div>
      </section>
      {bulkDialog === "set" && (
        <BulkSetDialog
          sets={lib.default_sets || []}
          count={selected.length}
          close={() => setBulkDialog(null)}
          apply={(setId: string, action: "add" | "remove") => {
            setBulkDialog(null);
            mutate(() =>
              api(`/api/default-sets/${setId}/bulk`, {
                method: "POST",
                body: JSON.stringify({ action, bullet_ids: selected }),
              }),
            );
          }}
        />
      )}
      {bulkDialog && bulkDialog !== "set" && (
        <BulkDialog
          kind={bulkDialog}
          close={() => setBulkDialog(null)}
          apply={(value: any) => {
            if (bulkDialog === "tag") bulk("add-tags", { tag_names: value });
            else bulk("move-section", { section: value });
            setBulkDialog(null);
          }}
        />
      )}
      {createKind && (
        <EntryCreateDialog
          kind={createKind}
          lib={lib}
          close={() => setCreateKind(null)}
          saved={async (row: any) => {
            await reloadLibrary();
            setSection(sectionForKind(createKind));
            setContentView("entries");
            setEntryDetail(row);
            setEntryConfirmed(structuredClone(row));
            setCreateKind(null);
          }}
          setError={setError}
        />
      )}
      {createOpen && (
        <CreateDialog
          close={() => setCreateOpen(false)}
          saved={async (id: string) => {
            setCreateOpen(false);
            await load(1);
            const row = { id };
            await inspect(row);
          }}
        />
      )}
    </main>
  );
}
function SectionSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const options = SECTIONS.slice(1).filter(([key]) => key !== "profile");
  return (
    <div className="section-choices" role="group" aria-label="Section">
      {options.map(([key, label, icon]) => (
        <button
          type="button"
          key={key}
          aria-pressed={value === key}
          onClick={() => onChange(key)}
        >
          <AppIcon name={icon} />
          {label}
        </button>
      ))}
    </div>
  );
}

function AttachBullet({ detail, mutate }: any) {
  const [target, setTarget] = useState("");
  const [options, setOptions] = useState<any[]>([]);
  useEffect(() => {
    const params = new URLSearchParams({
      section: detail.section || "",
      page: "1",
      page_size: "100",
      status: "active",
      q: "",
    });
    api<any>(`/api/library-management/items?${params}`)
      .then((row) =>
        setOptions(
          (row.items || []).filter((item: any) => item.id !== detail.id),
        ),
      )
      .catch(() => setOptions([]));
  }, [detail.id, detail.section]);
  if (!options.length) return null;
  return (
    <fieldset className="variant-create-card">
      <legend>Make this bullet a variant of another bullet</legend>
      <select
        aria-label="Target bullet"
        value={target}
        onChange={(event) => setTarget(event.target.value)}
      >
        <option value="">Choose a bullet</option>
        {options.map((item) => (
          <option key={item.id} value={item.id}>
            {(item.body || "Bullet").slice(0, 80)}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={!target}
        onClick={() =>
          mutate(() =>
            api(`/api/library/bullets/${detail.id}/attach`, {
              method: "POST",
              body: JSON.stringify({ target_bullet_id: target }),
            }),
          )
        }
      >
        Move onto that bullet
      </button>
    </fieldset>
  );
}

function Variants({ detail, mutate }: any) {
  const [name, setName] = useState("");
  const [body, setBody] = useState("");
  const [editing, setEditing] = useState<any>(null);
  return (
    <div className="variant-management variant-list">
      {detail.variants.map((v: any) => (
        <article
          key={v.id}
          className={`variant-card ${v.archived_at ? "archived" : ""}`}
        >
          <label className="variant-card-header">
            <input
              type="radio"
              checked={v.is_default}
              disabled={!!v.archived_at}
              onChange={() =>
                mutate(() =>
                  api(`/api/library/variants/${v.id}/default`, {
                    method: "POST",
                  }),
                )
              }
            />
            <strong>
              {v.name}
              {v.is_default && (
                <span className="status-badge default">Default</span>
              )}
              {v.ai_generated && (
                <span
                  className="status-badge variant-ai-badge"
                  title={[
                    v.ai_model ? `Drafted by ${v.ai_model}` : "Drafted by AI",
                    [v.ai_job_role, v.ai_job_company].filter(Boolean).join(" at "),
                  ]
                    .filter(Boolean)
                    .join(" for ")}
                >
                  AI-written
                </span>
              )}
            </strong>
          </label>
          <p className="variant-wording">{v.body}</p>
          <small className="variant-meta">
            <span
              className={`status-badge ${v.archived_at ? "archived" : "active"}`}
            >
              {v.archived_at ? "Archived" : "Active"}
            </span>{" "}
            {v.updated_at
              ? new Date(v.updated_at).toLocaleDateString()
              : ""}
          </small>
          <div className="variant-actions">
            <button onClick={() => setEditing({ ...v })}>Edit</button>
            <button
              onClick={() =>
                mutate(() =>
                  api(`/api/library/variants/${v.id}/duplicate`, {
                    method: "POST",
                  }),
                )
              }
            >
              Duplicate
            </button>
            <button
              type="button"
              disabled={!!v.archived_at}
              onClick={() =>
                mutate(() =>
                  api(`/api/library/variants/${v.id}/detach`, { method: "POST" }),
                )
              }
            >
              Make this its own bullet
            </button>
            <button
              onClick={() =>
                mutate(() =>
                  api(
                    `/api/library/variants/${v.id}/${v.archived_at ? "restore" : "archive"}`,
                    {
                      method: "POST",
                      body: v.archived_at
                        ? undefined
                        : JSON.stringify({
                            replacement_variant_id: v.is_default
                              ? detail.variants.find(
                                  (x: any) => !x.archived_at && !x.is_default,
                                )?.id
                              : null,
                          }),
                    },
                  ),
                )
              }
            >
              {v.archived_at ? "Restore" : "Archive"}
            </button>
          </div>
        </article>
      ))}
      {editing && (
        <article className="variant-card inline-variant-editor">
          <label>
            Variant name
            <input
              value={editing.name}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
            />
          </label>
          <label>
            Variant wording
            <textarea
              value={editing.body}
              onChange={(e) => setEditing({ ...editing, body: e.target.value })}
            />
          </label>
          <div className="variant-actions">
            <button onClick={() => setEditing(null)}>Cancel</button>
            <button
              className="primary"
              onClick={() =>
                mutate(() =>
                  api(`/api/library/variants/${editing.id}`, {
                    method: "PUT",
                    body: JSON.stringify({
                      name: editing.name,
                      body: editing.body,
                    }),
                  }),
                ).then(() => setEditing(null))
              }
            >
              Save
            </button>
          </div>
        </article>
      )}
      <AttachBullet detail={detail} mutate={mutate} />
      <fieldset className="variant-create-card">
        <legend>Add New Variant</legend>
        <input
          aria-label="Variant name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Variant name"
        />
        <textarea
          aria-label="Variant wording"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Wording"
        />
        <button
          disabled={!name.trim() || !body.trim()}
          onClick={() =>
            mutate(() =>
              api(`/api/library/bullets/${detail.id}/variants`, {
                method: "POST",
                body: JSON.stringify({ name, body }),
              }),
            ).then(() => {
              setName("");
              setBody("");
            })
          }
        >
          Add New Variant
        </button>
      </fieldset>
    </div>
  );
}
function Usage({ rows, onOpenResume, empty }: any) {
  return (
    <div className="usage-list">
      {!rows.length ? (
        <div className="library-state">
          <strong>
            {empty || "This bullet is not currently used in a resume"}
          </strong>
        </div>
      ) : (
        rows.map((u: any) => (
          <article className="usage-card" key={u.placement_id}>
            <div className="usage-card-main">
              <strong>{u.resume_name}</strong>
              <span className={`library-section-pill ${u.section}`}>
                <AppIcon name={sectionIconName(u.section)} />
                {sectionLabel(u.section)}
              </span>
              <span className="usage-context">
                {u.variant_name || "Missing variant"}
              </span>
            </div>
            <span className={`usage-status ${u.status.toLowerCase()}`}>
              {u.status}
            </span>
            <div className="usage-actions">
              <button
                disabled={u.status === "Missing"}
                onClick={() => onOpenResume(u.composition_id, u)}
              >
                Open usage
              </button>
            </div>
          </article>
        ))
      )}
    </div>
  );
}
function CreateDialog({ close, saved }: any) {
  const [x, setX] = useState({
    body: "",
    section: "experience",
    parent_context: "",
    variant_name: "Default",
    tags: "",
  });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const r = await api<any>("/api/library-management/items", {
        method: "POST",
        body: JSON.stringify({
          ...x,
          tags: x.tags
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
        }),
      });
      saved(r.id);
    } finally {
      setBusy(false);
    }
  };
  return (
    <ModalShell title="Add New Bullet" close={close}>
      <div className="detail-form">
        <label>
          Bullet text
          <textarea
            value={x.body}
            onChange={(e) => setX({ ...x, body: e.target.value })}
          />
        </label>
        <div className="choice-field">
          <span>Section</span>
          <SectionSelect
            value={x.section}
            onChange={(section) => setX({ ...x, section })}
          />
        </div>
        <label>
          Parent context
          <input
            value={x.parent_context}
            onChange={(e) => setX({ ...x, parent_context: e.target.value })}
          />
        </label>
        <label>
          Initial variant name
          <input
            value={x.variant_name}
            onChange={(e) => setX({ ...x, variant_name: e.target.value })}
          />
        </label>
        <label>
          Tags
          <input
            value={x.tags}
            onChange={(e) => setX({ ...x, tags: e.target.value })}
          />
        </label>
        <div className="form-actions">
          <button onClick={close}>Cancel</button>
          <button
            className="primary"
            disabled={busy || !x.body.trim()}
            onClick={submit}
          >
            Create Bullet
          </button>
        </div>
      </div>
    </ModalShell>
  );
}

function sectionForKind(kind: LibraryEntryKind) {
  return (
    {
      employment: "experience",
      project: "projects",
      education: "education",
      leadership: "leadership",
      "tool-group": "skills",
      interest: "interests",
      profile: "profile",
      "custom-section": "custom",
      "custom-entry": "custom",
    } as any
  )[kind];
}
function entryMatches(x: any, query: string, status: string) {
  return (
    (status === "all" || (status === "archived") === !!x.archived_at) &&
    JSON.stringify(x).toLowerCase().includes(query.toLowerCase())
  );
}
function entriesFor(lib: any, section: string) {
  if (section === "experience") return lib.employment || [];
  if (section === "projects") return lib.projects || [];
  if (section === "education") return lib.education || [];
  if (section === "leadership") return lib.leadership || [];
  if (section === "skills") return lib.tool_groups || [];
  if (section === "interests") return lib.interests || [];
  if (section === "profile") return lib.profiles || [];
  return lib.custom_sections || [];
}
function entryDates(x: any) {
  if (x.date_label) return x.date_label;
  if (x.display_date) return x.display_date;
  if (x.graduation_date) return x.graduation_date;
  return "";
}
function entryCells(section: string, x: any) {
  const modified = x.updated_at
    ? new Date(x.updated_at).toLocaleDateString()
    : "—";
  const degree = [x.degree_type, x.degree_major].filter(Boolean).join(" ");
  const tools = (x.items || []).map((t: any) => t.name).filter(Boolean);
  if (section === "profile")
    return [
      { label: "Profile", width: "minmax(140px, 1.3fr)", primary: x.label || "Untitled", secondary: x.name || "" },
      { label: "Email", width: "minmax(0, 1.2fr)", text: x.email || "—" },
      { label: "Phone", width: "minmax(0, 0.8fr)", text: x.phone || "—" },
      { label: "LinkedIn", width: "minmax(0, 1fr)", text: x.linkedin_label || "—" },
      { label: "Last Modified", width: "110px", text: modified },
    ];
  if (section === "experience" || section === "leadership")
    return [
      { label: "Role", width: "minmax(140px, 1.4fr)", primary: x.title || x.organization || x.name || "Untitled", secondary: x.title ? x.organization || "" : x.subtitle || "" },
      { label: "Location", width: "minmax(0, 0.8fr)", text: x.location || "—" },
      { label: "Dates", width: "minmax(0, 0.9fr)", text: entryDates(x) || "—" },
      { label: "Bullets", width: "72px", text: String(groupEntryBullets(x).length) },
      { label: "Last Modified", width: "110px", text: modified },
    ];
  if (section === "projects")
    return [
      { label: "Project", width: "minmax(140px, 1.4fr)", primary: x.name || x.title || "Untitled", secondary: x.organization || x.subtitle || "" },
      { label: "Location", width: "minmax(0, 0.8fr)", text: x.location || "—" },
      { label: "Dates", width: "minmax(0, 0.9fr)", text: entryDates(x) || "—" },
      { label: "Bullets", width: "72px", text: String(groupEntryBullets(x).length) },
      { label: "Last Modified", width: "110px", text: modified },
    ];
  if (section === "education")
    return [
      { label: "School", width: "minmax(140px, 1.3fr)", primary: x.institution || "Untitled", secondary: x.college_school || "" },
      { label: "Degree", width: "minmax(0, 1fr)", text: x.degree || degree || "—" },
      { label: "Location", width: "minmax(0, 0.8fr)", text: x.location || "—" },
      { label: "Graduation", width: "minmax(0, 0.7fr)", text: entryDates(x) || "—" },
      { label: "Last Modified", width: "110px", text: modified },
    ];
  if (section === "skills")
    return [
      { label: "Group", width: "minmax(140px, 1fr)", primary: x.name || "Untitled", secondary: "" },
      { label: "Tools", width: "minmax(0, 1.6fr)", text: tools.join(", ") || "—" },
      { label: "Tool Count", width: "88px", text: String(tools.length) },
      { label: "Last Modified", width: "110px", text: modified },
    ];
  if (section === "interests")
    return [
      { label: "Interest", width: "minmax(180px, 1fr)", primary: x.body || "Untitled", secondary: "" },
      { label: "Last Modified", width: "110px", text: modified },
    ];
  return [
    { label: "Section", width: "minmax(140px, 1.2fr)", primary: x.title || x.name || "Untitled", secondary: "" },
    { label: "Layout", width: "minmax(0, 0.7fr)", text: x.layout || "—" },
    { label: "Entries", width: "72px", text: String((x.entries || []).length) },
    { label: "Last Modified", width: "110px", text: modified },
  ];
}
function ProjectHelp({ name }: { name: string }) {
  return (
    <span className="project-help" onClick={(event) => event.stopPropagation()}>
      <SectionHelp name={name} notes={bulletCoaching} />
    </span>
  );
}
function EntryResults({
  lib,
  section,
  query,
  status,
  view,
  selectedId,
  onSelect,
}: any) {
  const rows = entriesFor(lib, section).filter((x: any) =>
    entryMatches(x, query, status),
  );
  if (!rows.length)
    return (
      <div className="library-state">
        <strong>{query ? "No matching records" : "No Library records"}</strong>
        <span>
          {query
            ? "Try another search or filter."
            : "Use Add New to create reusable content."}
        </span>
      </div>
    );
  const columns = entryCells(section, rows[0]);
  const grid = {
    "--entry-columns": columns.map((c) => c.width).join(" "),
  } as React.CSSProperties;
  if (view === "card")
    return (
      <div className="library-cards entry-cards">
        {rows.map((x: any) => {
          const cells = entryCells(section, x);
          const lead = cells[0];
          const entryHelp =
            section === "projects" || section === "leadership";
          return (
            <article
              className={`${selectedId === x.id ? "selected" : ""} ${entryHelp ? "project-entry-card" : ""}`.trim()}
              key={x.id}
              onClick={entryHelp ? () => onSelect(x) : undefined}
            >
              {entryHelp ? (
                <div className="entry-title-row">
                  <button
                    type="button"
                    className="entry-name-open"
                    onClick={() => onSelect(x)}
                  >
                    <strong>{lead.primary}</strong>
                  </button>
                  <ProjectHelp name={lead.primary} />
                </div>
              ) : null}
              <button type="button" onClick={() => onSelect(x)}>
                {entryHelp ? null : <strong>{lead.primary}</strong>}
                {lead.secondary ? <span>{lead.secondary}</span> : null}
                <span className="library-card-meta">
                  {cells.slice(1).map((cell) => (
                    <span key={cell.label}>
                      {cell.label}: {cell.text}
                    </span>
                  ))}
                </span>
                {x.archived_at && <em>Archived</em>}
              </button>
            </article>
          );
        })}
      </div>
    );
  return (
    <div className="entry-results">
      <div className="entry-table-head" style={grid}>
        {columns.map((cell) => (
          <span key={cell.label}>{cell.label}</span>
        ))}
      </div>
      {rows.map((x: any) => {
        const cells = entryCells(section, x);
        const entryHelp =
          section === "projects" || section === "leadership";
        const className = `entry-table-row ${selectedId === x.id ? "selected" : ""} ${entryHelp ? "entry-with-help" : ""}`.trim();
        const body = cells.map((cell) =>
          cell.primary != null ? (
            <span key={cell.label}>
              {entryHelp ? (
                <div className="entry-title-row">
                  <button
                    type="button"
                    className="entry-name-open"
                    onClick={() => onSelect(x)}
                  >
                    <strong>{cell.primary}</strong>
                  </button>
                  <ProjectHelp name={cell.primary} />
                </div>
              ) : (
                <strong>{cell.primary}</strong>
              )}
              <small>{cell.secondary}</small>
            </span>
          ) : (
            <span key={cell.label}>{cell.text}</span>
          ),
        );
        if (entryHelp)
          return (
            <div
              className={className}
              key={x.id}
              style={grid}
              onClick={() => onSelect(x)}
            >
              {body}
            </div>
          );
        return (
          <button
            className={className}
            key={x.id}
            style={grid}
            onClick={() => onSelect(x)}
          >
            {body}
          </button>
        );
      })}
    </div>
  );
}
function groupEntryBullets(x: any) {
  const m = new Map();
  for (const r of x.bullets || []) {
    if (!m.has(r.id))
      m.set(r.id, {
        id: r.id,
        body: r.body || "",
        is_default: r.is_default,
        variants: [],
      });
    if (r.variant_id) m.get(r.id).variants.push(r);
  }
  return [...m.values()];
}
function kindForSection(section: string): LibraryEntryKind {
  return (
    {
      experience: "employment",
      projects: "project",
      education: "education",
      leadership: "leadership",
      skills: "tool-group",
      interests: "interest",
      custom: "custom-section",
      profile: "profile",
    } as any
  )[section];
}
function recordUsage(lib: any, section: string, detail: any) {
  const compositions = lib?.compositions || [];
  const named = (id: string) =>
    compositions.find((c: any) => String(c.id) === String(id));
  const row = (composition: any, context: string) => ({
    placement_id: String(composition.id),
    composition_id: composition.id,
    resume_name: composition.name,
    section,
    variant_name: context,
    status: composition.archived_at ? "Archived" : "Current",
  });
  if (section === "profile")
    return compositions
      .filter((c: any) => String(c.profile_id || "") === String(detail.id))
      .map((c: any) => row(c, detail.label || "Header"));
  if (section === "custom")
    return (lib?.composition_custom_sections || [])
      .filter((link: any) => String(link.section_id) === String(detail.id))
      .map((link: any) => named(link.composition_id))
      .filter(Boolean)
      .map((c: any) => row(c, detail.title || "Custom section"));
  const itemSection: Record<string, string> = {
    experience: "work_experience",
    projects: "projects",
    education: "education",
    leadership: "leadership",
    skills: "tool_groups",
    interests: "personal_interests",
  };
  return (lib?.composition_items || [])
    .filter(
      (link: any) =>
        String(link.item_id) === String(detail.id) &&
        link.section === itemSection[section],
    )
    .map((link: any) => named(link.composition_id))
    .filter(Boolean)
    .map((c: any) => row(c, sectionLabel(section)));
}
function variantDetail(bullet: any, section: string) {
  return {
    id: bullet.id,
    section,
    variants: (bullet.variants || []).map((v: any) => ({
      id: v.variant_id || v.id,
      name: v.variant_name || v.name || "Variant",
      body: v.body || "",
      is_default: v.is_default,
      archived_at: v.variant_archived_at || null,
      updated_at: v.variant_updated_at || v.updated_at || bullet.updated_at,
    })),
  };
}
function fieldVariantText(kind: string, variant: any) {
  if (kind === "profile")
    return [variant.display_name, variant.email, variant.phone]
      .filter(Boolean)
      .join(" · ");
  if (kind === "education")
    return [
      variant.institution,
      variant.degree_major || variant.degree,
      variant.display_date || variant.graduation_date,
    ]
      .filter(Boolean)
      .join(" · ");
  return [variant.item_name || variant.organization, variant.title, variant.date_label]
    .filter(Boolean)
    .join(" · ");
}

function FieldVariantList({ kind, detail }: { kind: string; detail: any }) {
  const rows = (detail.field_variants || []).filter((variant: any) => !variant.archived_at);
  if (!rows.length) return null;
  return (
    <div className="variant-management variant-list">
      {rows.map((variant: any) => (
        <article className="variant-card" key={variant.id}>
          <div className="variant-card-header">
            <strong>{variant.name}</strong>
          </div>
          <p className="variant-wording">{fieldVariantText(kind, variant)}</p>
        </article>
      ))}
    </div>
  );
}

function EntryDetails({
  lib,
  section: librarySection,
  detail,
  confirmed,
  tab,
  setTab,
  setDetail,
  reloadLibrary,
  onOpenResume,
  onOpenBullet,
  setError,
}: any) {
  if (!detail)
    return (
      <div className="library-state">
        <strong>Select an entry</strong>
        <span>Details and bullets will appear here.</span>
      </div>
    );
  const section =
    librarySection ||
    ("linkedin_url" in detail && detail.label != null
      ? "profile"
      : detail.kind === "employment"
        ? "experience"
        : detail.kind === "project"
          ? "projects"
          : detail.kind === "leadership"
            ? "leadership"
            : detail.institution
              ? "education"
              : detail.items
                ? "skills"
                : detail.body
                  ? "interests"
                  : "custom");
  const kind = kindForSection(section);
  const save = async () => {
    try {
      let path = "";
      if (["employment", "project", "leadership"].includes(kind))
        path = `/api/library/items/${detail.id}`;
      else if (kind === "education")
        path = `/api/library/education/${detail.id}`;
      else if (kind === "tool-group")
        path = `/api/library/tool-groups/${detail.id}`;
      else if (kind === "interest")
        path = `/api/library/interests/${detail.id}`;
      else if (kind === "profile")
        path = `/api/library/profiles/${detail.id}`;
      else path = `/api/library/custom-sections/${detail.id}`;
      const body =
        kind === "profile" ? profilePayload(detail) : detail;
      const message = kind === "profile" ? profileWriteError(detail) : "";
      if (message) {
        setError(message);
        return;
      }
      await api(path, { method: "PUT", body: JSON.stringify(body) });
      await reloadLibrary();
    } catch (e: any) {
      setError(e.message);
    }
  };
  const lifecycle = async () => {
    const table =
      kind === "education"
        ? "education_items"
        : kind === "tool-group"
          ? "tool_groups"
          : kind === "interest"
          ? "interests"
          : kind === "profile"
            ? "profiles"
            : kind === "custom-section"
              ? "custom-sections"
              : "content_items";
    const action = detail.archived_at ? "restore" : "archive";
    if (!detail.archived_at) {
      const names = [];
      for (const c of detail.compositions || [])
        if (!c.archived_at) names.push(c.name);
      const msg = names.length
        ? `This ${kind} is used in ${names.length} resume(s). It will stay in those resumes, but it won't be offered when adding new entries.\n${names.slice(0, 5).join("\n")}${names.length > 5 ? `\nand ${names.length - 5} more` : ""}`
        : `Archive this ${kind}?`;
      if (
        !(await confirmDialog({
          title: `Archive ${kind}`,
          message: msg,
          names,
          confirmLabel: "Archive",
          danger: true,
        }))
      )
        return;
    }
    await api(`/api/library/${table}/${detail.id}/${action}`, {
      method: "POST",
    });
    await reloadLibrary();
    setDetail(null);
  };
  const bullets = groupEntryBullets(detail);
  const fieldVariants = (detail.field_variants || []).filter(
    (variant: any) => !variant.archived_at,
  );
  const usage = recordUsage(lib, section, detail);
  const refreshAfterVariant = async (fn: () => Promise<any>) => {
    try {
      await fn();
      const next = await reloadLibrary();
      const row = entriesFor(next, section).find(
        (x: any) => x.id === detail.id,
      );
      if (row) setDetail(hydrateEducationDraft(structuredClone(row)));
    } catch (e: any) {
      setError(e.message);
      throw e;
    }
  };
  const duplicateProfile = async () => {
    try {
      await api(`/api/library/profiles/${detail.id}/duplicate`, {
        method: "POST",
        body: JSON.stringify({ label: `${detail.label} Copy` }),
      });
      await reloadLibrary();
    } catch (e: any) {
      setError(e.message);
    }
  };
  return (
    <>
      <div className="detail-heading">
        <h2>{sectionLabel(section)} Details</h2>
      </div>
      <div className="detail-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "details"}
          onClick={() => setTab("details")}
        >
          Details
        </button>
        {kind !== "profile" && (
          <button
            role="tab"
            aria-selected={tab === "bullets"}
            onClick={() => setTab("bullets")}
          >
            Bullets ({bullets.length})
          </button>
        )}
        <button
          role="tab"
          aria-selected={tab === "variants"}
          onClick={() => setTab("variants")}
        >
          Variants (
            {(kind === "profile" ? Math.max(fieldVariants.length, 1) : fieldVariants.length) +
              (kind === "profile"
                ? 0
                : bullets.reduce(
                    (n: number, b: any) => n + (b.variants?.length || 0),
                    0,
                  ))}
          )
        </button>
        <button
          role="tab"
          aria-selected={tab === "usage"}
          onClick={() => setTab("usage")}
        >
          Usage ({usage.length})
        </button>
        <button
          role="tab"
          aria-selected={tab === "sets"}
          onClick={() => setTab("sets")}
        >
          Defaults sets
        </button>
      </div>
      {tab === "details" ? (
        <>
          <LibraryEntryForm kind={kind} draft={detail} setDraft={setDetail} />
          <div className="form-actions detail-actions">
            <button className="detail-archive" onClick={lifecycle}>
              {detail.archived_at ? "Restore" : "Archive"}
            </button>
            <button
              className="detail-cancel"
              onClick={() => setDetail(structuredClone(confirmed))}
            >
              Cancel
            </button>
            <button className="primary detail-save" onClick={save}>
              Save Changes
            </button>
          </div>
        </>
      ) : tab === "bullets" ? (
        <div className="entry-bullets">
          {bullets.map((b: any) => (
            <div className="bullet-row" key={b.id}>
              <span>
                {b.variants.find((v: any) => v.is_default)?.body || b.body}
              </span>
              <button onClick={() => onOpenBullet(b.id)}>Open bullet</button>
            </div>
          ))}
        </div>
      ) : tab === "variants" ? (
        kind === "profile" ? (
          <div className="variant-management variant-list">
            <FieldVariantList kind={kind} detail={detail} />
            <div className="variant-management variant-list">
            <article className="variant-card">
              <div className="variant-card-header">
                <strong>{detail.label}</strong>
              </div>
              <p className="variant-wording">
                {[detail.name, detail.email, detail.phone, detail.linkedin_label]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              <div className="variant-actions">
                <button onClick={duplicateProfile}>Duplicate</button>
              </div>
            </article>
            </div>
          </div>
        ) : (
          <div className="entry-variants">
            <FieldVariantList kind={kind} detail={detail} />
            {bullets.map((b: any) => (
              <Variants
                key={b.id}
                detail={variantDetail(b, section)}
                mutate={refreshAfterVariant}
              />
            ))}
            {!fieldVariants.length && !bullets.length && (
              <div className="library-state">
                <strong>This record has no wording variants</strong>
                <span>Bullets added to this entry will show their variants here.</span>
              </div>
            )}
          </div>
        )
      ) : tab === "sets" ? (
        <div className="entry-sets">
          <SetMembershipEditor
            lib={lib}
            itemType={setItemType(kind)}
            itemId={detail.id}
            label={`Include this ${sectionLabel(section).toLowerCase()} entry in`}
            variants={
              ["employment", "project", "leadership", "education", "profile"].includes(kind)
                ? fieldVariants.map((v: any) => ({ id: v.id, label: v.name }))
                : undefined
            }
            reloadLibrary={reloadLibrary}
            setError={setError}
          />
          {bullets.length > 0 && (
            <>
              <h3>Bullets</h3>
              <p className="set-hint">
                A bullet is used only in sets that also include this entry.
              </p>
              {bullets.map((b: any) => (
                <SetMembershipEditor
                  key={b.id}
                  lib={lib}
                  itemType="bullet"
                  itemId={b.id}
                  label={b.variants.find((v: any) => v.is_default)?.body || b.body}
                  variants={bulletVariantOptions(b.variants)}
                  reloadLibrary={reloadLibrary}
                  setError={setError}
                />
              ))}
            </>
          )}
        </div>
      ) : (
        <Usage
          rows={usage}
          onOpenResume={onOpenResume}
          empty={`This ${sectionLabel(section).toLowerCase()} is not currently used in a resume`}
        />
      )}
    </>
  );
}
function setItemType(kind: string) {
  if (["employment", "project", "leadership"].includes(kind)) return "content_item";
  if (kind === "education") return "education_item";
  if (kind === "tool-group") return "tool_group";
  if (kind === "custom-section") return "custom_section";
  return kind;
}
function EntryCreateDialog({ kind, lib, close, saved, setError }: any) {
  const [draft, setDraft] = useState(() => cloneBlankDraft(kind));
  useEffect(() => {
    if (kind === "custom-entry" && !draft.section_id)
      setDraft({
        ...draft,
        section_id:
          lib.custom_sections?.find((x: any) => !x.archived_at)?.id || "",
      });
  }, []);
  const submit = async () => {
    try {
      let path = "";
      if (["employment", "project", "leadership"].includes(kind))
        path = "/api/library/items";
      else if (kind === "education") path = "/api/library/education";
      else if (kind === "tool-group") path = "/api/library/tool-groups";
      else if (kind === "interest") path = "/api/library/interests";
      else if (kind === "profile") path = "/api/library/profiles";
      else if (kind === "custom-section") path = "/api/library/custom-sections";
      else path = "/api/library/custom-entries";
      const message = kind === "profile" ? profileWriteError(draft) : "";
      if (message) {
        setError(message);
        return;
      }
      const row = await api<any>(path, {
        method: "POST",
        body: JSON.stringify(kind === "profile" ? profilePayload(draft) : draft),
      });
      saved({ ...draft, ...row });
    } catch (e: any) {
      setError(e.message);
    }
  };
  return (
    <ModalShell title={`Add ${kind.replaceAll("-", " ")}`} close={close}>
      <LibraryEntryForm kind={kind} draft={draft} setDraft={setDraft} />
      {kind === "custom-entry" && (
        <div className="choice-field">
          <span>Custom section</span>
          <ChoiceList
            label="Custom section"
            value={draft.section_id}
            empty="Create a custom section before adding an entry."
            options={(lib.custom_sections || [])
              .filter((x: any) => !x.archived_at)
              .map((x: any) => ({ value: x.id, label: x.title }))}
            onChange={(section_id) => setDraft({ ...draft, section_id })}
          />
        </div>
      )}
      <div className="form-actions">
        <button onClick={close}>Cancel</button>
        <button
          className="primary"
          onClick={submit}
          disabled={kind === "custom-entry" && !draft.section_id}
        >
          Create Entry
        </button>
      </div>
    </ModalShell>
  );
}

function BulkDialog({ kind, close, apply }: any) {
  const [tags, setTags] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [section, setSection] = useState("experience");
  return (
    <ModalShell
      title={kind === "tag" ? "Tag selected bullets" : "Move selected bullets"}
      close={close}
    >
      {kind === "tag" ? (
        <div className="detail-form">
          <span className="tag-chip-list">
            {tags.map((x) => (
              <span className="tag-chip" key={x}>
                {x}
                <button onClick={() => setTags(tags.filter((t) => t !== x))}>
                  ×
                </button>
              </span>
            ))}
          </span>
          <input
            aria-label="Add tag"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === ",") && draft.trim()) {
                e.preventDefault();
                if (!tags.includes(draft.trim()))
                  setTags([...tags, draft.trim()]);
                setDraft("");
              }
            }}
          />
        </div>
      ) : (
        <div className="choice-field">
          <span>Section</span>
          <SectionSelect value={section} onChange={setSection} />
        </div>
      )}
      <div className="form-actions">
        <button onClick={close}>Cancel</button>
        <button
          className="primary"
          onClick={() => apply(kind === "tag" ? tags : section)}
          disabled={kind === "tag" && !tags.length}
        >
          Apply
        </button>
      </div>
    </ModalShell>
  );
}

function BulkSetDialog({ sets, count, close, apply }: any) {
  const [setId, setSetId] = useState(sets[0]?.id || "");
  return (
    <ModalShell title="Defaults set for selected bullets" close={close}>
      {sets.length ? (
        <div className="choice-field">
          <span>Defaults set</span>
          <ChoiceList
            label="Defaults set"
            value={setId}
            options={sets.map((set: any) => ({ value: set.id, label: set.name }))}
            onChange={setSetId}
          />
          <p className="set-hint">
            Added bullets use their default wording. A bullet is used only in
            sets that also include its entry.
          </p>
        </div>
      ) : (
        <p>Create a defaults set first, under Defaults sets in this Library.</p>
      )}
      <div className="form-actions">
        <button onClick={close}>Cancel</button>
        <button disabled={!setId} onClick={() => apply(setId, "remove")}>
          Remove {count} from set
        </button>
        <button className="primary" disabled={!setId} onClick={() => apply(setId, "add")}>
          Add {count} to set
        </button>
      </div>
    </ModalShell>
  );
}

import React, { useCallback, useEffect, useRef, useState } from "react";
import FitIndicator, { Fit } from "./FitIndicator";
import ResumePreview from "./ResumePreview";
import { api } from "./api";
import { RESUME_ENGINE_BUILD, RESUME_ENGINE_VERSION } from "./app-version";
import { EditorHistory } from "./EditorHistory";
import StandaloneLibrary from "./StandaloneLibrary";
import { AppIcon } from "./AppIcon";
import ModalShell from "./ModalShell";
import OverflowMenu from "./OverflowMenu";
import RevisionHistoryPanel from "./RevisionHistoryPanel";
import { confirmDialog } from "./ConfirmDialog";
import { RenameResumeDialog, EditDetailsDialog } from "./HomeDialogs";
import MonthYearField from "./MonthYearField";

import primaryLogo from "./assets/logo-primary-480.png";
import compactLogo from "./assets/logo-compact.png";
import favicon from "./assets/favicon-256.png";

type Comp = {
  id: string;
  name: string;
  description: string;
  display_title: string;
  target_company: string;
  target_role: string;
  preferred_page_length: number;
  date_format: "year" | "numeric" | "short" | "long";
  section_sort_modes: Record<string, "automatic" | "manual">;
  summary_variant_id?: string | null;
  revision: number;
  archived_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  autosaved_at?: string | null;
  resume: any;
};
type EditorKind =
  | "profile"
  | "summary"
  | "education"
  | "interest"
  | "tool-group"
  | "tool"
  | "project"
  | "employment"
  | "leadership"
  | "bullet"
  | "variant"
  | "custom-section"
  | "custom-entry"
  | null;
export default function App() {
  const [lib, setLib] = useState<any>(null);
  const [screen, setScreen] = useState<"home" | "editor" | "library">(() =>
    location.hash === "#library" ? "library" : "home",
  );
  const [homeSection, setHomeSection] = useState<"active" | "bin">("active");
  const [homeQuery, setHomeQuery] = useState("");
  const [homeView, setHomeView] = useState<"list" | "card">(() =>
    localStorage.getItem("resume-engine-home-view") === "card"
      ? "card"
      : "list",
  );
  const [comp, setComp] = useState<Comp | null>(null);
  const [toolbarRenameOpen, setToolbarRenameOpen] = useState(false);
  const [toolbarName, setToolbarName] = useState("");
  const [fit, setFit] = useState<Fit | null>(null);
  const [status, setStatus] = useState("Loading…");
  const [error, setError] = useState("");
  const [previewRevision, setPreviewRevision] = useState<any>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [homeDialog, setHomeDialog] = useState<any>(null);
  const [duplicateOpen, setDuplicateOpen] = useState(false);
  const [editorPercent, setEditorPercent] = useState(() => {
    const stored = Number(localStorage.getItem("resume-engine-editor-percent"));
    return stored >= 35 && stored <= 80 ? stored : 65;
  });
  const [editorCollapsed, setEditorCollapsed] = useState(
    () => localStorage.getItem("resume-engine-editor-collapsed") === "true",
  );
  const [previewCollapsed, setPreviewCollapsed] = useState(
    () => localStorage.getItem("resume-engine-preview-collapsed") === "true",
  );
  const [mobileWorkspace, setMobileWorkspace] = useState<"editor" | "preview">(
    () =>
      localStorage.getItem("resume-engine-mobile-workspace") === "preview"
        ? "preview"
        : "editor",
  );
  const [collapsedSections, setCollapsedSections] = useState<string[]>(() => {
    try {
      return JSON.parse(
        localStorage.getItem("resume-engine-collapsed-sections") || "[]",
      );
    } catch {
      return [];
    }
  });
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(() => {
    const stored = Number(localStorage.getItem("resume-engine-preview-zoom"));
    return stored >= 50 && stored <= 150 ? stored : 100;
  });
  const splitterDragging = useRef(false);
  const compRef = useRef<Comp | null>(null);
  const historyRef = useRef(new EditorHistory());
  const sessionId = useRef(crypto.randomUUID());
  const [, refreshHistory] = useState(0);
  const timer = useRef<any>();
  useEffect(() => {
    compRef.current = comp;
    if (comp && !toolbarRenameOpen) setToolbarName(comp.name);
  }, [comp, toolbarRenameOpen]);
  useEffect(
    () => historyRef.current.subscribe(() => refreshHistory((x) => x + 1)),
    [],
  );
  useEffect(() => {
    if (comp) historyRef.current.begin(comp.id, sessionId.current);
  }, [comp?.id]);

  const loadLibrary = async () => {
    let next = await api<any>("/api/library");
    if (!next.compositions.length) {
      await api("/api/library/import-seed", {
        method: "POST",
        body: JSON.stringify({ seed_key: "jonah-resume-v1" }),
      });
      next = await api<any>("/api/library");
    }
    setLib(next);
    return next;
  };
  const loadComposition = async (id: string) => {
    const selected = lib?.compositions?.find?.((x: any) => x.id === id);
    const next = await api<Comp>(
      `/api/compositions/${id}${selected?.archived_at ? "?include_archived=true" : ""}`,
    );
    setComp(next);
    historyRef.current.begin(next.id, sessionId.current);
    setFit(null);
    return next;
  };
  const load = async () => {
    try {
      await loadLibrary();
      setStatus("Saved");
    } catch (e: any) {
      setError(e.message);
    }
  };
  useEffect(() => {
    const route = () => {
      if (location.hash === "#library") setScreen("library");
    };
    addEventListener("hashchange", route);
    return () => removeEventListener("hashchange", route);
  }, []);
  useEffect(() => {
    load();
    let icon = document.querySelector<HTMLLinkElement>("link[rel='icon']");
    if (!icon) {
      icon = document.createElement("link");
      icon.rel = "icon";
      document.head.appendChild(icon);
    }
    icon.href = favicon;
  }, []);

  const changed = (resume: any) => {
    if (!comp) return;
    setComp({ ...comp, resume });
    setFit(null);
    setStatus("Unsaved changes");
    clearTimeout(timer.current);
    const revision = comp.revision,
      id = comp.id;
    timer.current = setTimeout(async () => {
      try {
        setStatus("Saving…");
        setComp(
          await api<Comp>(`/api/compositions/${id}`, {
            method: "PUT",
            body: JSON.stringify({ revision, resume, source: "autosave" }),
          }),
        );
        setStatus("Saved");
      } catch (e: any) {
        setStatus(e.status === 409 ? "Conflict" : "Save failed");
        setError(e.message);
      }
    }, 700);
  };
  const chooseSummary = async (summary_variant_id: string) => {
    if (!comp) return;
    setStatus("Saving…");
    try {
      setComp(
        await api<Comp>(`/api/compositions/${comp.id}/summary`, {
          method: "PUT",
          body: JSON.stringify({
            revision: comp.revision,
            summary_variant_id: summary_variant_id || null,
          }),
        }),
      );
      setStatus("Saved");
    } catch (e: any) {
      setStatus(e.status === 409 ? "Conflict" : "Save failed");
      setError(e.message);
    }
  };
  const chooseInterest = async (item: any, included: boolean) => {
    if (!comp) return;
    setStatus("Saving…");
    try {
      setComp(
        await api<Comp>(`/api/compositions/${comp.id}/interests`, {
          method: "PUT",
          body: JSON.stringify({
            revision: comp.revision,
            interest_id: item.id,
            included,
          }),
        }),
      );
      setStatus("Saved");
    } catch (e: any) {
      setStatus(e.status === 409 ? "Conflict" : "Save failed");
      setError(e.message);
    }
  };
  const chooseLibraryItem = async (
    section: string,
    item: any,
    included: boolean,
  ) => {
    if (!comp) return;
    setStatus("Saving…");
    const endpoint =
      section === "tool_groups"
        ? "tool-groups"
        : section === "education"
          ? "education"
          : `historical/${section}`;
    try {
      setComp(
        await api<Comp>(`/api/compositions/${comp.id}/${endpoint}`, {
          method: "PUT",
          body: JSON.stringify({
            revision: comp.revision,
            item_id: item.id,
            included,
          }),
        }),
      );
      setStatus("Saved");
    } catch (e: any) {
      setStatus(e.status === 409 ? "Conflict" : "Save failed");
      setError(e.message);
    }
  };
  const included = (section: string, item: any) => {
    const rendered = comp?.resume?.[section] || [];
    if (section === "tool_groups")
      return rendered.some((x: any) => x.name === item.name);
    if (section === "projects")
      return rendered.some((x: any) => x.name === item.name);
    return rendered.some(
      (x: any) =>
        x.organization === item.organization && x.title === item.title,
    );
  };
  const createBlankComposition = async () => {
    try {
      const next = await api<Comp>("/api/compositions", {
        method: "POST",
        body: JSON.stringify({}),
      });
      setComp(next);
      await loadLibrary();
      setPreviewRevision(null);
      setScreen("editor");
    } catch (e: any) {
      setError(e.message);
    }
  };
  const runHistoryAction = async (direction: "undo" | "redo") => {
    try {
      await historyRef.current[direction]();
      setStatus("Saved");
    } catch (e: any) {
      setStatus(e?.status === 409 ? "Conflict" : "Save failed");
      setError(
        e?.message ||
          `${direction} failed. Retry when synchronization is available.`,
      );
    }
  };
  const recordMetadataCommand = (
    before: any,
    after: any,
    preRevision: number,
  ) => {
    if (!compRef.current) return;
    const apply = async (value: any) => {
      const current = compRef.current!;
      const next = await api<Comp>(`/api/compositions/${current.id}/metadata`, {
        method: "PUT",
        body: JSON.stringify({ revision: current.revision, ...value }),
      });
      compRef.current = next;
      setComp(next);
      await loadLibrary();
    };
    historyRef.current.record({
      id: crypto.randomUUID(),
      label: "Resume details",
      compositionId: compRef.current.id,
      sessionId: sessionId.current,
      preRevision,
      identity: { compositionId: compRef.current.id, fieldGroup: "metadata" },
      undo: () => apply(before),
      redo: () => apply(after),
    });
  };
  const recordPreferenceCommand = (
    before: any,
    after: any,
    preRevision: number,
  ) => {
    if (!compRef.current) return;
    const apply = async (value: any) => {
      const current = compRef.current!;
      const next = await api<Comp>(
        `/api/compositions/${current.id}/preferences`,
        {
          method: "PUT",
          body: JSON.stringify({ revision: current.revision, ...value }),
        },
      );
      compRef.current = next;
      setComp(next);
    };
    historyRef.current.record({
      id: crypto.randomUUID(),
      label: "Resume preferences",
      compositionId: compRef.current.id,
      sessionId: sessionId.current,
      preRevision,
      identity: {
        compositionId: compRef.current.id,
        fieldGroup: "preferences",
      },
      undo: () => apply(before),
      redo: () => apply(after),
    });
  };
  const saveCompositionPreferences = async (preferences: any) => {
    if (!comp || comp.archived_at) return;
    if (
      preferences.preferred_page_length > 1 &&
      preferences.preferred_page_length !== comp.preferred_page_length &&
      !(await confirmDialog({
        title: "Use more than one page?",
        message:
          "Leading recruiters recommend keeping your resume to one page for anyone with under 20 years of work experience.",
        confirmLabel: "Use more pages",
      }))
    )
      return;
    const beforePreferences = {
      preferred_page_length: comp.preferred_page_length,
      date_format: comp.date_format,
      section_sort_modes: comp.section_sort_modes,
    };
    const preRevision = comp.revision;
    try {
      setStatus("Saving…");
      const savedPreferences = await api<Comp>(
        `/api/compositions/${comp.id}/preferences`,
        {
          method: "PUT",
          body: JSON.stringify({ revision: comp.revision, ...preferences }),
        },
      );
      setComp(savedPreferences);
      compRef.current = savedPreferences;
      recordPreferenceCommand(beforePreferences, preferences, preRevision);
      setStatus("Saved");
    } catch (e: any) {
      setStatus(e.status === 409 ? "Conflict" : "Save failed");
      setError(e.message);
    }
  };
  const saveCompositionMetadata = async (metadata: {
    name: string;
    description: string;
    display_title: string;
    target_company: string;
    target_role: string;
  }) => {
    if (!comp || comp.archived_at) return;
    const name = metadata.name.trim();
    if (!name) {
      setError("Internal name is required.");
      return;
    }
    const beforeMetadata = {
      name: comp.name,
      description: comp.description || "",
      display_title: comp.display_title || "",
      target_company: comp.target_company || "",
      target_role: comp.target_role || "",
    };
    const nextMetadata = { ...metadata, name };
    const preRevision = comp.revision;
    try {
      setStatus("Saving…");
      const savedMetadata = await api<Comp>(
        `/api/compositions/${comp.id}/metadata`,
        {
          method: "PUT",
          body: JSON.stringify({ revision: comp.revision, ...nextMetadata }),
        },
      );
      setComp(savedMetadata);
      compRef.current = savedMetadata;
      recordMetadataCommand(beforeMetadata, nextMetadata, preRevision);
      await loadLibrary();
      setStatus("Saved");
    } catch (e: any) {
      setStatus(e.status === 409 ? "Conflict" : "Save failed");
      setError(e.message);
    }
  };
  const lifecycleComposition = async (archiveIt: boolean) => {
    if (!comp) return;
    try {
      const next = await api<Comp>(
        `/api/compositions/${comp.id}/${archiveIt ? "archive" : "restore"}`,
        { method: "POST", body: JSON.stringify({ revision: comp.revision }) },
      );
      setComp(next);
      await loadLibrary();
      setStatus("Saved");
    } catch (e: any) {
      setStatus(e.status === 409 ? "Conflict" : "Save failed");
      setError(e.message);
    }
  };
  const reloadLatest = async () => {
    if (!comp) return;
    await loadComposition(comp.id);
    setStatus("Saved");
    setError("");
    setPreviewRevision(null);
  };
  const duplicate = async (
    name: string,
    setDialogError?: (value: string) => void,
  ) => {
    try {
      await api<Comp>(`/api/compositions/${comp!.id}/duplicate`, {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      });
      await loadLibrary();
      setDuplicateOpen(false);
      setAnnouncement(`Duplicated as '${name.trim()}'. Find it on Home.`);
    } catch (e: any) {
      (setDialogError || setError)(e.message);
    }
  };
  const openComposition = async (id: string) => {
    try {
      await loadComposition(id);
      setPreviewRevision(null);
      setScreen("editor");
      setStatus("Saved");
    } catch (e: any) {
      setError(e.message);
    }
  };
  const saveHomeMetadata = async (
    item: any,
    setDialogError: (value: string) => void,
  ) => {
    try {
      await api(`/api/compositions/${item.id}/metadata`, {
        method: "PUT",
        body: JSON.stringify({
          revision: item.revision,
          name: item.name.trim(),
          description: item.description || "",
          display_title: item.display_title || "",
          target_company: item.target_company || "",
          target_role: item.target_role || "",
        }),
      });
      setHomeDialog(null);
      await loadLibrary();
    } catch (e: any) {
      setDialogError(e.message);
    }
  };
  const setArchivedFromHome = async (item: any, archived: boolean) => {
    const action = archived
      ? "move this resume to the Bin"
      : "restore this resume";
    if (
      !(await confirmDialog({
        title: archived ? "Move to Bin" : "Restore resume",
        message: archived
          ? "Move this resume to the Bin? You can restore it from the Bin."
          : "Restore this resume?",
        confirmLabel: archived ? "Move to Bin" : "Restore",
        danger: archived,
      }))
    )
      return;
    try {
      await api(
        `/api/compositions/${item.id}/${archived ? "archive" : "restore"}`,
        {
          method: "POST",
          body: JSON.stringify({ revision: item.revision }),
        },
      );
      await loadLibrary();
    } catch (e: any) {
      setError(e.message);
    }
  };
  const changeHomeView = (view: "list" | "card") => {
    setHomeView(view);
    localStorage.setItem("resume-engine-home-view", view);
  };
  useEffect(() => {
    localStorage.setItem("resume-engine-editor-percent", String(editorPercent));
  }, [editorPercent]);
  useEffect(() => {
    localStorage.setItem(
      "resume-engine-editor-collapsed",
      String(editorCollapsed),
    );
  }, [editorCollapsed]);
  useEffect(() => {
    localStorage.setItem(
      "resume-engine-preview-collapsed",
      String(previewCollapsed),
    );
  }, [previewCollapsed]);
  useEffect(() => {
    localStorage.setItem("resume-engine-mobile-workspace", mobileWorkspace);
  }, [mobileWorkspace]);
  useEffect(() => {
    localStorage.setItem("resume-engine-preview-zoom", String(zoom));
  }, [zoom]);
  useEffect(() => {
    localStorage.setItem(
      "resume-engine-collapsed-sections",
      JSON.stringify(collapsedSections),
    );
  }, [collapsedSections]);
  useEffect(() => {
    const moveSplitter = (event: PointerEvent) => {
      if (!splitterDragging.current) return;
      const percent = Math.round((event.clientX / window.innerWidth) * 100);
      setEditorPercent(Math.min(80, Math.max(35, percent)));
    };
    const stopSplitter = () => {
      splitterDragging.current = false;
    };
    window.addEventListener("pointermove", moveSplitter);
    window.addEventListener("pointerup", stopSplitter);
    return () => {
      window.removeEventListener("pointermove", moveSplitter);
      window.removeEventListener("pointerup", stopSplitter);
    };
  }, []);

  const saveNow = async () => {
    if (!comp || comp.archived_at || status === "Saving…") return;
    clearTimeout(timer.current);
    try {
      setStatus("Saving…");
      setComp(
        await api<Comp>(`/api/compositions/${comp.id}`, {
          method: "PUT",
          body: JSON.stringify({
            revision: comp.revision,
            resume: comp.resume,
            source: "manual",
          }),
        }),
      );
      setStatus("Saved");
    } catch (e: any) {
      setStatus(e.status === 409 ? "Conflict" : "Save failed");
      setError(e.message);
    }
  };
  const exportPdf = async () => {
    if (!comp || !fit?.fits) return;
    const r = await fetch(
      `/api/compositions/${comp.id}/export/pdf?revision=${comp.revision}`,
      { method: "POST" },
    );
    if (!r.ok) {
      setError((await r.json().catch(() => ({}))).detail || "Export failed");
      return;
    }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await r.blob());
    const disposition = r.headers.get("Content-Disposition") || "";
    a.download =
      disposition.match(/filename="?([^";]+)"?/i)?.[1] || "resume.pdf";
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const toggleFullscreen = async () => {
    const element = document.querySelector<HTMLElement>(".preview-workspace");
    if (!element) return;
    if (document.fullscreenElement) await document.exitFullscreen();
    else await element.requestFullscreen();
  };
  const onFit = useCallback((x: Fit) => {
    setFit(x);
    setCurrentPage((page) =>
      Math.min(Math.max(1, page), x.actualPageCount || 1),
    );
  }, []);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest('[role="dialog"], [data-assistive-editor="true"]'))
        return;
      if (target?.matches('input, textarea, [contenteditable="true"]')) return;
      if (
        !(event.ctrlKey || event.metaKey) ||
        event.altKey ||
        event.key.toLowerCase() !== "z"
      )
        return;
      if (status === "Conflict") return;
      event.preventDefault();
      runHistoryAction(event.shiftKey ? "redo" : "undo");
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [status]);
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (
        ["Unsaved changes", "Saving…", "Conflict", "Save failed"].includes(
          status,
        )
      ) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [status]);

  const openLibraryFromEditor = (
    sectionKey: string,
    entryId?: string,
    createKind?: string,
  ) => {
    if (!comp) return;
    sessionStorage.setItem(
      "resume-engine-return-target",
      JSON.stringify({
        compositionId: comp.id,
        resumeName: comp.name,
        sectionKey,
        entryId: entryId || null,
        scrollTop:
          document.querySelector<HTMLElement>(".editing-shell .editor")
            ?.scrollTop || 0,
        collapsedSections,
        expandedEntries: JSON.parse(
          localStorage.getItem("resume-engine-entry-expansion") || "{}",
        ),
      }),
    );
    sessionStorage.setItem(
      "resume-engine-library-target",
      JSON.stringify({
        sectionKey,
        entryId: entryId || null,
        contentView: "entries",
        createKind: createKind || null,
      }),
    );
    history.pushState({ resumeEngineLibrary: true }, "", "#library");
    setScreen("library");
  };
  const returnFromLibrary = async () => {
    const raw = sessionStorage.getItem("resume-engine-return-target");
    if (!raw) return;
    const target = JSON.parse(raw);
    const item = lib?.compositions?.find(
      (x: any) => x.id === target.compositionId,
    );
    sessionStorage.removeItem("resume-engine-return-target");
    sessionStorage.removeItem("resume-engine-library-target");
    if (!item || item.archived_at) {
      setError("That resume is in the Bin, so the return target was cleared.");
      setScreen("home");
      return;
    }
    await loadLibrary();
    await openComposition(target.compositionId);
    setCollapsedSections(target.collapsedSections || []);
    localStorage.setItem(
      "resume-engine-entry-expansion",
      JSON.stringify(target.expandedEntries || {}),
    );
    requestAnimationFrame(() => {
      const el = document.querySelector<HTMLElement>(".editing-shell .editor");
      if (el) el.scrollTop = target.scrollTop || 0;
      document
        .querySelector(`[data-section-key="${target.sectionKey}"]`)
        ?.scrollIntoView({ block: "center" });
    });
  };
  if (!lib) return <main className="loading">{error || "Loading…"}</main>;
  if (screen === "library")
    return (
      <StandaloneLibrary
        lib={lib}
        reloadLibrary={loadLibrary}
        onHome={() => {
          sessionStorage.removeItem("resume-engine-return-target");
          sessionStorage.removeItem("resume-engine-library-target");
          history.pushState(null, "", location.pathname);
          setHomeSection("active");
          setScreen("home");
        }}
        onBin={() => {
          sessionStorage.removeItem("resume-engine-return-target");
          sessionStorage.removeItem("resume-engine-library-target");
          history.pushState(null, "", location.pathname);
          setHomeSection("bin");
          setScreen("home");
        }}
        onReturnToResume={returnFromLibrary}
        onOpenResume={async (id: string, usage?: any) => {
          if (usage)
            sessionStorage.setItem(
              "resume-engine-usage-target",
              JSON.stringify(usage),
            );
          await openComposition(id);
        }}
      />
    );
  if (screen === "home")
    return (
      <HomeScreen
        lib={lib}
        error={error}
        dismissError={() => setError("")}
        section={homeSection}
        setSection={setHomeSection}
        query={homeQuery}
        setQuery={setHomeQuery}
        view={homeView}
        setView={changeHomeView}
        createResume={createBlankComposition}
        openResume={openComposition}
        renameResume={(item: any) => setHomeDialog({ type: "rename", item })}
        editDetails={(item: any) => setHomeDialog({ type: "details", item })}
        setArchived={setArchivedFromHome}
        openLibrary={() => {
          location.hash = "library";
          setScreen("library");
        }}
      />
    );
  if (!comp) {
    setScreen("home");
    return null;
  }
  const activeSummaries = lib.summary_variants.filter(
    (x: any) => !x.archived_at,
  );
  return (
    <main className="editing-shell">
      <header className="editing-topbar">
        <div className="editing-brand">
          <img src={compactLogo} alt="" />
          <span>
            Resume <strong>Engine</strong>
          </span>
        </div>
        <div className="editing-document-name">
          {toolbarRenameOpen ? (
            <form
              className="toolbar-rename-form"
              onSubmit={async (event) => {
                event.preventDefault();
                const name = toolbarName.trim();
                if (!name || name === comp.name) {
                  setToolbarName(comp.name);
                  setToolbarRenameOpen(false);
                  return;
                }
                await saveCompositionMetadata({
                  name,
                  description: comp.description || "",
                  display_title: comp.display_title || "",
                  target_company: comp.target_company || "",
                  target_role: comp.target_role || "",
                });
                setToolbarRenameOpen(false);
              }}
            >
              <label className="sr-only" htmlFor="toolbar-resume-name">
                Resume name
              </label>
              <input
                id="toolbar-resume-name"
                value={toolbarName}
                maxLength={120}
                autoFocus
                onChange={(event) => setToolbarName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    setToolbarName(comp.name);
                    setToolbarRenameOpen(false);
                  }
                }}
              />
              <button type="submit" aria-label="Save resume name">
                Save
              </button>
              <button
                type="button"
                aria-label="Cancel resume rename"
                onClick={() => {
                  setToolbarName(comp.name);
                  setToolbarRenameOpen(false);
                }}
              >
                Cancel
              </button>
            </form>
          ) : (
            <button
              className="toolbar-rename-trigger"
              title="Rename resume"
              aria-label={`Rename ${comp.name}`}
              onClick={() => {
                setToolbarName(comp.name);
                setToolbarRenameOpen(true);
              }}
            >
              <span>{comp.name}</span>
              <span aria-hidden="true">✎</span>
            </button>
          )}
        </div>
        <div className="editing-actions">
          <span
            className={`topbar-status ${status.toLowerCase().replaceAll(" ", "-")}`}
            aria-live="polite"
          >
            {status}
          </span>
          <button onClick={() => setScreen("home")}>
            <AppIcon name="home" />
            <span className="action-label">Home</span>
          </button>
          <button
            onClick={() => {
              location.hash = "library";
              setScreen("library");
            }}
          >
            <AppIcon name="library" />
            <span className="action-label">Library</span>
          </button>
          <button
            onClick={() => runHistoryAction("undo")}
            disabled={
              !historyRef.current.snapshot.canUndo || status === "Conflict"
            }
            aria-busy={historyRef.current.snapshot.busy}
            aria-keyshortcuts="Control+Z Meta+Z"
            title="Undo last committed editor command"
          >
            <span aria-hidden="true">↶</span>
            <span className="action-label">Undo</span>
          </button>
          <button
            onClick={() => runHistoryAction("redo")}
            disabled={
              !historyRef.current.snapshot.canRedo || status === "Conflict"
            }
            aria-busy={historyRef.current.snapshot.busy}
            aria-keyshortcuts="Control+Shift+Z Meta+Shift+Z Control+Y"
            title="Redo last undone editor command"
          >
            <span aria-hidden="true">↷</span>
            <span className="action-label">Redo</span>
          </button>
          <OverflowMenu
            label="More actions"
            items={[
              { label: "Duplicate…", onSelect: () => setDuplicateOpen(true) },
              {
                label: "Revision History…",
                onSelect: () => setHistoryOpen(true),
              },
            ]}
          />
          <button
            className="export-action"
            disabled={!fit?.fits || !!previewRevision}
            onClick={exportPdf}
          >
            <span aria-hidden="true">⇩</span>
            <span className="action-label">Export PDF</span>
          </button>
        </div>
      </header>
      <div
        className="mobile-workspace-toggle"
        role="group"
        aria-label="Workspace"
      >
        <button
          aria-pressed={mobileWorkspace === "editor"}
          onClick={() => setMobileWorkspace("editor")}
        >
          Editor
        </button>
        <button
          aria-pressed={mobileWorkspace === "preview"}
          onClick={() => setMobileWorkspace("preview")}
        >
          Live View
        </button>
      </div>
      <div
        className={`workspace mobile-${mobileWorkspace}`}
        style={{
          gridTemplateColumns: editorCollapsed
            ? "0 0 1fr"
            : previewCollapsed
              ? "1fr 0 0"
              : `${editorPercent}fr 14px ${100 - editorPercent}fr`,
        }}
      >
        {editorCollapsed ? (
          <button
            className="restore-pane restore-editor"
            onClick={() => setEditorCollapsed(false)}
          >
            Show editor
          </button>
        ) : (
          <aside className="editor" aria-label="Resume editor">
            <h1 className="sr-only">Edit Resume</h1>
            <span className="version-marker sr-only">
              {RESUME_ENGINE_VERSION} Build {RESUME_ENGINE_BUILD}
            </span>
            {error && (
              <div role="alert" className="error">
                {error}
                <button onClick={() => setError("")}>Dismiss</button>
              </div>
            )}
            <>
              <ResumeDetails
                comp={comp}
                save={saveCompositionMetadata}
                savePreferences={saveCompositionPreferences}
                status={status}
              />
              <div
                className={`save-status ${status.toLowerCase().replaceAll(" ", "-")}`}
              >
                {status}
              </div>
              {status === "Conflict" && (
                <div className="conflict-recovery" role="alert">
                  Unsaved local changes were not written.{" "}
                  <button onClick={reloadLatest}>
                    Reload latest composition
                  </button>
                </div>
              )}
              <SectionsPanel
                comp={comp}
                lib={lib}
                setComp={setComp}
                setStatus={setStatus}
                setError={setError}
                collapsed={collapsedSections}
                setCollapsed={setCollapsedSections}
                saveCompositionPreferences={saveCompositionPreferences}
                chooseSummary={chooseSummary}
                chooseInterest={chooseInterest}
                chooseLibraryItem={chooseLibraryItem}
                included={included}
                openLibraryFromEditor={openLibraryFromEditor}
              />
            </>
          </aside>
        )}
        {!editorCollapsed && !previewCollapsed && (
          <div
            className="workspace-splitter"
            role="separator"
            aria-label="Resize editor and preview panes"
            aria-orientation="vertical"
            aria-valuemin={35}
            aria-valuemax={80}
            aria-valuenow={editorPercent}
            tabIndex={0}
            onPointerDown={(event) => {
              splitterDragging.current = true;
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
                event.preventDefault();
                setEditorPercent((value) =>
                  Math.min(
                    80,
                    Math.max(35, value + (event.key === "ArrowRight" ? 2 : -2)),
                  ),
                );
              }
            }}
          >
            <button
              aria-label="Collapse editor pane"
              onClick={() => setEditorCollapsed(true)}
            >
              ‹
            </button>
            <span aria-hidden="true">⋮</span>
            <button
              aria-label="Collapse preview pane"
              onClick={() => setPreviewCollapsed(true)}
            >
              ›
            </button>
          </div>
        )}
        {previewCollapsed ? (
          <button
            className="restore-pane restore-preview"
            onClick={() => setPreviewCollapsed(false)}
          >
            Show preview
          </button>
        ) : (
          <section
            className="stage preview-workspace"
            aria-label="Live resume preview"
          >
            <div className="preview-toolbar">
              <button
                aria-label="Previous Page"
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              >
                ‹
              </button>
              <output aria-label="Current page and total pages">
                Page {currentPage} / {fit?.actualPageCount || 1}
              </output>
              <button
                aria-label="Next Page"
                disabled={currentPage >= (fit?.actualPageCount || 1)}
                onClick={() =>
                  setCurrentPage((p) =>
                    Math.min(fit?.actualPageCount || 1, p + 1),
                  )
                }
              >
                ›
              </button>
              <span className="preview-toolbar-spacer" />
              <FitIndicator fit={fit} compact />
              <span className="preview-toolbar-spacer" />
              <button
                onClick={() => setZoom((value) => Math.max(50, value - 10))}
                aria-label="Zoom out"
              >
                −
              </button>
              <output aria-label="Preview zoom">{zoom}%</output>
              <button
                onClick={() => setZoom((value) => Math.min(150, value + 10))}
                aria-label="Zoom in"
              >
                +
              </button>
              <button onClick={toggleFullscreen} aria-label="Expand preview">
                ⛶
              </button>
            </div>
            <div
              className="preview-canvas"
              style={{ "--preview-zoom": zoom / 100 } as React.CSSProperties}
            >
              {previewRevision && (
                <div className="revision-banner">
                  Previewing revision {previewRevision.revision} (read-only){" "}
                  <button onClick={() => setPreviewRevision(null)}>
                    Return to current
                  </button>
                </div>
              )}
              <ResumePreview
                compositionId={comp.id}
                revision={comp.revision}
                preferredPageCount={comp.preferred_page_length || 1}
                revisionId={previewRevision?.id || null}
                currentPage={currentPage}
                onFit={onFit}
              />
            </div>
          </section>
        )}
      </div>
      {historyOpen && (
        <RevisionHistoryPanel
          comp={comp}
          close={() => {
            setHistoryOpen(false);
            setPreviewRevision(null);
          }}
          preview={setPreviewRevision}
          restore={async (row: any, setPanelError: any) => {
            try {
              const next = await api<Comp>(
                `/api/compositions/${comp.id}/revisions/${row.id}/restore`,
                {
                  method: "POST",
                  body: JSON.stringify({ revision: comp.revision }),
                },
              );
              setComp(next);
              setHistoryOpen(false);
              setPreviewRevision(null);
              await loadLibrary();
            } catch (e: any) {
              setPanelError(e.message);
            }
          }}
        />
      )}
      {duplicateOpen && (
        <RenameResumeDialog
          item={{ name: `${comp.name} Copy` }}
          close={() => setDuplicateOpen(false)}
          save={(x: any, setDialogError: any) =>
            duplicate(x.name, setDialogError)
          }
        />
      )}
      {homeDialog?.type === "rename" && (
        <RenameResumeDialog
          item={homeDialog.item}
          close={() => setHomeDialog(null)}
          save={saveHomeMetadata}
        />
      )}
      {homeDialog?.type === "details" && (
        <EditDetailsDialog
          item={homeDialog.item}
          close={() => setHomeDialog(null)}
          save={saveHomeMetadata}
        />
      )}
    </main>
  );
}
function ResumeDetails({ comp, save, savePreferences, status }: any) {
  const [collapsed, setCollapsed] = useState(false);
  const [draft, setDraft] = useState({
    name: comp.name,
    description: comp.description || "",
    display_title: comp.display_title || "",
    target_company: comp.target_company || "",
    target_role: comp.target_role || "",
  });
  useEffect(() => {
    setDraft({
      name: comp.name,
      description: comp.description || "",
      display_title: comp.display_title || "",
      target_company: comp.target_company || "",
      target_role: comp.target_role || "",
    });
  }, [comp.id, comp.revision]);
  const field = (key: string, label: string, required = false) => (
    <label>
      {label}
      {required ? " *" : ""}
      <input
        value={draft[key as keyof typeof draft]}
        required={required}
        maxLength={key === "name" ? 120 : 200}
        onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
        onBlur={() => save(draft)}
      />
    </label>
  );
  return (
    <section
      className={`resume-details editor-section ${collapsed ? "collapsed" : "expanded"}`}
      aria-labelledby="resume-details-title"
    >
      <div className="section-heading resume-details-heading">
        <h2 id="resume-details-title">
          <AppIcon name="details" /> Resume Details
        </h2>
        <button
          className="section-chevron"
          aria-expanded={!collapsed}
          aria-controls="resume-details-body"
          aria-label={`${collapsed ? "Expand" : "Collapse"} Resume Details`}
          onClick={() => setCollapsed((value) => !value)}
        >
          <span aria-hidden="true">↓</span>
        </button>
      </div>
      {!collapsed && (
        <div id="resume-details-body" className="resume-details-body">
          <div className="form-grid">
            {field("name", "Internal name", true)}
            {field("display_title", "Display title")}
            {field("target_company", "Target company")}
            {field("target_role", "Target role")}
          </div>
          <small>
            Display title and target details are planning metadata and are not
            printed on the resume.
          </small>
          <fieldset className="composition-preferences">
            <legend>Resume preferences</legend>
            <label>
              Preferred page length
              <select
                value={comp.preferred_page_length || 1}
                onChange={(e) =>
                  savePreferences({
                    preferred_page_length: Number(e.target.value),
                    date_format: comp.date_format || "long",
                    section_sort_modes: comp.section_sort_modes || {},
                  })
                }
              >
                <option value={1}>1 page</option>
                <option value={2}>2 pages</option>
                <option value={3}>3 pages</option>
              </select>
            </label>
            <label>
              Date format{" "}
              <small aria-live="polite">
                Example:{" "}
                {comp.date_format === "year"
                  ? "2026"
                  : comp.date_format === "numeric"
                    ? "10/2026"
                    : comp.date_format === "short"
                      ? "Oct 2026"
                      : "October 2026"}
              </small>
              <select
                value={comp.date_format || "long"}
                onChange={(e) =>
                  savePreferences({
                    preferred_page_length: comp.preferred_page_length || 1,
                    date_format: e.target.value,
                    section_sort_modes: comp.section_sort_modes || {},
                  })
                }
              >
                <option value="year">Year only</option>
                <option value="numeric">Numeric month/year</option>
                <option value="short">Short month/year</option>
                <option value="long">Long month/year</option>
              </select>
            </label>
          </fieldset>
        </div>
      )}
    </section>
  );
}

function HomeScreen({
  lib,
  error,
  dismissError,
  section,
  setSection,
  query,
  setQuery,
  view,
  setView,
  createResume,
  openResume,
  renameResume,
  editDetails,
  setArchived,
  openLibrary,
}: any) {
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const archived = section === "bin";
  const rows = (lib.compositions || []).filter(
    (item: any) =>
      Boolean(item.archived_at) === archived &&
      [
        item.name,
        item.display_title,
        item.target_company,
        item.target_role,
      ].some((value: any) =>
        (value || "").toLowerCase().includes(query.trim().toLowerCase()),
      ),
  );
  const modified = (item: any) =>
    item.autosaved_at || item.updated_at || item.created_at;
  const formatDate = (value: string | null) =>
    value
      ? new Intl.DateTimeFormat(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        }).format(new Date(value))
      : "Unavailable";
  const menu = (item: any) => (
    <div className="resume-menu-wrap">
      <button
        className="icon-button"
        aria-label={`Actions for ${item.name}`}
        aria-haspopup="menu"
        aria-expanded={openMenu === item.id}
        onClick={(event) => {
          event.stopPropagation();
          setOpenMenu(openMenu === item.id ? null : item.id);
        }}
      >
        ⋯
      </button>
      {openMenu === item.id && (
        <div className="resume-menu" role="menu">
          {!archived && (
            <button
              role="menuitem"
              onClick={() => {
                setOpenMenu(null);
                renameResume(item);
              }}
            >
              Rename
            </button>
          )}
          {!archived && (
            <button
              role="menuitem"
              onClick={() => {
                setOpenMenu(null);
                editDetails(item);
              }}
            >
              Edit details
            </button>
          )}
          <button
            role="menuitem"
            className={archived ? "" : "danger-text"}
            onClick={() => {
              setOpenMenu(null);
              setArchived(item, !archived);
            }}
          >
            {archived ? "Restore" : "Move to Bin"}
          </button>
        </div>
      )}
    </div>
  );
  return (
    <main className="home-shell" onClick={() => openMenu && setOpenMenu(null)}>
      <aside className="home-rail" aria-label="Primary navigation">
        <img className="rail-logo" src={compactLogo} alt="Resume Engine" />
        <button
          className={section === "active" ? "rail-link active" : "rail-link"}
          onClick={() => setSection("active")}
        >
          <AppIcon name="home" />
          Home
        </button>
        <button className="rail-link" onClick={openLibrary}>
          <AppIcon name="library" />
          Library
        </button>
        <button
          className={section === "bin" ? "rail-link active" : "rail-link"}
          onClick={() => setSection("bin")}
        >
          <AppIcon name="bin" />
          Bin
        </button>
      </aside>
      <section className="home-content">
        {error && (
          <div role="alert" className="error home-error">
            {error}
            <button onClick={dismissError}>Dismiss</button>
          </div>
        )}
        <header className="home-hero">
          <img src={primaryLogo} alt="Resume Engine" className="home-logo" />
          <h1>Resume Engine</h1>
          <p>A Really Useful tool for completing job applications</p>
          {section === "active" && (
            <div className="hero-actions">
              <button className="primary-action" onClick={createResume}>
                + New Resume
              </button>
              <span className="tooltip-wrap">
                <button disabled aria-describedby="import-help">
                  Import Existing Resume
                </button>
                <span id="import-help" role="tooltip">
                  Import from an existing resume is coming soon.
                </span>
              </span>
            </div>
          )}
        </header>
        <section
          className="resume-library"
          aria-labelledby="resume-library-title"
        >
          <div className="library-toolbar">
            <label className="resume-search">
              <span aria-hidden="true">⌕</span>
              <span className="sr-only">Search resumes</span>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search your resumes…"
              />
            </label>
            <div className="view-toggle" aria-label="Resume view">
              <button
                aria-pressed={view === "list"}
                onClick={() => setView("list")}
              >
                ☷ List View
              </button>
              <button
                aria-pressed={view === "card"}
                onClick={() => setView("card")}
              >
                ▦ Card View
              </button>
            </div>
          </div>
          <div className="library-title-row">
            <h2 id="resume-library-title">
              {archived ? "Bin" : "My Resumes"} ({rows.length})
            </h2>
          </div>
          {rows.length === 0 ? (
            <div className="empty-state">
              <strong>
                {query
                  ? "No matching resumes"
                  : archived
                    ? "The Bin is empty"
                    : "No resumes yet"}
              </strong>
              <span>
                {query
                  ? "Try a different search."
                  : archived
                    ? "Resumes moved to the Bin will appear here."
                    : "Create a new resume to get started."}
              </span>
            </div>
          ) : view === "list" ? (
            <div
              className="resume-table"
              role="table"
              aria-label={archived ? "Deleted resumes" : "Active resumes"}
            >
              <div className="resume-table-head" role="row">
                <span role="columnheader">Name</span>
                <span role="columnheader">Target Company</span>
                <span role="columnheader">Target Role</span>
                <span role="columnheader">Last Modified</span>
                <span aria-hidden="true" />
              </div>
              {rows.map((item: any) => (
                <div className="resume-table-row" role="row" key={item.id}>
                  <button
                    className="resume-name"
                    disabled={archived}
                    onClick={() => openResume(item.id)}
                    role="cell"
                  >
                    <AppIcon name="document" aria-hidden="true" />{" "}
                    <span>{item.name}</span>
                  </button>
                  <span
                    role="cell"
                    className={!item.target_company ? "placeholder-value" : ""}
                  >
                    {item.target_company || "—"}
                  </span>
                  <span
                    role="cell"
                    className={!item.target_role ? "placeholder-value" : ""}
                  >
                    {item.target_role || "—"}
                  </span>
                  <span role="cell">{formatDate(modified(item))}</span>
                  <span role="cell">{menu(item)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="resume-card-grid">
              {rows.map((item: any) => (
                <article className="resume-card" key={item.id}>
                  <div className="resume-card-top">
                    <span className="resume-card-icon" aria-hidden="true">
                      <AppIcon name="document" />
                    </span>
                    {menu(item)}
                  </div>
                  <button
                    className="card-open"
                    disabled={archived}
                    onClick={() => openResume(item.id)}
                  >
                    <strong>{item.name}</strong>
                  </button>
                  <dl>
                    <div>
                      <dt>Target Company</dt>
                      <dd>{item.target_company || "—"}</dd>
                    </div>
                    <div>
                      <dt>Target Role</dt>
                      <dd>{item.target_role || "—"}</dd>
                    </div>
                  </dl>
                  <small>Last modified {formatDate(modified(item))}</small>
                </article>
              ))}
            </div>
          )}
        </section>
      </section>
    </main>
  );
}

function groupBullets(rows: any[]) {
  const m = new Map<string, any>();
  for (const r of rows || []) {
    if (!m.has(r.id))
      m.set(r.id, {
        id: r.id,
        parent_id: r.parent_id,
        sort_order: r.sort_order,
        archived_at: r.archived_at,
        variants: [],
      });
    if (r.variant_id)
      m.get(r.id).variants.push({
        id: r.variant_id,
        bullet_id: r.id,
        variant_name: r.variant_name,
        body: r.body,
        is_default: r.is_default,
        sort_order: r.variant_sort_order,
        archived_at: r.variant_archived_at,
      });
  }
  return [...m.values()];
}
const BUILTIN_SECTIONS = [
  ["summary", "Summary"],
  ["education", "Education"],
  ["tools", "Skills"],
  ["projects", "Projects"],
  ["work_experience", "Work Experience"],
  ["leadership", "Leadership"],
  ["personal_interests", "Personal Interests"],
];
const EDITOR_SECTION_ICONS: Record<
  string,
  Parameters<typeof AppIcon>[0]["name"]
> = {
  profile: "profile",
  summary: "document",
  education: "education",
  tools: "skills",
  projects: "projects",
  work_experience: "experience",
  leadership: "leadership",
  personal_interests: "interests",
};
const editorSectionIcon = (key: string) =>
  key.startsWith("custom:")
    ? "custom-sections"
    : EDITOR_SECTION_ICONS[key] || "custom-sections";
function AddBulletButton() {
  return (
    <span className="tooltip-wrap">
      <button
        type="button"
        className="add-bullet-inline"
        aria-disabled="true"
        aria-describedby="add-bullet-soon"
        onClick={(e) => e.preventDefault()}
      >
        + Add Bullet
      </button>
      <span id="add-bullet-soon" role="tooltip">
        Adding bullets is coming soon.
      </span>
    </span>
  );
}
const ENTRY_LABELS: any = {
  projects: "Project",
  work_experience: "Experience",
  education: "Education",
  tool_groups: "Skill Group",
  leadership: "Leadership",
  personal_interests: "Interest",
};
function AddEntryDialog({
  comp,
  section,
  items,
  includedIds,
  close,
  saved,
  fail,
}: any) {
  const custom = section.startsWith("custom:");
  const [tab, setPickerTab] = useState<"library" | "create">(
    custom ? "create" : "library",
  );
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<any>(null);
  const [draft, setDraft] = useState<any>({});
  const [busy, setBusy] = useState(false);
  const label = custom ? "Entry" : ENTRY_LABELS[section];
  const available = items
    .filter(
      (x: any) =>
        !x.archived_at &&
        !includedIds.includes(String(x.id)) &&
        JSON.stringify(x).toLowerCase().includes(q.toLowerCase()),
    )
    .slice(0, 5);
  const add = async () => {
    setBusy(true);
    try {
      if (tab === "library") {
        if (!selected) return;
        const endpoint =
          section === "personal_interests"
            ? "interests"
            : section === "tool_groups"
              ? "tool-groups"
              : section === "education"
                ? "education"
                : `historical/${section}`;
        saved(
          await api(`/api/compositions/${comp.id}/${endpoint}`, {
            method: "PUT",
            body: JSON.stringify({
              revision: comp.revision,
              item_id: selected.id,
              included: true,
            }),
          }),
          selected.id,
        );
      } else {
        saved(
          await api(`/api/compositions/${comp.id}/entries/create`, {
            method: "POST",
            body: JSON.stringify({
              revision: comp.revision,
              section,
              fields: draft,
            }),
          }),
        );
      }
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <ModalShell title={`Add ${label}`} close={close}>
      {!custom && (
        <div className="picker-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={tab === "library"}
            onClick={() => setPickerTab("library")}
          >
            Choose from Library
          </button>
          <button
            role="tab"
            aria-selected={tab === "create"}
            onClick={() => setPickerTab("create")}
          >
            Create New
          </button>
        </div>
      )}
      {tab === "library" ? (
        <>
          <input
            aria-label={`Search ${label}`}
            placeholder="Search library…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div className="entry-picker-grid">
            <div className="entry-picker-results">
              {available.map((x: any) => (
                <button
                  className="entry-picker-result"
                  aria-pressed={selected?.id === x.id}
                  key={x.id}
                  onClick={() => setSelected(x)}
                >
                  <strong>
                    {x.name || x.organization || x.institution || x.body}
                  </strong>
                  <small>
                    {x.title || x.subtitle || x.degree_major || ""} ·{" "}
                    {
                      groupBullets(x.bullets || []).filter(
                        (b: any) => !b.archived_at,
                      ).length
                    }{" "}
                    bullets
                  </small>
                </button>
              ))}
              <small>
                Showing 1–{available.length} of {available.length} items
              </small>
            </div>
            <div className="entry-picker-details">
              {selected ? (
                <pre>{JSON.stringify(selected, null, 2)}</pre>
              ) : (
                <p>Select an entry to review details and bullets.</p>
              )}
            </div>
          </div>
        </>
      ) : (
        <div className="form-grid">
          <label className="full">
            Primary text
            <input
              value={
                draft.name ||
                draft.organization ||
                draft.institution ||
                draft.body ||
                ""
              }
              onChange={(e) =>
                setDraft(
                  section === "projects"
                    ? { ...draft, name: e.target.value }
                    : section === "education"
                      ? { ...draft, institution: e.target.value }
                      : section === "personal_interests"
                        ? { ...draft, body: e.target.value }
                        : { ...draft, organization: e.target.value },
                )
              }
            />
          </label>
          {["projects", "work_experience", "leadership"].includes(section) && (
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
                      end_year: null,
                      end_month: null,
                    })
                  }
                />
                Current
              </label>
            </>
          )}
          {section === "education" && (
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
          )}
          {["work_experience", "leadership"].includes(section) && (
            <label>
              Title
              <input
                value={draft.title || ""}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              />
            </label>
          )}
        </div>
      )}
      <div className="form-actions">
        <button onClick={close}>Cancel</button>
        <button
          className="primary"
          disabled={busy || (tab === "library" && !selected)}
          onClick={add}
        >
          Add to Resume
        </button>
      </div>
    </ModalShell>
  );
}
function chronologicalKey(x: any) {
  const structured = !!(x.start_year || x.end_year || x.is_current);
  if (!structured) return [1, 0, 0, x.sort_order || 0, String(x.id)];
  const end = x.is_current
      ? 999912
      : (x.end_year || 0) * 100 + (x.end_month || 12),
    start = (x.start_year || 0) * 100 + (x.start_month || 1);
  return [
    0,
    x.is_current ? -1 : 0,
    -end,
    -start,
    x.sort_order || 0,
    String(x.id),
  ];
}
function SectionsPanel({
  comp,
  lib,
  setComp,
  setStatus,
  setError,
  collapsed,
  setCollapsed,
  begin,
  saveCompositionPreferences,
  chooseSummary,
  chooseInterest,
  chooseLibraryItem,
  openLibraryFromEditor,
}: any) {
  const [compositionItems, setCompositionItems] = useState<any[]>([]),
    [placements, setPlacements] = useState<any[]>([]),
    [entryExpanded, setEntryExpanded] = useState<Record<string, boolean>>(
      () => {
        try {
          return JSON.parse(
            localStorage.getItem(`resume-engine-entry-expansion`) || "{}",
          );
        } catch {
          return {};
        }
      },
    ),
    [entryDialog, setEntryDialog] = useState<any>(null),
    [menu, setMenu] = useState<string | null>(null),
    [announcement, setAnnouncement] = useState("");
  const reload = () =>
    Promise.all([
      api<any[]>(`/api/compositions/${comp.id}/items`),
      api<any[]>(`/api/compositions/${comp.id}/bullet-placements`),
    ])
      .then(([i, b]) => {
        setCompositionItems(i);
        setPlacements(b);
      })
      .catch((e: any) => setError(e.message));
  useEffect(() => {
    reload();
  }, [comp.id, comp.revision]);
  useEffect(
    () =>
      localStorage.setItem(
        "resume-engine-entry-expansion",
        JSON.stringify(entryExpanded),
      ),
    [entryExpanded],
  );
  const clean = (x: string) => (x.startsWith("hidden:") ? x.slice(7) : x),
    source = comp.resume.section_order || [],
    custom = lib.custom_sections.map((x: any) => [
      `custom:${x.id}`,
      x.title,
      x,
    ]);
  const order = [
    ...source,
    ...custom
      .map((x: any) => x[0])
      .filter((x: string) => !source.map(clean).includes(x)),
  ];
  const rows = order
    .map((stored: string) => {
      const key = clean(stored),
        b = BUILTIN_SECTIONS.find((x) => x[0] === key),
        c = custom.find((x: any) => x[0] === key),
        base = b ? [b[0], b[1], null] : c;
      return base ? [...base, !stored.startsWith("hidden:")] : null;
    })
    .filter(Boolean) as any[];
  const save = async (next: any[]) => {
    try {
      setStatus("Saving…");
      const section_order = next.map((x) => (x[3] ? x[0] : `hidden:${x[0]}`));
      setComp(
        await api(`/api/compositions/${comp.id}/sections`, {
          method: "PUT",
          body: JSON.stringify({
            revision: comp.revision,
            section_order,
            interest_layout: comp.resume.interest_layout || "compact",
            included_builtin: next
              .filter((x) => !x[0].startsWith("custom:") && x[3])
              .map((x) => x[0]),
            included_custom: next
              .filter((x) => x[0].startsWith("custom:") && x[3])
              .map((x) => x[0].slice(7)),
          }),
        }),
      );
      setStatus("Saved");
    } catch (e: any) {
      setError(e.message);
      setStatus(e.status === 409 ? "Conflict" : "Save failed");
    }
  };
  const moveSection = (i: number, d: number) => {
    const t = i + d;
    if (t < 0 || t >= rows.length) return;
    const n = rows.map((x) => [...x]);
    [n[i], n[t]] = [n[t], n[i]];
    save(n);
    setAnnouncement(
      `${rows[i][1]} moved to position ${t + 1} of ${rows.length}.`,
    );
  };
  const sources: any = {
    education: lib.education,
    tool_groups: lib.tool_groups,
    projects: lib.projects,
    work_experience: lib.employment,
    leadership: lib.leadership,
    personal_interests: lib.interests,
  };
  const sectionEntries = (key: string) => {
    let a = compositionItems
      .filter((x) => x.section === key)
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((x) =>
        (sources[key] || []).find(
          (r: any) => String(r.id) === String(x.item_id),
        ),
      )
      .filter(Boolean);
    if (
      (comp.section_sort_modes?.[key] || "automatic") === "automatic" &&
      ["projects", "work_experience", "leadership"].includes(key)
    )
      a = [...a].sort((a, b) => {
        const left = chronologicalKey(a),
          right = chronologicalKey(b);
        for (let i = 0; i < Math.max(left.length, right.length); i++) {
          if (left[i] < right[i]) return -1;
          if (left[i] > right[i]) return 1;
        }
        return 0;
      });
    return a;
  };
  const reorder = async (key: string, items: any[], i: number, d: number) => {
    const t = i + d;
    if (t < 0 || t >= items.length) return;
    const ids = items.map((x) => x.id);
    [ids[i], ids[t]] = [ids[t], ids[i]];
    try {
      setComp(
        await api(`/api/compositions/${comp.id}/items/order`, {
          method: "PUT",
          body: JSON.stringify({ revision: comp.revision, section: key, ids }),
        }),
      );
      setAnnouncement(
        `${ENTRY_LABELS[key]} moved to position ${t + 1} of ${items.length}.`,
      );
    } catch (e: any) {
      setError(e.message);
    }
  };
  const card = (key: string, x: any, i: number, items: any[]) => {
    const id = String(x.id),
      expanded = entryExpanded[id] ?? i === 0,
      bullets = placements
        .filter((b) => String(b.destination_parent_id) === id)
        .sort((a, b) => a.sort_order - b.sort_order),
      title = x.organization || x.name || x.institution || x.body,
      subtitle = x.title || x.subtitle || x.degree_major || x.date_label || "",
      manual = (comp.section_sort_modes?.[key] || "automatic") === "manual";
    return (
      <article className="entry-card" key={id}>
        <div className="entry-card-header">
          <button className="item-drag-handle" aria-label={`Drag ${title}`}>
            ⠿
          </button>
          <span className="section-icon">
            <AppIcon name={editorSectionIcon(key)} />
          </span>
          <div>
            <strong>{title}</strong>
            <div className="entry-meta">
              <span>{subtitle}</span>
              <span>{x.location}</span>
              <span>{x.date_label || x.display_date}</span>
            </div>
          </div>
          <span className="entry-menu-wrap">
            <button
              aria-label={`Actions for ${title}`}
              onClick={() => setMenu(menu === id ? null : id)}
            >
              ⋮
            </button>
            {menu === id && (
              <span className="entry-menu" role="menu">
                <button
                  role="menuitem"
                  onClick={() => openLibraryFromEditor(key, id)}
                >
                  Edit in Library
                </button>
                <button
                  role="menuitem"
                  disabled={!manual || i === 0}
                  title={
                    !manual ? "Choose Manual order to move entries." : undefined
                  }
                  onClick={() => reorder(key, items, i, -1)}
                >
                  Move up
                </button>
                <button
                  role="menuitem"
                  disabled={!manual || i === items.length - 1}
                  onClick={() => reorder(key, items, i, 1)}
                >
                  Move down
                </button>
                <button
                  role="menuitem"
                  onClick={() =>
                    key === "personal_interests"
                      ? chooseInterest(x, false)
                      : chooseLibraryItem(key, x, false)
                  }
                >
                  Remove from this resume
                </button>
              </span>
            )}
          </span>
          <button
            className="section-chevron"
            aria-expanded={expanded}
            onClick={() =>
              setEntryExpanded({ ...entryExpanded, [id]: !expanded })
            }
          >
            ↓
          </button>
        </div>
        {expanded && (
          <div className="entry-card-body">
            {key === "tool_groups" && (
              <div className="tool-chips">
                {(x.items || []).map((t: any) => (
                  <span className="tool-chip" key={t.id}>
                    {t.name}
                  </span>
                ))}
              </div>
            )}
            <h4>Bullet Points</h4>
            <div className="bullet-list">
              {bullets.map((b: any, bi: number) => (
                <div className="bullet-row" key={b.id}>
                  <button
                    className="item-drag-handle"
                    aria-label={`Drag bullet ${bi + 1}`}
                  >
                    ⠿
                  </button>
                  <span>
                    {b.wording_snapshot}
                    {b.active_variant_count > 1 && (
                      <small> · {b.variant_name}</small>
                    )}
                    {b.usage_status !== "current" && (
                      <span className="bullet-status">{b.usage_status}</span>
                    )}
                  </span>
                  <button
                    aria-label="Bullet actions"
                    onClick={async () => {
                      if (
                        await confirmDialog({
                          title: "Remove bullet",
                          message: "Remove this bullet from this resume?",
                          confirmLabel: "Remove",
                          danger: true,
                        })
                      ) {
                        try {
                          setComp(
                            await api(
                              `/api/compositions/${comp.id}/bullet-placements/${b.id}?revision=${comp.revision}`,
                              { method: "DELETE" },
                            ),
                          );
                        } catch (e: any) {
                          setError(e.message);
                        }
                      }
                    }}
                  >
                    ⋮
                  </button>
                </div>
              ))}
            </div>
            <AddBulletButton />
          </div>
        )}
      </article>
    );
  };
  const content = (key: string) => {
    if (key === "summary")
      return (
        <div className="entry-card">
          <label>
            Summary variant
            <select
              value={comp.summary_variant_id || ""}
              onChange={(e) => chooseSummary(e.target.value)}
            >
              <option value="">No summary</option>
              {lib.summary_variants
                .filter((x: any) => !x.archived_at)
                .map((x: any) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
            </select>
          </label>
        </div>
      );
    if (key.startsWith("custom:")) {
      const sec = lib.custom_sections.find(
        (x: any) => `custom:${x.id}` === key,
      );
      return (
        <div className="entry-list">
          {sec?.entries.map((x: any, i: number) =>
            card(key, x, i, sec.entries),
          )}
          <button
            className="add-entry-button"
            onClick={() => setEntryDialog({ section: key, items: [] })}
          >
            + Add Entry
          </button>
        </div>
      );
    }
    const items = sectionEntries(key);
    return (
      <div className="entry-list">
        {["projects", "work_experience", "leadership"].includes(key) && (
          <label className="order-mode">
            Order:
            <select
              value={comp.section_sort_modes?.[key] || "automatic"}
              onChange={(e) =>
                saveCompositionPreferences({
                  preferred_page_length: comp.preferred_page_length || 1,
                  date_format: comp.date_format || "long",
                  section_sort_modes: {
                    ...comp.section_sort_modes,
                    [key]: e.target.value,
                  },
                })
              }
            >
              <option value="automatic">By date</option>
              <option value="manual">Manual</option>
            </select>
          </label>
        )}
        {items.map((x: any, i: number) => card(key, x, i, items))}
        <button
          className="add-entry-button"
          onClick={() =>
            setEntryDialog({
              section: key,
              items: sources[key] || [],
              includedIds: items.map((x: any) => String(x.id)),
            })
          }
        >
          + Add {ENTRY_LABELS[key]}
        </button>
      </div>
    );
  };
  return (
    <section className="resume-sections" aria-labelledby="sections-title">
      <div className="sections-heading">
        <h2 id="sections-title">
          Sections{" "}
          <span className="tooltip-wrap">
            <button aria-describedby="sections-help">?</button>
            <span id="sections-help" role="tooltip">
              Remove entries from this resume from each card menu. Archive
              reusable records in Library.
            </span>
          </span>
        </h2>
        <button
          onClick={() =>
            openLibraryFromEditor("custom", undefined, "custom-section")
          }
        >
          + Add Section
        </button>
      </div>
      <div className="sr-only" aria-live="polite">
        {announcement}
      </div>
      <article className="section-card profile-section">
        <div className="section-card-header">
          <span className="section-icon">
            <AppIcon name="profile" />
          </span>
          <strong>Profile</strong>
          <button
            className="section-chevron"
            aria-expanded={!collapsed.includes("profile")}
            onClick={() =>
              setCollapsed(
                collapsed.includes("profile")
                  ? collapsed.filter((x: string) => x !== "profile")
                  : [...collapsed, "profile"],
              )
            }
          >
            ↓
          </button>
        </div>
      </article>
      {rows.map((r: any, i: number) => {
        const closed = collapsed.includes(r[0]);
        return (
          <article
            className={`section-card ${closed ? "collapsed" : "expanded"}`}
            data-section-key={r[0]}
            key={r[0]}
          >
            <div className="section-card-header">
              <button
                className="drag-handle"
                aria-label={`Move ${r[1]}`}
                onKeyDown={(e) => {
                  if (e.key === "ArrowUp") moveSection(i, -1);
                  if (e.key === "ArrowDown") moveSection(i, 1);
                }}
              >
                ⠿
              </button>
              <span className="section-icon">
                <AppIcon name={editorSectionIcon(r[0])} />
              </span>
              <strong>{r[1]}</strong>
              <span className="item-count">
                {r[0] === "summary" ? "" : sectionEntries(r[0]).length || ""}
              </span>
              <label className="visibility-toggle">
                <input
                  type="checkbox"
                  role="switch"
                  aria-checked={r[3]}
                  checked={r[3]}
                  onChange={(e) => {
                    const n = rows.map((x) => [...x]);
                    n[i][3] = e.target.checked;
                    save(n);
                  }}
                />
                <span className="sr-only">
                  {r[3] ? "Hide" : "Show"} {r[1]}
                </span>
              </label>
              <button
                className="section-chevron"
                aria-expanded={!closed}
                onClick={() =>
                  setCollapsed(
                    closed
                      ? collapsed.filter((x: string) => x !== r[0])
                      : [...collapsed, r[0]],
                  )
                }
              >
                ↓
              </button>
            </div>
            {!closed && (
              <div className="section-card-body">{content(r[0])}</div>
            )}
          </article>
        );
      })}
      {entryDialog && (
        <AddEntryDialog
          comp={comp}
          {...entryDialog}
          close={() => setEntryDialog(null)}
          fail={(e: any) => setError(e.message)}
          saved={(next: any, id?: string) => {
            setComp(next);
            setEntryDialog(null);
            if (id) setEntryExpanded({ ...entryExpanded, [id]: true });
            reload();
          }}
        />
      )}
    </section>
  );
}

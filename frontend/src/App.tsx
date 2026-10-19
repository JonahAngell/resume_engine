import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import FitIndicator, { Fit, linesOver } from "./FitIndicator";
import ResumePreview, { type PreviewMarkClick } from "./ResumePreview";
import { api } from "./api";
import { RESUME_ENGINE_BUILD, RESUME_ENGINE_VERSION } from "./app-version";
import { EditorHistory } from "./EditorHistory";
import StandaloneLibrary from "./StandaloneLibrary";
import JobDocument from "./JobDocument";
import { activeIdsForTerms, buildMatchMarks, type MarkItem } from "./matchMarks";
import AddSkillDialog from "./AddSkillDialog";
import SuggestVariantDialog from "./SuggestVariantDialog";
import KeywordAssistDialog from "./KeywordAssistDialog";
import MatchDashboard from "./match/MatchDashboard";
import MarkPopover, { type PopoverAnchor } from "./match/MarkPopover";
import { useJobMatch } from "./match/useJobMatch";
import type { AssistRequest, DashboardTab } from "./match/types";
import JobsPage from "./JobsPage";
import { AppIcon } from "./AppIcon";
import ModalShell from "./ModalShell";
import OverflowMenu from "./OverflowMenu";
import RevisionHistoryPanel from "./RevisionHistoryPanel";
import { chooseSaveMode, confirmDialog } from "./ConfirmDialog";
import {
  bulletCoaching,
  dateFormatCoaching,
  firstJobCoaching,
  lastJobCoaching,
  laterJobCoaching,
  sectionCoaching,
} from "./resumeCoaching";
import { RenameResumeDialog, EditDetailsDialog, JobTargetField } from "./HomeDialogs";
import MonthYearField from "./MonthYearField";
import { autoFitSkillRows } from "./skillRows";
import { SectionHelp } from "./SectionHelp";
import { EditorLibraryDialogs } from "./editor/EditorLibraryDialogs";
import { profilePayload } from "./LibraryEntryForms";
import { RecordActions } from "./editor/LibraryPickerDialog";
import { ShrinkReviewDialog, placementLineId, type AiJobContext } from "./editor/AiBulletTools";
import { DragHandle, dragRowClass, useRowDrag } from "./editor/useRowDrag";
import OptionGrid from "./OptionGrid";
import ImportResumeDialog from "./ImportResumeDialog";
import NewResumeDialog, { type RecommendResult } from "./NewResumeDialog";

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
  job_description_id?: string | null;
  preferred_page_length: number;
  date_format: "year" | "numeric" | "short" | "long";
  template_style: "classic" | "sheets" | "harvard" | "dais" | "sre";
  skill_row_max: number;
  section_sort_modes: Record<string, "automatic" | "manual">;
  summary_variant_id?: string | null;
  profile_id?: string | null;
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
  const [screen, setScreen] = useState<
    "home" | "editor" | "library" | "jobs" | "import"
  >(() =>
    location.hash === "#library"
      ? "library"
      : location.hash === "#jobs"
        ? "jobs"
        : "home",
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
  const [shrinkOpen, setShrinkOpen] = useState(false);
  const [status, setStatus] = useState("Loading…");
  const [error, setError] = useState("");
  const [newResumeOpen, setNewResumeOpen] = useState(false);
  const [defaultSetDialog, setDefaultSetDialog] = useState(false);
  // Shown on Job match after "New from AI Recommendation" builds a resume.
  const [aiBuilt, setAiBuilt] = useState<
    (Omit<RecommendResult, "composition"> & { compositionId: string }) | null
  >(null);
  const [autoCoach, setAutoCoach] = useState(false);
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
  const [editorTab, setEditorTab] = useState<"edit" | "match">("edit");
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
  const [activeMatchIds, setActiveMatchIds] = useState<string[]>([]);
  const [dashTab, setDashTab] = useState<DashboardTab>("overview");
  const [dashFocus, setDashFocus] = useState<{ key: string; nonce: number } | null>(null);
  const [assist, setAssist] = useState<AssistRequest | null>(null);
  const [popover, setPopover] = useState<{
    anchor: PopoverAnchor;
    ids: string[];
    lineId: string;
    source: "job" | "resume";
  } | null>(null);
  const [matchRailOpen, setMatchRailOpen] = useState(true);
  const [zoom, setZoom] = useState(() => {
    const stored = Number(localStorage.getItem("resume-engine-preview-zoom"));
    return stored >= 50 && stored <= 150 ? stored : 100;
  });
  const splitterDragging = useRef(false);
  const compRef = useRef<Comp | null>(null);
  const historyRef = useRef(new EditorHistory());
  const sessionId = useRef(crypto.randomUUID());
  const [, refreshHistory] = useState(0);
  const compactTopbar = useMediaQuery(COMPACT_TOPBAR_QUERY);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
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
        body: JSON.stringify({ seed_key: "nia-calder-resume-v1" }),
      });
      next = await api<any>("/api/library");
    }
    setLib(next);
    return next;
  };
  const matchState = useJobMatch({
    compositionId: comp?.id || "",
    revision: comp?.revision || 0,
    linkedJobId: comp?.job_description_id || "",
    active: editorTab === "match" && !!comp,
    reloadLibrary: loadLibrary,
  });
  const compareJob = editorTab === "match" ? matchState.compareJob : null;
  const matchMarks = useMemo(() => {
    const match = matchState.match;
    if (editorTab !== "match" || !match) return [];
    return buildMatchMarks([
      ...match.required,
      ...match.preferred,
      ...(match.responsibilities || []),
      ...(match.eligibility_rows || []),
    ]);
  }, [editorTab, matchState.match]);
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
      else if (location.hash === "#jobs") setScreen("jobs");
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
  const chooseProfile = async (profile_id: string) => {
    if (!comp || !profile_id) return;
    setStatus("Saving…");
    try {
      setComp(
        await api<Comp>(`/api/compositions/${comp.id}/profile`, {
          method: "PUT",
          body: JSON.stringify({
            revision: comp.revision,
            profile_id,
          }),
        }),
      );
      setStatus("Saved");
    } catch (e: any) {
      setStatus(e.status === 409 ? "Conflict" : "Save failed");
      setError(e.message);
    }
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
  const openNewResume = () => setNewResumeOpen(true);
  const openCreated = async (next: Comp) => {
    setComp(next);
    await loadLibrary();
    setPreviewRevision(null);
    setScreen("editor");
    setNewResumeOpen(false);
  };
  const createFromSet = async (defaultSetId: string | null) => {
    const next = await api<Comp>("/api/compositions", {
      method: "POST",
      body: JSON.stringify(
        defaultSetId ? { default_set_id: defaultSetId } : { entire_library: true },
      ),
    });
    setAiBuilt(null);
    setEditorTab("edit");
    await openCreated(next);
  };
  const createFromAi = async (result: RecommendResult) => {
    const { composition, ...summary } = result;
    setAiBuilt({ ...summary, compositionId: composition.id });
    setAutoCoach(true);
    setDashTab("coach");
    setEditorTab("match");
    setMatchRailOpen(true);
    await openCreated(composition);
  };
  const manageDefaultSets = () => {
    setNewResumeOpen(false);
    sessionStorage.setItem(
      "resume-engine-library-target",
      JSON.stringify({ sectionKey: "default-sets", entryId: null, contentView: "entries" }),
    );
    location.hash = "library";
    setScreen("library");
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
      (comp.preferred_page_length || 1) === 1 &&
      preferences.preferred_page_length > 1 &&
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
      template_style: comp.template_style || "classic",
      skill_row_max: comp.skill_row_max || 4,
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
    target_company?: string;
    target_role?: string;
    job_description_id?: string | null;
  }) => {
    if (!comp || comp.archived_at) return;
    const name = metadata.name.trim();
    if (!name) {
      setError("Resume name is required.");
      return;
    }
    const beforeMetadata: {
      name: string;
      description: string;
      display_title: string;
      target_company: string;
      target_role: string;
      job_description_id?: string | null;
    } = {
      name: comp.name,
      description: comp.description || "",
      display_title: comp.display_title || "",
      target_company: comp.target_company || "",
      target_role: comp.target_role || "",
    };
    if ("job_description_id" in metadata) {
      beforeMetadata.job_description_id = comp.job_description_id || null;
    }
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
      const metadata: {
        revision: number;
        name: string;
        description: string;
        display_title: string;
        target_company: string;
        target_role: string;
        job_description_id?: string | null;
      } = {
        revision: item.revision,
        name: item.name.trim(),
        description: item.description || "",
        display_title: item.display_title || "",
        target_company: item.target_company || "",
        target_role: item.target_role || "",
      };
      if ("job_description_id" in item) {
        metadata.job_description_id = item.job_description_id || null;
      }
      await api(`/api/compositions/${item.id}/metadata`, {
        method: "PUT",
        body: JSON.stringify(metadata),
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
      const detail = (await r.json().catch(() => ({}))).detail;
      setError(detail || "Export failed");
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
  const onPreviewMarkClick = useCallback((click: PreviewMarkClick) => {
    setPopover({ anchor: click.anchor, ids: click.matchIds, lineId: click.lineId, source: "resume" });
  }, []);
  const onJobMarkClick = useCallback((markId: string, anchor: PopoverAnchor) => {
    setPopover({ anchor, ids: [markId], lineId: "", source: "job" });
  }, []);
  const closePopover = useCallback(() => setPopover(null), []);
  const popoverItems = useMemo<MarkItem[]>(() => {
    if (!popover) return [];
    const items = matchMarks.filter((mark) => popover.ids.includes(mark.id)).flatMap((mark) => mark.items || []);
    if (!popover.lineId) return items;
    // A click on one resume line offers revisions of that line first.
    return items.map((item) => {
      const here = item.rewrites.filter((target) => target.lineId === popover.lineId);
      return here.length ? { ...item, rewrites: here } : item;
    });
  }, [popover, matchMarks]);
  const onActiveMatch = useCallback((ids: string[]) => {
    setActiveMatchIds((current) =>
      current.length === ids.length && current.every((id, index) => id === ids[index])
        ? current
        : ids,
    );
  }, []);
  useEffect(() => {
    if (editorTab !== "match") {
      setActiveMatchIds([]);
      setPopover(null);
    }
  }, [editorTab]);
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
  const homeDialogs = (
    <>
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
      {newResumeOpen && (
        <NewResumeDialog
          sets={lib.default_sets || []}
          close={() => setNewResumeOpen(false)}
          createFromSet={createFromSet}
          createFromAi={createFromAi}
          manageSets={manageDefaultSets}
        />
      )}
      {defaultSetDialog && comp && (
        <SaveDefaultSetDialog
          sets={lib.default_sets || []}
          initialName={comp.display_title || comp.name}
          close={() => setDefaultSetDialog(false)}
          save={async (name: string, replaceId: string) => {
            await api(`/api/compositions/${comp.id}/default-set`, {
              method: "POST",
              body: JSON.stringify({
                name,
                replace_id: replaceId || null,
              }),
            });
            await loadLibrary();
            setDefaultSetDialog(false);
            setStatus("Saved");
          }}
        />
      )}
    </>
  );
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
        onJobs={() => {
          sessionStorage.removeItem("resume-engine-return-target");
          sessionStorage.removeItem("resume-engine-library-target");
          location.hash = "jobs";
          setScreen("jobs");
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
  const leaveTo = (next: "home" | "library" | "jobs" | "bin") => {
    history.pushState(null, "", next === "library" || next === "jobs" ? `#${next}` : location.pathname);
    if (next === "bin") setHomeSection("bin");
    if (next === "home") setHomeSection("active");
    setScreen(next === "bin" ? "home" : next);
  };
  if (screen === "jobs")
    return (
      <JobsPage
        onHome={() => {
          void loadLibrary();
          leaveTo("home");
        }}
        onLibrary={() => leaveTo("library")}
        onBin={() => leaveTo("bin")}
      />
    );
  if (screen === "import")
    return (
      <ImportResumeDialog
        close={() => setScreen("home")}
        onLibrary={() => {
          location.hash = "library";
          setScreen("library");
        }}
        onJobs={() => {
          location.hash = "jobs";
          setScreen("jobs");
        }}
        onBin={() => {
          setHomeSection("bin");
          setScreen("home");
        }}
        onImported={async (id: string, warnings: string[]) => {
          setError(warnings.length ? warnings.join(" ") : "");
          await loadLibrary();
          await openComposition(id);
        }}
      />
    );
  if (screen === "home")
    return (
      <>
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
        createResume={openNewResume}
        openResume={openComposition}
        renameResume={(item: any) => setHomeDialog({ type: "rename", item })}
        editDetails={(item: any) => setHomeDialog({ type: "details", item })}
        setArchived={setArchivedFromHome}
        openLibrary={() => {
          location.hash = "library";
          setScreen("library");
        }}
        openJobs={() => {
          location.hash = "jobs";
          setScreen("jobs");
        }}
        onImport={() => setScreen("import")}
      />
      {homeDialogs}
    </>
  );
  if (!comp) {
    setScreen("home");
    return null;
  }
  const activeSummaries = lib.summary_variants.filter(
    (x: any) => !x.archived_at,
  );
  const resumePane = (
    <section
      className={`stage preview-workspace${editorTab === "match" ? " compare-doc" : ""}`}
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
            setCurrentPage((p) => Math.min(fit?.actualPageCount || 1, p + 1))
          }
        >
          ›
        </button>
        <span className="preview-toolbar-spacer" />
        <FitIndicator fit={fit} compact />
        {comp && !previewRevision && (
          <button
            type="button"
            className={`shrink-button ${fit && !fit.fits && linesOver(fit) > 0 ? "urgent" : ""}`}
            onClick={() => setShrinkOpen(true)}
            disabled={!fit || fit.state === "measurement-error"}
            title="Find bullets to condense and items to remove so the resume fits its target length"
          >
            <span aria-hidden="true">✦</span> Shrink to fit
          </button>
        )}
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
          highlight={
            editorTab === "match"
              ? { marks: matchMarks, activeIds: activeMatchIds }
              : { marks: [], activeIds: [] }
          }
          onHighlightPage={setCurrentPage}
          onHighlightHover={onActiveMatch}
          onMarkClick={editorTab === "match" ? onPreviewMarkClick : undefined}
        />
      </div>
    </section>
  );
  const matchRailShown = matchRailOpen || !compareJob;
  return (
    <main className="editing-shell">
      <header className="editing-topbar">
        <button
          type="button"
          className="editing-brand"
          aria-label="Home"
          onClick={() => setScreen("home")}
        >
          <img src={compactLogo} alt="" />
          <span>
            Resume <strong>Engine</strong>
          </span>
        </button>
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
        <div className="editor-tabs header-tabs" role="tablist" aria-label="Editor">
          <button
            type="button"
            role="tab"
            aria-selected={editorTab === "edit"}
            className={editorTab === "edit" ? "active" : ""}
            onClick={() => setEditorTab("edit")}
          >
            Edit
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={editorTab === "match"}
            className={editorTab === "match" ? "active" : ""}
            onClick={() => setEditorTab("match")}
          >
            Job match
          </button>
        </div>
        <div className="editing-actions">
          <span
            className={`topbar-status ${status.toLowerCase().replaceAll(" ", "-")}`}
            aria-live="polite"
          >
            {status}
          </span>
          {!compactTopbar && (
            <>
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
            </>
          )}
          <OverflowMenu
            label="More actions"
            items={[
              ...(compactTopbar
                ? [
                    {
                      label: "Library",
                      onSelect: () => {
                        location.hash = "library";
                        setScreen("library");
                      },
                    },
                    {
                      label: "Undo",
                      onSelect: () => runHistoryAction("undo"),
                      disabled:
                        !historyRef.current.snapshot.canUndo ||
                        status === "Conflict",
                    },
                    {
                      label: "Redo",
                      onSelect: () => runHistoryAction("redo"),
                      disabled:
                        !historyRef.current.snapshot.canRedo ||
                        status === "Conflict",
                    },
                  ]
                : []),
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
            title={
              fit && !fit.fits
                ? "Export is available when the page count matches the target length."
                : undefined
            }
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
          {editorTab === "match" ? "Match details" : "Editor"}
        </button>
        <button
          aria-pressed={mobileWorkspace === "preview"}
          onClick={() => setMobileWorkspace("preview")}
        >
          {editorTab === "match" ? "Documents" : "Live View"}
        </button>
      </div>
      {editorTab === "match" ? (
        <div
          className={`compare-workspace mobile-${mobileWorkspace}${matchRailShown ? "" : " rail-collapsed"}`}
        >
          <aside className="compare-rail" aria-label="Job match">
            <div hidden={!matchRailShown}>
              {compareJob && (
                <button
                  type="button"
                  className="rail-collapse"
                  onClick={() => setMatchRailOpen(false)}
                >
                  Hide match details
                </button>
              )}
              <MatchDashboard
                state={matchState}
                compositionId={comp.id}
                revision={comp.revision}
                summaryVariantId={comp.summary_variant_id || null}
                pageCount={fit?.actualPageCount || null}
                tab={dashTab}
                onTab={setDashTab}
                focus={dashFocus}
                onFocus={(key) => {
                  setDashTab("requirements");
                  setDashFocus({ key, nonce: Date.now() });
                }}
                onActive={onActiveMatch}
                onAssist={setAssist}
                onApplied={(next) => setComp(next)}
                autoCoach={autoCoach}
                onAutoCoachDone={() => setAutoCoach(false)}
                built={aiBuilt?.compositionId === comp.id ? aiBuilt : null}
                onDismissBuilt={() => setAiBuilt(null)}
              />
            </div>
            {!matchRailShown && (
              <button
                type="button"
                className="rail-restore"
                onClick={() => setMatchRailOpen(true)}
              >
                Show match details
              </button>
            )}
          </aside>
          <div className="compare-documents">
            <div className="compare-doc job-doc">
              <JobDocument
                job={compareJob}
                marks={matchMarks}
                activeIds={activeMatchIds}
                onActive={onActiveMatch}
                onMarkClick={onJobMarkClick}
              />
            </div>
            {resumePane}
          </div>
          {popover && popoverItems.length > 0 && (
            <MarkPopover
              anchor={popover.anchor}
              items={popoverItems}
              source={popover.source}
              jobId={matchState.jobId}
              onClose={closePopover}
              onAssist={(request) => {
                setPopover(null);
                setAssist(request);
              }}
              onSkip={(item) => {
                setPopover(null);
                matchState.skipKeyword(item.keyword);
              }}
              onShowInDashboard={(item) => {
                setPopover(null);
                setMatchRailOpen(true);
                setMobileWorkspace("editor");
                setDashTab("requirements");
                setDashFocus({ key: `${item.group}:${item.requirement}`, nonce: Date.now() });
              }}
              onShowOther={(item) => {
                setPopover(null);
                onActiveMatch(activeIdsForTerms([item.keyword]));
              }}
            />
          )}
          {assist?.kind === "skill" && (
            <AddSkillDialog
              compositionId={comp.id}
              revision={comp.revision}
              keyword={assist.keyword}
              onApplied={async (next) => {
                setComp(next);
                await loadLibrary();
              }}
              close={() => setAssist(null)}
            />
          )}
          {assist?.kind === "rewrite" && compareJob && (
            <SuggestVariantDialog
              compositionId={comp.id}
              revision={comp.revision}
              job={compareJob}
              target={assist.target}
              onApplied={async (next) => {
                setComp(next);
                await loadLibrary();
              }}
              onAddSkill={(keyword) => setAssist({ kind: "skill", keyword })}
              close={() => setAssist(null)}
            />
          )}
          {assist?.kind === "keyword" && compareJob && (
            <KeywordAssistDialog
              compositionId={comp.id}
              revision={comp.revision}
              job={compareJob}
              keyword={assist.keyword}
              requirement={assist.requirement}
              category={assist.category}
              onApplied={async (next) => {
                setComp(next);
                await loadLibrary();
              }}
              onRevise={(target) => setAssist({ kind: "rewrite", target })}
              onAddSkill={(keyword) => setAssist({ kind: "skill", keyword })}
              close={() => setAssist(null)}
            />
          )}
        </div>
      ) : (
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
            <div className="editor-tab-panel" hidden={editorTab !== "edit"}>
              {error && (
                <div role="alert" className="error">
                  {error}
                  <button onClick={() => setError("")}>Dismiss</button>
                </div>
              )}
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
                <button type="button" onClick={() => setDefaultSetDialog(true)}>
                  Save as defaults set
                </button>
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
                chooseProfile={chooseProfile}
                reloadLibrary={loadLibrary}
                chooseInterest={chooseInterest}
                chooseLibraryItem={chooseLibraryItem}
                included={included}
                openLibraryFromEditor={openLibraryFromEditor}
                aiJobs={matchState.jobs}
                aiJobId={matchState.jobId}
                setAiJobId={matchState.setJobId}
                fit={fit}
                openShrink={() => setShrinkOpen(true)}
              />
            </div>
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
            <span aria-hidden="true">⋮</span>
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
          resumePane
        )}
      </div>
      )}
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
      {shrinkOpen && comp && (
        <ShrinkReviewDialog
          close={() => setShrinkOpen(false)}
          ai={{
            compositionId: comp.id,
            revision: comp.revision,
            jobs: matchState.jobs || [],
            jobId: matchState.jobId || "",
            setJobId: matchState.setJobId,
            fit,
            onApplied: async (next: any) => {
              setComp(next);
              await loadLibrary();
              setStatus("Saved");
            },
            openReview: () => {},
          }}
        />
      )}
      {homeDialogs}
    </main>
  );
}
function ResumeDetails({ comp, save, savePreferences, status }: any) {
  const [collapsed, setCollapsed] = useState(false);
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
          <span aria-hidden="true">
            <AppIcon name="chevron" />
          </span>
        </button>
      </div>
      {!collapsed && (
        <div id="resume-details-body" className="resume-details-body">
          <JobTargetField
            jobId={comp.job_description_id || ""}
            company={comp.target_company || ""}
            role={comp.target_role || ""}
            onChange={(jobId) =>
              save({
                name: comp.name,
                description: comp.description || "",
                display_title: comp.display_title || "",
                target_company: comp.target_company || "",
                target_role: comp.target_role || "",
                job_description_id: jobId || null,
              })
            }
          />
          <fieldset className="composition-preferences">
            <legend>Resume preferences</legend>
            <div className="target-length-field">
              <span id="target-length-label">Target length</span>
              <div className="target-length" role="group" aria-labelledby="target-length-label">
                <button
                  type="button"
                  aria-label="Decrease target length"
                  disabled={(comp.preferred_page_length || 1) <= 1}
                  onClick={() =>
                    savePreferences({
                      preferred_page_length: (comp.preferred_page_length || 1) - 1,
                      date_format: comp.date_format || "long",
                      template_style: comp.template_style || "classic",
                      skill_row_max: comp.skill_row_max || 4,
                      section_sort_modes: comp.section_sort_modes || {},
                    })
                  }
                >
                  −
                </button>
                <output aria-live="polite">
                  {comp.preferred_page_length || 1}
                </output>
                <button
                  type="button"
                  aria-label="Increase target length"
                  disabled={(comp.preferred_page_length || 1) >= 10}
                  onClick={() =>
                    savePreferences({
                      preferred_page_length: (comp.preferred_page_length || 1) + 1,
                      date_format: comp.date_format || "long",
                      template_style: comp.template_style || "classic",
                      skill_row_max: comp.skill_row_max || 4,
                      section_sort_modes: comp.section_sort_modes || {},
                    })
                  }
                >
                  +
                </button>
              </div>
            </div>
            <div className="preference-field">
              <span id="date-format-label">Date format</span>
              <OptionGrid
                label="Date format"
                columns={2}
                value={comp.date_format || "long"}
                options={[
                  { value: "year", label: "2026" },
                  { value: "numeric", label: "10/2026" },
                  { value: "short", label: "Oct 2026" },
                  { value: "long", label: "October 2026" },
                ]}
                onChange={(date_format) =>
                  savePreferences({
                    preferred_page_length: comp.preferred_page_length || 1,
                    date_format,
                    template_style: comp.template_style || "classic",
                    skill_row_max: comp.skill_row_max || 4,
                    section_sort_modes: comp.section_sort_modes || {},
                  })
                }
              />
              <small className="coaching-note">{dateFormatCoaching}</small>
            </div>
            <div className="preference-field">
              <span id="template-style-label">Template</span>
              <OptionGrid
                label="Template"
                columns={3}
                value={comp.template_style || "classic"}
                options={[
                  { value: "classic", label: "Default" },
                  { value: "sheets", label: "Ruled Serif" },
                  { value: "harvard", label: "Harvard Style" },
                  { value: "dais", label: "Times Serif" },
                  { value: "sre", label: "Skill Table" },
                ]}
                onChange={(template_style) =>
                  savePreferences({
                    preferred_page_length: comp.preferred_page_length || 1,
                    date_format: comp.date_format || "long",
                    template_style,
                    skill_row_max: comp.skill_row_max || 4,
                    section_sort_modes: comp.section_sort_modes || {},
                  })
                }
              />
            </div>
          </fieldset>
        </div>
      )}
    </section>
  );
}

function SaveDefaultSetDialog({
  sets,
  initialName,
  close,
  save,
}: {
  sets: any[];
  initialName: string;
  close: () => void;
  save: (name: string, replaceId: string) => Promise<void>;
}) {
  const [name, setName] = useState(initialName);
  const [replaceId, setReplaceId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <ModalShell title="Save as defaults set" close={close}>
      <p>
        Add the records and wording on this resume to a defaults set. New
        resumes can start from it, and you can fine-tune it in the Library.
      </p>
      <label>
        Defaults set
        <select
          value={replaceId}
          onChange={(event) => setReplaceId(event.target.value)}
        >
          <option value="">Create a new set</option>
          {sets.map((item) => (
            <option key={item.id} value={item.id}>
              Replace “{item.name}”
            </option>
          ))}
        </select>
      </label>
      {!replaceId && (
        <label>
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="form-actions">
        <button onClick={close}>Cancel</button>
        <button
          className="primary"
          disabled={busy || (!replaceId && !name.trim())}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await save(name.trim(), replaceId);
            } catch (reason: any) {
              setError(reason.message || "Could not save this defaults set");
              setBusy(false);
            }
          }}
        >
          Save
        </button>
      </div>
    </ModalShell>
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
  openJobs,
  onImport,
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
        <nav className="rail-nav">
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
          <button className="rail-link" onClick={openJobs}>
            <AppIcon name="jobs" />
            Jobs
          </button>
          <button
            className={section === "bin" ? "rail-link active" : "rail-link"}
            onClick={() => setSection("bin")}
          >
            <AppIcon name="bin" />
            Bin
          </button>
        </nav>
      </aside>
      <section className="home-content">
        {error && (
          <div role="alert" className="error home-error">
            {error}
            <button onClick={dismissError}>Dismiss</button>
          </div>
        )}
        <header className="home-hero">
          <img src={primaryLogo} alt="" className="home-logo" />
          <h1 className="sr-only">Resume Engine</h1>
          <p>A Really Useful tool for completing job applications</p>
          {section === "active" && (
            <div className="hero-actions">
              <button
                className="primary-action"
                onClick={() => createResume()}
              >
                + New Resume
              </button>
              <button type="button" onClick={onImport}>
                Import Existing Resume
              </button>
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
                <svg
                  viewBox="0 0 16 16"
                  width="1em"
                  height="1em"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  focusable="false"
                  style={{ verticalAlign: "-0.18em" }}
                >
                  <rect x="3" y="1.4" width="10" height="13.2" rx="1.7" />
                  <path d="M3 5.2h10" />
                  <path d="M5.2 8h5.6M5.2 10.6h4" />
                </svg>{" "}
                Card View
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

// Matches the phone breakpoint in resume-print.css where the top bar moves
// Library, Undo and Redo into its overflow menu.
const COMPACT_TOPBAR_QUERY = "(max-width: 560px)";
function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const list = matchMedia(query);
    const onChange = () => setMatches(list.matches);
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);
  return matches;
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
const LIBRARY_ENTRY_KEYS = [
  "education",
  "projects",
  "work_experience",
  "leadership",
];
const BULLET_TARGET: Record<
  string,
  { section: string; parent: string; library: string }
> = {
  education: {
    section: "education",
    parent: "education_item",
    library: "education",
  },
  projects: {
    section: "projects",
    parent: "content_item",
    library: "projects",
  },
  work_experience: {
    section: "work_experience",
    parent: "content_item",
    library: "experience",
  },
  leadership: {
    section: "leadership",
    parent: "content_item",
    library: "leadership",
  },
};
function moveIndex<T>(items: T[], from: number, to: number) {
  const next = items.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}
function orderedSkills(items: any[], toolOrder: Record<string, number>) {
  return items
    .filter((skill) => !skill.archived_at)
    .slice()
    .sort((a, b) => {
      const left = toolOrder[String(a.id)];
      const right = toolOrder[String(b.id)];
      if (left != null && right != null && left !== right) return left - right;
      if (left != null && right == null) return -1;
      if (left == null && right != null) return 1;
      return (a.sort_order || 0) - (b.sort_order || 0);
    });
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
function compareChronological(a: any, b: any) {
  const left = chronologicalKey(a),
    right = chronologicalKey(b);
  for (let i = 0; i < Math.max(left.length, right.length); i++) {
    if (left[i] < right[i]) return -1;
    if (left[i] > right[i]) return 1;
  }
  return 0;
}
const DATED_ENTRY_KEYS = ["projects", "work_experience", "leadership"];
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
  reloadLibrary,
  chooseInterest,
  chooseLibraryItem,
  openLibraryFromEditor,
  aiJobs,
  aiJobId,
  setAiJobId,
  fit,
  openShrink,
}: any) {
  const [compositionItems, setCompositionItems] = useState<any[]>([]),
    [placements, setPlacements] = useState<any[]>([]),
    [hiddenToolIds, setHiddenToolIds] = useState<string[]>([]),
    [toolOrder, setToolOrder] = useState<Record<string, number>>({}),
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
    [libraryDialog, setLibraryDialog] = useState<any>(null),
    [menu, setMenu] = useState<string | null>(null),
    [announcement, setAnnouncement] = useState(""),
    [orderedRows, setOrderedRows] = useState<any[] | null>(null),
    [sectionDrag, setSectionDrag] = useState<{
      key: string;
      from: number;
      over: number;
    } | null>(null);
  const reload = () =>
    Promise.all([
      api<any[]>(`/api/compositions/${comp.id}/items`),
      api<any[]>(`/api/compositions/${comp.id}/bullet-placements`),
      api<any[]>(`/api/compositions/${comp.id}/hidden-tools`),
      api<any[]>(`/api/compositions/${comp.id}/tool-order`),
    ])
      .then(([i, b, hidden, order]) => {
        setCompositionItems(i);
        setPlacements(b);
        setHiddenToolIds(hidden.map((row) => String(row.tool_id)));
        setToolOrder(
          Object.fromEntries(
            order.map((row) => [String(row.tool_id), row.sort_order]),
          ),
        );
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
  const shownRows = orderedRows ?? rows;
  const rowsRef = useRef(shownRows);
  const revisionRef = useRef(comp.revision);
  const saveQueue = useRef(Promise.resolve());
  const orderGen = useRef(0);
  const sectionDragRef = useRef<{
    pointerId: number;
    key: string;
    from: number;
    over: number;
    startY: number;
    moved: boolean;
  } | null>(null);
  const reorderRowsRef = useRef<
    (listId: string, from: number, to: number) => void
  >(() => {});
  const rowDrag = useRowDrag((listId, from, to) =>
    reorderRowsRef.current(listId, from, to),
  );
  rowsRef.current = shownRows;
  if (comp.revision > revisionRef.current) revisionRef.current = comp.revision;
  useEffect(
    () => () => document.body.classList.remove("section-reordering"),
    [],
  );
  const save = (next: any[]) => {
    const gen = ++orderGen.current;
    setOrderedRows(next.map((x) => [...x]));
    saveQueue.current = saveQueue.current
      .catch(() => undefined)
      .then(async () => {
        setStatus("Saving…");
        const section_order = next.map((x) =>
          x[3] ? x[0] : `hidden:${x[0]}`,
        );
        const saved = await api<any>(`/api/compositions/${comp.id}/sections`, {
          method: "PUT",
          body: JSON.stringify({
            revision: revisionRef.current,
            section_order,
            interest_layout: comp.resume.interest_layout || "compact",
            included_builtin: next
              .filter((x) => !x[0].startsWith("custom:") && x[3])
              .map((x) => x[0]),
            included_custom: next
              .filter((x) => x[0].startsWith("custom:") && x[3])
              .map((x) => x[0].slice(7)),
          }),
        });
        revisionRef.current = saved.revision;
        setComp(saved);
        if (gen === orderGen.current) setOrderedRows(null);
        setStatus("Saved");
      })
      .catch((e: any) => {
        if (gen === orderGen.current) setOrderedRows(null);
        setError(e.message);
        setStatus(e.status === 409 ? "Conflict" : "Save failed");
      });
  };
  const moveSection = (i: number, d: number) => {
    const list = rowsRef.current;
    const t = i + d;
    if (t < 0 || t >= list.length) return;
    const n = list.map((x) => [...x]);
    [n[i], n[t]] = [n[t], n[i]];
    save(n);
    setAnnouncement(`${list[i][1]} moved to position ${t + 1} of ${list.length}.`);
  };
  const sectionDropIndex = (clientY: number, from: number) => {
    const cards = [
      ...document.querySelectorAll<HTMLElement>(
        ".resume-sections article.section-card[data-section-key]",
      ),
    ];
    let target = from;
    for (let i = 0; i < cards.length; i++) {
      if (i === from) continue;
      const rect = cards[i].getBoundingClientRect();
      const mid = rect.top + Math.min(rect.height, 52) / 2;
      if (i < from && clientY < mid) return i;
      if (i > from && clientY > mid) target = i;
    }
    return target;
  };
  const startSectionDrag = (
    event: React.PointerEvent<HTMLButtonElement>,
    key: string,
    index: number,
  ) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    sectionDragRef.current = {
      pointerId: event.pointerId,
      key,
      from: index,
      over: index,
      startY: event.clientY,
      moved: false,
    };
  };
  const moveSectionDrag = (event: React.PointerEvent<HTMLButtonElement>) => {
    const session = sectionDragRef.current;
    if (!session || event.pointerId !== session.pointerId) return;
    if (!session.moved && Math.abs(event.clientY - session.startY) < 4) return;
    session.moved = true;
    document.body.classList.add("section-reordering");
    const scroller = document.querySelector<HTMLElement>(".editor");
    if (scroller) {
      const bounds = scroller.getBoundingClientRect();
      if (event.clientY > bounds.bottom - 48) scroller.scrollTop += 14;
      else if (event.clientY < bounds.top + 48) scroller.scrollTop -= 14;
    }
    const over = sectionDropIndex(event.clientY, session.from);
    if (over === session.over && sectionDrag?.key === session.key) return;
    session.over = over;
    setSectionDrag({ key: session.key, from: session.from, over });
  };
  const endSectionDrag = (event: React.PointerEvent<HTMLButtonElement>) => {
    const session = sectionDragRef.current;
    if (!session || event.pointerId !== session.pointerId) return;
    sectionDragRef.current = null;
    document.body.classList.remove("section-reordering");
    setSectionDrag(null);
    if (!session.moved || session.over === session.from) return;
    const list = rowsRef.current.map((x) => [...x]);
    const [item] = list.splice(session.from, 1);
    list.splice(session.over, 0, item);
    save(list);
    setAnnouncement(
      `${item[1]} moved to position ${session.over + 1} of ${list.length}.`,
    );
  };
  const storageSection = (key: string) =>
    key === "tools" ? "tool_groups" : key;
  const sources: any = {
    education: lib.education,
    tool_groups: lib.tool_groups,
    projects: lib.projects,
    work_experience: lib.employment,
    leadership: lib.leadership,
    personal_interests: lib.interests,
  };
  const sectionEntries = (key: string) => {
    const stored = storageSection(key);
    let a = compositionItems
      .filter((x) => x.section === stored)
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((x) =>
        (sources[stored] || []).find(
          (r: any) => String(r.id) === String(x.item_id),
        ),
      )
      .filter(Boolean);
    if (
      (comp.section_sort_modes?.[key] || "automatic") === "automatic" &&
      DATED_ENTRY_KEYS.includes(key)
    )
      a = [...a].sort(compareChronological);
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
  const persistOrder = (task: () => Promise<any>) => {
    saveQueue.current = saveQueue.current
      .catch(() => undefined)
      .then(async () => {
        setStatus("Saving…");
        const saved = await task();
        revisionRef.current = saved.revision;
        setComp(saved);
        setStatus("Saved");
      })
      .catch((e: any) => {
        setError(e.message);
        setStatus(e.status === 409 ? "Conflict" : "Save failed");
        reload();
      });
  };
  const moveItems = (section: string, items: any[], from: number, to: number) => {
    if (to < 0 || to >= items.length || from === to) return;
    const next = moveIndex(items, from, to);
    const ids = next.map((item) => item.id);
    setCompositionItems((current) => [
      ...current.filter((row) => row.section !== section),
      ...ids.map((id, index) => ({ section, item_id: id, sort_order: index })),
    ]);
    persistOrder(() =>
      api(`/api/compositions/${comp.id}/items/order`, {
        method: "PUT",
        body: JSON.stringify({
          revision: revisionRef.current,
          section,
          ids,
        }),
      }),
    );
    setAnnouncement(
      `${ENTRY_LABELS[section] || "Item"} moved to position ${to + 1} of ${next.length}.`,
    );
  };
  const writeEntryOrder = (
    key: string,
    ids: string[],
    mode: "automatic" | "manual",
  ) => {
    const storedIds = compositionItems
      .filter((row) => row.section === key)
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((row) => String(row.item_id));
    const orderChanged =
      ids.length !== storedIds.length ||
      ids.some((id, index) => id !== storedIds[index]);
    const modeChanged =
      (comp.section_sort_modes?.[key] || "automatic") !== mode;
    if (!orderChanged && !modeChanged) return;
    const modes = { ...(comp.section_sort_modes || {}), [key]: mode };
    if (orderChanged) {
      setCompositionItems((current) => [
        ...current.filter((row) => row.section !== key),
        ...ids.map((id, index) => ({
          section: key,
          item_id: id,
          sort_order: index,
        })),
      ]);
    }
    if (modeChanged) {
      setComp((current: Comp | null) =>
        current ? { ...current, section_sort_modes: modes } : current,
      );
    }
    const preferences = {
      preferred_page_length: comp.preferred_page_length || 1,
      date_format: comp.date_format || "long",
      template_style: comp.template_style || "classic",
      skill_row_max: comp.skill_row_max || 4,
      section_sort_modes: modes,
    };
    if (!orderChanged) {
      saveCompositionPreferences(preferences);
      return;
    }
    persistOrder(async () => {
      const ordered = await api<any>(`/api/compositions/${comp.id}/items/order`, {
        method: "PUT",
        body: JSON.stringify({
          revision: revisionRef.current,
          section: key,
          ids,
        }),
      });
      revisionRef.current = ordered.revision;
      if ((ordered.section_sort_modes?.[key] || "automatic") === mode)
        return ordered;
      return api(`/api/compositions/${comp.id}/preferences`, {
        method: "PUT",
        body: JSON.stringify({
          revision: ordered.revision,
          preferred_page_length: ordered.preferred_page_length || 1,
          date_format: ordered.date_format || "long",
          template_style: ordered.template_style || "classic",
          skill_row_max: ordered.skill_row_max || 4,
          section_sort_modes: {
            ...(ordered.section_sort_modes || {}),
            [key]: mode,
          },
        }),
      });
    });
  };
  const moveBullets = (rows: any[], from: number, to: number) => {
    if (to < 0 || to >= rows.length || from === to) return;
    const next = moveIndex(rows, from, to);
    const sample = next[0];
    setPlacements((current) => {
      const moving = new Set(next.map((row) => String(row.id)));
      return [
        ...current.filter((row) => !moving.has(String(row.id))),
        ...next.map((row, index) => ({ ...row, sort_order: index })),
      ];
    });
    persistOrder(() =>
      api(`/api/compositions/${comp.id}/bullet-placements/order`, {
        method: "PUT",
        body: JSON.stringify({
          revision: revisionRef.current,
          destination_section: sample.destination_section,
          destination_parent_type: sample.destination_parent_type,
          destination_parent_id: sample.destination_parent_id,
          ids: next.map((row) => row.id),
        }),
      }),
    );
    setAnnouncement(`Bullet moved to position ${to + 1} of ${next.length}.`);
  };
  const moveSkills = (groupId: string, skills: any[], from: number, to: number) => {
    if (to < 0 || to >= skills.length || from === to) return;
    const next = moveIndex(skills, from, to);
    setToolOrder((current) => {
      const copy = { ...current };
      next.forEach((skill, index) => {
        copy[String(skill.id)] = index;
      });
      return copy;
    });
    persistOrder(() =>
      api(`/api/compositions/${comp.id}/tool-groups/${groupId}/tools/order`, {
        method: "PUT",
        body: JSON.stringify({
          revision: revisionRef.current,
          ids: next.map((skill) => skill.id),
        }),
      }),
    );
    setAnnouncement(`Skill moved to position ${to + 1} of ${next.length}.`);
  };
  const parentPlacements = (parentId: string) =>
    placements
      .filter((row) => String(row.destination_parent_id) === String(parentId))
      .sort((a, b) => a.sort_order - b.sort_order);
  reorderRowsRef.current = (listId, from, to) => {
    if (listId.startsWith("entries:")) {
      const key = listId.slice("entries:".length);
      const rows = sectionEntries(key);
      if (to < 0 || to >= rows.length || from === to) return;
      writeEntryOrder(
        key,
        moveIndex(rows, from, to).map((row) => String(row.id)),
        "manual",
      );
      setAnnouncement(
        `${ENTRY_LABELS[key] || "Item"} moved to position ${to + 1} of ${rows.length}.`,
      );
      return;
    }
    if (listId === "interests") {
      moveItems("personal_interests", sectionEntries("personal_interests"), from, to);
      return;
    }
    if (listId === "skill-groups") {
      moveItems("tool_groups", sectionEntries("tools"), from, to);
      return;
    }
    if (listId.startsWith("skills:")) {
      const groupId = listId.slice("skills:".length);
      const group = (lib.tool_groups || []).find(
        (item: any) => String(item.id) === groupId,
      );
      moveSkills(groupId, orderedSkills(group?.items || [], toolOrder), from, to);
      return;
    }
    if (listId.startsWith("bullets:")) {
      moveBullets(parentPlacements(listId.slice("bullets:".length)), from, to);
    }
  };
  const refreshResume = async () => {
    await reloadLibrary();
    setComp(await api(`/api/compositions/${comp.id}`));
    setStatus("Saved");
  };
  const selectStoredItem = async (
    section: string,
    itemId: string,
    included: boolean,
    revision: number,
  ) => {
    if (section === "personal_interests") {
      return api<any>(`/api/compositions/${comp.id}/interests`, {
        method: "PUT",
        body: JSON.stringify({ revision, interest_id: itemId, included }),
      });
    }
    const endpoint =
      section === "tool_groups"
        ? "tool-groups"
        : section === "education"
          ? "education"
          : `historical/${section}`;
    return api<any>(`/api/compositions/${comp.id}/${endpoint}`, {
      method: "PUT",
      body: JSON.stringify({ revision, item_id: itemId, included }),
    });
  };
  const libraryActions = {
    pickProfile: async (profileId: string) => {
      setComp(
        await api(`/api/compositions/${comp.id}/profile`, {
          method: "PUT",
          body: JSON.stringify({ revision: comp.revision, profile_id: profileId }),
        }),
      );
      setStatus("Saved");
    },
    createProfile: async (draft: any) => {
      const row = await api<any>("/api/library/profiles", {
        method: "POST",
        body: JSON.stringify(draft),
      });
      await reloadLibrary();
      setComp(
        await api(`/api/compositions/${comp.id}/profile`, {
          method: "PUT",
          body: JSON.stringify({ revision: comp.revision, profile_id: row.id }),
        }),
      );
      setStatus("Saved");
    },
    saveProfile: async (id: string, draft: any) => {
      const mode = await chooseSaveMode("entry");
      if (!mode) return false;
      setComp(
        await api(`/api/compositions/${comp.id}/profiles/${id}/save`, {
          method: "POST",
          body: JSON.stringify({
            revision: comp.revision,
            mode,
            fields: profilePayload(draft),
          }),
        }),
      );
      await reloadLibrary();
      setStatus("Saved");
    },
    pickSummary: async (summaryId: string | null) => {
      setComp(
        await api(`/api/compositions/${comp.id}/summary`, {
          method: "PUT",
          body: JSON.stringify({
            revision: comp.revision,
            summary_variant_id: summaryId,
          }),
        }),
      );
      setStatus("Saved");
    },
    createSummary: async (draft: any) => {
      const row = await api<any>("/api/library/summaries", {
        method: "POST",
        body: JSON.stringify(draft),
      });
      await reloadLibrary();
      setComp(
        await api(`/api/compositions/${comp.id}/summary`, {
          method: "PUT",
          body: JSON.stringify({
            revision: comp.revision,
            summary_variant_id: row.id,
          }),
        }),
      );
      setStatus("Saved");
    },
    saveSummary: async (id: string, draft: any) => {
      const mode = await chooseSaveMode("entry");
      if (!mode) return false;
      setComp(
        await api(`/api/compositions/${comp.id}/summaries/${id}/save`, {
          method: "POST",
          body: JSON.stringify({
            revision: comp.revision,
            mode,
            name: (draft.name || "").trim(),
            body: (draft.body || "").trim(),
          }),
        }),
      );
      await reloadLibrary();
      setStatus("Saved");
    },
    pickEntry: async (section: string, item: any, replaceId?: string) => {
      if (!replaceId) {
        setComp(
          await selectStoredItem(section, item.id, true, comp.revision),
        );
        setStatus("Saved");
        return;
      }
      const ordered = sectionEntries(
        section === "tool_groups" ? "tools" : section,
      ).map((entry: any) => String(entry.id));
      let next = await selectStoredItem(section, item.id, true, comp.revision);
      next = await selectStoredItem(section, replaceId, false, next.revision);
      setComp(next);
      const ids = ordered.map((entryId) =>
        entryId === String(replaceId) ? String(item.id) : entryId,
      );
      setComp(
        await api(`/api/compositions/${comp.id}/items/order`, {
          method: "PUT",
          body: JSON.stringify({ revision: next.revision, section, ids }),
        }),
      );
      setStatus("Saved");
    },
    createEntry: async (section: string, draft: any) => {
      const fields = { ...draft };
      for (const key of [
        "kind",
        "bullets",
        "id",
        "archived_at",
        "sort_order",
        "items",
        "created_at",
        "updated_at",
      ])
        delete fields[key];
      if (section === "education" && !(fields.institution || "").trim())
        throw new Error("Institution is required.");
      if (section === "projects" && !(fields.name || "").trim())
        throw new Error("Project name is required.");
      if (
        (section === "work_experience" || section === "leadership") &&
        (!(fields.organization || "").trim() || !(fields.title || "").trim())
      )
        throw new Error("Organization and title are required.");
      if (section === "tool_groups" && !(fields.name || "").trim())
        throw new Error("Group name is required.");
      setComp(
        await api(`/api/compositions/${comp.id}/entries/create`, {
          method: "POST",
          body: JSON.stringify({
            revision: comp.revision,
            section,
            fields,
          }),
        }),
      );
      await reloadLibrary();
      setStatus("Saved");
    },
    saveEntry: async (section: string, id: string, draft: any) => {
      if (section === "tool_groups") {
        await api(`/api/library/tool-groups/${id}`, {
          method: "PUT",
          body: JSON.stringify({ name: (draft.name || "").trim() }),
        });
        await refreshResume();
        return;
      }
      const mode = await chooseSaveMode("entry");
      if (!mode) return false;
      const fields =
        section === "education"
          ? {
              institution: (draft.institution || "").trim(),
              college_school: draft.college_school || "",
              location: draft.location || "",
              degree_type: draft.degree_type || "",
              degree_major: draft.degree_major || "",
              graduation_year: draft.graduation_year ?? null,
              graduation_month: draft.graduation_month ?? null,
              display_date: draft.display_date || "",
            }
          : {
              name: draft.name || null,
              subtitle: draft.subtitle || null,
              organization: draft.organization || null,
              location: draft.location || "",
              title: draft.title || null,
              date_label: draft.date_label || "",
              start_year: draft.start_year ?? null,
              start_month: draft.start_month ?? null,
              end_year: draft.end_year ?? null,
              end_month: draft.end_month ?? null,
              is_current: !!draft.is_current,
            };
      setComp(
        await api(`/api/compositions/${comp.id}/entries/${id}/save`, {
          method: "POST",
          body: JSON.stringify({
            revision: comp.revision,
            mode,
            section,
            fields,
          }),
        }),
      );
      await reloadLibrary();
      setStatus("Saved");
    },
    pickBullet: async (
      section: string,
      parentId: string,
      choice: any,
      placementId?: string,
    ) => {
      const target = BULLET_TARGET[section];
      const next = placementId
        ? await api(
            `/api/compositions/${comp.id}/bullet-placements/${placementId}`,
            {
              method: "PUT",
              body: JSON.stringify({
                revision: comp.revision,
                bullet_id: choice.bullet_id,
                variant_id: choice.variant_id,
              }),
            },
          )
        : await api(`/api/compositions/${comp.id}/bullet-placements`, {
            method: "POST",
            body: JSON.stringify({
              revision: comp.revision,
              bullet_id: choice.bullet_id,
              variant_id: choice.variant_id,
              destination_section: target.section,
              destination_parent_type: target.parent,
              destination_parent_id: parentId,
            }),
          });
      setComp(next);
      await reloadLibrary();
      setStatus("Saved");
    },
    createBullet: async (section: string, parentId: string, body: string) => {
      const target = BULLET_TARGET[section];
      setComp(
        await api(`/api/compositions/${comp.id}/bullet-placements/create`, {
          method: "POST",
          body: JSON.stringify({
            revision: comp.revision,
            body,
            variant_name: "Default",
            library_section: target.library,
            destination_section: target.section,
            destination_parent_type: target.parent,
            destination_parent_id: parentId,
          }),
        }),
      );
      await reloadLibrary();
      setStatus("Saved");
    },
    saveBullet: async (placement: any, body: string) => {
      const mode = await chooseSaveMode("bullet");
      if (!mode) return false;
      setComp(
        await api(
          `/api/compositions/${comp.id}/bullet-placements/${placement.id}/save`,
          {
            method: "POST",
            body: JSON.stringify({ revision: comp.revision, mode, body }),
          },
        ),
      );
      await reloadLibrary();
      setStatus("Saved");
    },
    pickInterest: async (item: any, replaceId?: string) => {
      if (!replaceId) {
        setComp(
          await selectStoredItem(
            "personal_interests",
            item.id,
            true,
            comp.revision,
          ),
        );
        setStatus("Saved");
        return;
      }
      const ordered = sectionEntries("personal_interests").map((entry: any) =>
        String(entry.id),
      );
      let next = await selectStoredItem(
        "personal_interests",
        item.id,
        true,
        comp.revision,
      );
      next = await selectStoredItem(
        "personal_interests",
        replaceId,
        false,
        next.revision,
      );
      setComp(next);
      const ids = ordered.map((entryId) =>
        entryId === String(replaceId) ? String(item.id) : entryId,
      );
      setComp(
        await api(`/api/compositions/${comp.id}/items/order`, {
          method: "PUT",
          body: JSON.stringify({
            revision: next.revision,
            section: "personal_interests",
            ids,
          }),
        }),
      );
      setStatus("Saved");
    },
    createInterest: async (draft: any) => {
      if (!(draft.body || "").trim())
        throw new Error("Interest text is required.");
      setComp(
        await api(`/api/compositions/${comp.id}/entries/create`, {
          method: "POST",
          body: JSON.stringify({
            revision: comp.revision,
            section: "personal_interests",
            fields: { body: draft.body.trim() },
          }),
        }),
      );
      await reloadLibrary();
      setStatus("Saved");
    },
    saveInterest: async (id: string, draft: any) => {
      if (!(draft.body || "").trim())
        throw new Error("Interest text is required.");
      await api(`/api/library/interests/${id}`, {
        method: "PUT",
        body: JSON.stringify({ body: draft.body.trim() }),
      });
      await refreshResume();
    },
    addSkill: async (groupId: string, name: string) => {
      await api("/api/library/tools", {
        method: "POST",
        body: JSON.stringify({ name, group_id: groupId }),
      });
      await refreshResume();
    },
    renameSkill: async (groupId: string, id: string, name: string) => {
      if (!name.trim()) throw new Error("Skill name is required.");
      await api(`/api/library/tools/${id}`, {
        method: "PUT",
        body: JSON.stringify({ name: name.trim(), group_id: groupId }),
      });
      await refreshResume();
    },
    archiveSkill: async (id: string) => {
      await api(`/api/library/tools/${id}/archive`, { method: "POST" });
      await refreshResume();
    },
  };
  const aiContext: AiJobContext = {
    compositionId: comp.id,
    revision: comp.revision,
    jobs: aiJobs || [],
    jobId: aiJobId || "",
    setJobId: setAiJobId || (() => {}),
    onApplied: async (next: any) => {
      setComp(next);
      await reloadLibrary();
      setStatus("Saved");
    },
    openReview: () => setLibraryDialog({ mode: "ai-review" }),
    fit,
    lineCount: (placement: any) => fit?.bulletLines?.[placementLineId(placements, placement)] || null,
    openShrink: openShrink
      ? () => {
          setLibraryDialog(null);
          openShrink();
        }
      : undefined,
  };
  const parentBullets = (section: string, parentId: string) => {
    const source =
      section === "education"
        ? lib.education
        : section === "projects"
          ? lib.projects
          : section === "leadership"
            ? lib.leadership
            : lib.employment;
    return (
      (source || []).find((item: any) => String(item.id) === String(parentId))
        ?.bullets || []
    );
  };
  const toggleSkill = async (toolId: string, included: boolean) => {
    const previous = hiddenToolIds;
    setHiddenToolIds(
      included
        ? previous.filter((id) => id !== String(toolId))
        : [...previous, String(toolId)],
    );
    try {
      setStatus("Saving…");
      setComp(
        await api(`/api/compositions/${comp.id}/tools/${toolId}`, {
          method: "PUT",
          body: JSON.stringify({ revision: comp.revision, included }),
        }),
      );
      setStatus("Saved");
    } catch (e: any) {
      setHiddenToolIds(previous);
      setError(e.message);
      setStatus(e.status === 409 ? "Conflict" : "Save failed");
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
      manual = (comp.section_sort_modes?.[key] || "automatic") === "manual",
      entryListId = `entries:${key}`,
      entryDrag = DATED_ENTRY_KEYS.includes(key) && items.length > 1;
    return (
      <article
        className={`entry-card${entryDrag ? ` ${dragRowClass(rowDrag.drag, entryListId, i)}` : ""}`.trim()}
        data-drag-list={entryDrag ? entryListId : undefined}
        data-drag-index={entryDrag ? i : undefined}
        key={id}
      >
        <div className="entry-card-header">
          <button
            type="button"
            className={`item-drag-handle${DATED_ENTRY_KEYS.includes(key) ? " drag-handle" : ""}`}
            aria-label={`Drag ${title}`}
            onPointerDown={(event) =>
              entryDrag && rowDrag.start(event, entryListId, i)
            }
            onPointerMove={rowDrag.move}
            onPointerUp={rowDrag.end}
            onPointerCancel={rowDrag.end}
            onKeyDown={(event) => {
              if (!entryDrag) return;
              if (event.key === "ArrowUp" && i > 0) {
                event.preventDefault();
                rowDrag.nudge(entryListId, i, i - 1);
              }
              if (event.key === "ArrowDown" && i < items.length - 1) {
                event.preventDefault();
                rowDrag.nudge(entryListId, i, i + 1);
              }
            }}
          >
            ⠿
          </button>
          <span className="section-icon">
            <AppIcon name={editorSectionIcon(key)} />
          </span>
          <div>
            <div className="entry-title-row">
              <strong>{title}</strong>
              {key === "work_experience" && (
                <SectionHelp
                  name={title}
                  notes={[
                    ...(i === 0 ? firstJobCoaching : [laterJobCoaching]),
                    ...(i > 0 && i === items.length - 1 ? [lastJobCoaching] : []),
                    ...bulletCoaching,
                  ]}
                />
              )}
            </div>
            <div className="entry-meta">
              <span>{subtitle}</span>
              <span>{x.location}</span>
              <span>{x.date_label || x.display_date}</span>
            </div>
          </div>
          {LIBRARY_ENTRY_KEYS.includes(key) ? (
            <span className="record-actions">
              <RecordActions
                name={title}
                onEdit={() =>
                  setLibraryDialog({ mode: "edit-entry", section: key, item: x })
                }
                onReplace={() =>
                  setLibraryDialog({
                    mode: "pick-entry",
                    section: key,
                    replaceId: id,
                  })
                }
                onRemove={() => chooseLibraryItem(storageSection(key), x, false)}
              />
            </span>
          ) : (
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
                      !manual
                        ? "Choose Manual order to move entries."
                        : undefined
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
          )}
          <button
            className="section-chevron"
            aria-expanded={expanded}
            onClick={() =>
              setEntryExpanded({ ...entryExpanded, [id]: !expanded })
            }
          >
            <span aria-hidden="true">
              <AppIcon name="chevron" />
            </span>
          </button>
        </div>
        {expanded && (
          <div className="entry-card-body">
            <h4>Bullet Points</h4>
            <div className="bullet-list">
              {bullets.map((b: any, bulletIndex: number) => (
                <div
                  className={`bullet-row ${bullets.length > 1 ? "has-drag" : ""} ${dragRowClass(rowDrag.drag, `bullets:${id}`, bulletIndex)}`}
                  data-drag-list={bullets.length > 1 ? `bullets:${id}` : undefined}
                  data-drag-index={bullets.length > 1 ? bulletIndex : undefined}
                  key={b.id}
                >
                  {bullets.length > 1 && (
                    <DragHandle
                      label={(b.wording_snapshot || "bullet").slice(0, 80)}
                      listId={`bullets:${id}`}
                      index={bulletIndex}
                      count={bullets.length}
                      drag={rowDrag}
                    />
                  )}
                  <span>
                    {b.wording_snapshot}
                    {b.active_variant_count > 1 && (
                      <small> · {b.variant_name}</small>
                    )}
                    {b.usage_status !== "current" && (
                      <span className="bullet-status">{b.usage_status}</span>
                    )}
                  </span>
                  {LIBRARY_ENTRY_KEYS.includes(key) ? (
                    <RecordActions
                      name="bullet"
                      onEdit={() =>
                        setLibraryDialog({ mode: "edit-bullet", placement: b })
                      }
                      onReplace={() =>
                        setLibraryDialog({
                          mode: "pick-bullet",
                          section: key,
                          parentId: id,
                          placementId: b.id,
                          placement: b,
                          currentBulletId: b.bullet_id,
                        })
                      }
                      onRemove={async () => {
                        if (
                          !(await confirmDialog({
                            title: "Remove bullet",
                            message: "Remove this bullet from this resume?",
                            confirmLabel: "Remove",
                            danger: true,
                          }))
                        )
                          return;
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
                      }}
                    />
                  ) : (
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
                  )}
                </div>
              ))}
            </div>
            {LIBRARY_ENTRY_KEYS.includes(key) ? (
              <button
                type="button"
                className="add-bullet-inline"
                onClick={() =>
                  setLibraryDialog({
                    mode: "pick-bullet",
                    section: key,
                    parentId: id,
                  })
                }
              >
                + Add Bullet
              </button>
            ) : (
              <AddBulletButton />
            )}
          </div>
        )}
      </article>
    );
  };
  const setSkillRows = (next: number) => {
    const rows = Math.min(20, Math.max(1, next));
    if (rows === (comp.skill_row_max || 4)) return;
    saveCompositionPreferences({
      preferred_page_length: comp.preferred_page_length || 1,
      date_format: comp.date_format || "long",
      template_style: comp.template_style || "classic",
      skill_row_max: rows,
      section_sort_modes: comp.section_sort_modes || {},
    });
  };
  const content = (key: string) => {
    if (key === "summary") {
      const summary = (lib.summary_variants || []).find(
        (item: any) => item.id === comp.summary_variant_id,
      );
      return (
        <div className="entry-card library-record">
          {summary ? (
            <>
              <div>
                <strong>{summary.name}</strong>
                <p className="summary-preview">{summary.body}</p>
              </div>
              <RecordActions
                name={summary.name}
                onEdit={() =>
                  setLibraryDialog({ mode: "edit-summary", item: summary })
                }
                onReplace={() => setLibraryDialog({ mode: "pick-summary" })}
              />
            </>
          ) : (
            <>
              <p className="library-note">No summary on this resume.</p>
              <RecordActions
                name="summary"
                onReplace={() => setLibraryDialog({ mode: "pick-summary" })}
              />
            </>
          )}
        </div>
      );
    }
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
    const stored = storageSection(key);
    const items = sectionEntries(key);
    const skillRows = comp.skill_row_max || 4;
    if (key === "tools") {
      return (
        <div className="entry-list">
          {(comp.template_style || "classic") === "sre" && (
            <div className="target-length-field">
              <span id="skill-rows-label">Skill rows</span>
              <div className="skill-rows-controls">
                <div
                  className="target-length"
                  role="group"
                  aria-labelledby="skill-rows-label"
                >
                  <button
                    type="button"
                    aria-label="Decrease skill rows"
                    disabled={skillRows <= 1}
                    onClick={() => setSkillRows(skillRows - 1)}
                  >
                    −
                  </button>
                  <output aria-live="polite">{skillRows}</output>
                  <button
                    type="button"
                    aria-label="Increase skill rows"
                    disabled={skillRows >= 20}
                    onClick={() => setSkillRows(skillRows + 1)}
                  >
                    +
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setSkillRows(autoFitSkillRows(comp.resume?.tool_groups))
                  }
                >
                  Auto-fit
                </button>
              </div>
              <small className="coaching-note">
                Skills fill down this many rows, then wrap into the next column.
              </small>
            </div>
          )}
          {items.map((group: any, groupIndex: number) => {
            const skills = orderedSkills(group.items || [], toolOrder);
            const expansionKey = `skill:${group.id}`;
            const expanded = entryExpanded[expansionKey] ?? true;
            return (
            <article
              className={`entry-card skill-group-card ${dragRowClass(rowDrag.drag, "skill-groups", groupIndex)}`}
              data-drag-list={items.length > 1 ? "skill-groups" : undefined}
              data-drag-index={items.length > 1 ? groupIndex : undefined}
              key={group.id}
            >
              <div className={`library-record ${items.length > 1 ? "has-drag" : ""}`}>
                {items.length > 1 && (
                  <DragHandle
                    label={group.name}
                    listId="skill-groups"
                    index={groupIndex}
                    count={items.length}
                    drag={rowDrag}
                  />
                )}
                <strong>{group.name}</strong>
                <span className="skill-group-tools">
                  <RecordActions
                    name={group.name}
                    onEdit={() =>
                      setLibraryDialog({
                        mode: "edit-entry",
                        section: "tool_groups",
                        item: group,
                      })
                    }
                    onReplace={() =>
                      setLibraryDialog({
                        mode: "pick-entry",
                        section: "tool_groups",
                        replaceId: group.id,
                      })
                    }
                    onRemove={() => chooseLibraryItem("tool_groups", group, false)}
                  />
                  <button
                    type="button"
                    className="section-chevron"
                    aria-expanded={expanded}
                    aria-label={`${expanded ? "Collapse" : "Expand"} ${group.name}`}
                    onClick={() =>
                      setEntryExpanded({
                        ...entryExpanded,
                        [expansionKey]: !expanded,
                      })
                    }
                  >
                    <span aria-hidden="true">
                      <AppIcon name="chevron" />
                    </span>
                  </button>
                </span>
              </div>
              {expanded && (
              <div className="entry-card-body">
                {skills.map((skill: any, skillIndex: number) => (
                    <div
                      className={`skill-line ${skills.length > 1 ? "has-drag" : ""} ${dragRowClass(rowDrag.drag, `skills:${group.id}`, skillIndex)}`}
                      data-drag-list={
                        skills.length > 1 ? `skills:${group.id}` : undefined
                      }
                      data-drag-index={skills.length > 1 ? skillIndex : undefined}
                      key={skill.id}
                    >
                      {skills.length > 1 && (
                        <DragHandle
                          label={skill.name}
                          listId={`skills:${group.id}`}
                          index={skillIndex}
                          count={skills.length}
                          drag={rowDrag}
                        />
                      )}
                      <label>
                        <input
                          type="checkbox"
                          checked={!hiddenToolIds.includes(String(skill.id))}
                          aria-label={`Show ${skill.name} on this resume`}
                          onChange={(event) =>
                            toggleSkill(skill.id, event.target.checked)
                          }
                        />
                        {skill.name}
                      </label>
                    </div>
                  ))}
                <button
                  type="button"
                  className="add-bullet-inline"
                  onClick={() =>
                    setLibraryDialog({
                      mode: "manage-skills",
                      groupId: group.id,
                    })
                  }
                >
                  Manage skills
                </button>
              </div>
              )}
            </article>
            );
          })}
          <button
            className="add-entry-button"
            onClick={() =>
              setLibraryDialog({ mode: "pick-entry", section: "tool_groups" })
            }
          >
            + Add Skill Group
          </button>
        </div>
      );
    }
    if (key === "personal_interests") {
      return (
        <div className="entry-list interest-list">
          {items.map((item: any, interestIndex: number) => (
            <div
              className={`bullet-row ${items.length > 1 ? "has-drag" : ""} ${dragRowClass(rowDrag.drag, "interests", interestIndex)}`}
              data-drag-list={items.length > 1 ? "interests" : undefined}
              data-drag-index={items.length > 1 ? interestIndex : undefined}
              key={item.id}
            >
              {items.length > 1 && (
                <DragHandle
                  label={item.body}
                  listId="interests"
                  index={interestIndex}
                  count={items.length}
                  drag={rowDrag}
                />
              )}
              <span>{item.body}</span>
              <RecordActions
                name={item.body}
                onEdit={() =>
                  setLibraryDialog({ mode: "edit-interest", item })
                }
                onReplace={() =>
                  setLibraryDialog({
                    mode: "pick-interest",
                    replaceId: item.id,
                  })
                }
                onRemove={() => chooseInterest(item, false)}
              />
            </div>
          ))}
          <button
            type="button"
            className="add-entry-button"
            onClick={() => setLibraryDialog({ mode: "pick-interest" })}
          >
            + Add Interest
          </button>
        </div>
      );
    }
    return (
      <div className="entry-list">
        {["projects", "work_experience", "leadership"].includes(key) && (
          <div className="order-mode">
            <span id={`${key}-order-label`}>Order</span>
            <div
              className="view-toggle"
              role="group"
              aria-labelledby={`${key}-order-label`}
            >
              {(
                [
                  ["automatic", "By date"],
                  ["manual", "Manual"],
                ] as const
              ).map(([mode, label]) => (
                <button
                  type="button"
                  key={mode}
                  aria-pressed={
                    (comp.section_sort_modes?.[key] || "automatic") === mode
                  }
                  onClick={() => {
                    if ((comp.section_sort_modes?.[key] || "automatic") === mode)
                      return;
                    if (mode === "automatic") {
                      const ids = [...items]
                        .sort(compareChronological)
                        .map((row) => String(row.id));
                      const shown = items.map((row) => String(row.id));
                      if (ids.some((id, index) => id !== shown[index])) {
                        writeEntryOrder(key, ids, "automatic");
                        return;
                      }
                    }
                    saveCompositionPreferences({
                      preferred_page_length: comp.preferred_page_length || 1,
                      date_format: comp.date_format || "long",
                      template_style: comp.template_style || "classic",
                      skill_row_max: comp.skill_row_max || 4,
                      section_sort_modes: {
                        ...comp.section_sort_modes,
                        [key]: mode,
                      },
                    })
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
        {items.map((x: any, i: number) => card(key, x, i, items))}
        <button
          className="add-entry-button"
          onClick={() =>
            LIBRARY_ENTRY_KEYS.includes(key)
              ? setLibraryDialog({ mode: "pick-entry", section: stored })
              : setEntryDialog({
                  section: stored,
                  items: sources[stored] || [],
                  includedIds: items.map((x: any) => String(x.id)),
                })
          }
        >
          + Add {ENTRY_LABELS[stored]}
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
              Use the icons on each record to edit it, replace it from the
              library, or remove it from this resume. Drag a handle to reorder
              entries, bullets, skills, or interests on this resume.
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
      <article
        className={`section-card profile-section ${collapsed.includes("profile") ? "collapsed" : "expanded"}`}
      >
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
            <span aria-hidden="true">
              <AppIcon name="chevron" />
            </span>
          </button>
        </div>
        {!collapsed.includes("profile") && (
          <div className="section-card-body">
            {(() => {
              const profile = (lib.profiles || []).find(
                (item: any) => item.id === comp.profile_id,
              );
              return (
                <div className="entry-card library-record">
                  {profile ? (
                    <>
                      <div>
                        <strong>{profile.name}</strong>
                        <div className="entry-meta">
                          <span>{profile.label}</span>
                        </div>
                      </div>
                      <RecordActions
                        name={profile.name}
                        onEdit={() =>
                          setLibraryDialog({
                            mode: "edit-profile",
                            item: profile,
                          })
                        }
                        onReplace={() =>
                          setLibraryDialog({ mode: "pick-profile" })
                        }
                      />
                    </>
                  ) : (
                    <>
                      <p className="library-note">No profile on this resume.</p>
                      <RecordActions
                        name="profile"
                        onReplace={() =>
                          setLibraryDialog({ mode: "pick-profile" })
                        }
                      />
                    </>
                  )}
                </div>
              );
            })()}
          </div>
        )}
      </article>
      {shownRows.map((r: any, i: number) => {
        const closed = collapsed.includes(r[0]);
        const dragging = sectionDrag?.key === r[0];
        const dropClass =
          sectionDrag && sectionDrag.over !== sectionDrag.from
            ? sectionDrag.over === i && sectionDrag.over < sectionDrag.from
              ? "drop-before"
              : sectionDrag.over === i && sectionDrag.over > sectionDrag.from
                ? "drop-after"
                : ""
            : "";
        return (
          <article
            className={`section-card ${closed ? "collapsed" : "expanded"} ${dragging ? "is-dragging" : ""} ${dropClass}`}
            data-section-key={r[0]}
            key={r[0]}
          >
            <div className="section-card-header">
              <button
                type="button"
                className="drag-handle"
                aria-label={`Move ${r[1]}`}
                onPointerDown={(e) => startSectionDrag(e, r[0], i)}
                onPointerMove={moveSectionDrag}
                onPointerUp={endSectionDrag}
                onPointerCancel={endSectionDrag}
                onKeyDown={(e) => {
                  if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
                  e.preventDefault();
                  moveSection(i, e.key === "ArrowUp" ? -1 : 1);
                }}
              >
                ⠿
              </button>
              <span className="section-icon">
                <AppIcon name={editorSectionIcon(r[0])} />
              </span>
              <span className="section-title-row">
                <strong>{r[1]}</strong>
                {sectionCoaching[r[0]] && (
                  <SectionHelp name={r[1]} notes={sectionCoaching[r[0]]} />
                )}
              </span>
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
                    const n = shownRows.map((x) => [...x]);
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
                <span aria-hidden="true">
                  <AppIcon name="chevron" />
                </span>
              </button>
            </div>
            {!closed && (
              <div className="section-card-body">{content(r[0])}</div>
            )}
          </article>
        );
      })}
      {libraryDialog && (
        <EditorLibraryDialogs
          dialog={libraryDialog}
          close={() => setLibraryDialog(null)}
          lib={lib}
          includedIds={(section) =>
            sectionEntries(section === "tool_groups" ? "tools" : section).map(
              (item: any) => String(item.id),
            )
          }
          parentBullets={parentBullets}
          placedBulletIds={
            new Set(placements.map((row) => String(row.bullet_id)))
          }
          actions={libraryActions}
          ai={aiContext}
        />
      )}
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

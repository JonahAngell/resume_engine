import React, { useEffect, useRef, useState } from "react";
import type { Fit } from "./FitIndicator";
import type { MatchMark } from "./matchMarks";
import type { PopoverAnchor } from "./match/MarkPopover";

export type PreviewHighlight = { marks: MatchMark[]; activeIds: string[] };
export type PreviewMarkClick = { matchIds: string[]; lineId: string; anchor: PopoverAnchor };
const emptyHighlight: PreviewHighlight = { marks: [], activeIds: [] };

export default function ResumePreview({
  compositionId,
  revision,
  revisionId,
  preferredPageCount,
  onFit,
  currentPage,
  highlight = emptyHighlight,
  onHighlightHover,
  onMarkClick,
  draft,
}: {
  compositionId: string;
  revision: number;
  revisionId?: string | null;
  preferredPageCount: number;
  onFit: (x: Fit) => void;
  currentPage: number;
  highlight?: PreviewHighlight;
  onHighlightHover?: (ids: string[]) => void;
  onMarkClick?: (click: PreviewMarkClick) => void;
  /** Unsaved template settings: the resume is rendered with them instead of its own look. */
  draft?: { baseStyle: string; settings: unknown } | null;
}) {
  const [html, setHtml] = useState(""),
    seq = useRef(0),
    frame = useRef<HTMLIFrameElement>(null),
    measured = useRef<Fit | null>(null),
    highlightRef = useRef(highlight);
  highlightRef.current = highlight;
  const postMarks = () => {
    frame.current?.contentWindow?.postMessage(
      { type: "resume-highlight", marks: highlightRef.current.marks },
      "*",
    );
  };
  const postActive = () => {
    frame.current?.contentWindow?.postMessage(
      { type: "resume-highlight-focus", activeIds: highlightRef.current.activeIds },
      "*",
    );
  };
  const draftKey = draft ? JSON.stringify(draft) : "";
  useEffect(() => {
    const id = ++seq.current,
      url = draft
        ? "/api/templates/preview"
        : revisionId
          ? `/api/compositions/${compositionId}/revisions/${revisionId}/render`
          : `/api/compositions/${compositionId}/render?revision=${revision}`;
    const request: RequestInit | undefined = draft
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ composition_id: compositionId, base_style: draft.baseStyle, settings: draft.settings }),
        }
      : undefined;
    fetch(url, request)
      .then(async (r) => {
        if (!r.ok) {
          const detail = (await r.json().catch(() => ({}))).detail;
          throw new Error(detail || "Preview failed");
        }
        return r.text();
      })
      .then((t) => {
        if (id === seq.current) setHtml(t);
      })
      .catch((e) =>
        onFit({ fits: false, state: "measurement-error", message: e.message }),
      );
    // draftKey stands in for draft, which is a new object on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compositionId, revision, revisionId, draftKey]);
  useEffect(() => {
    const fn = (e: MessageEvent) => {
      if (e.source !== frame.current?.contentWindow) return;
      if (e.data?.type === "resume-highlight-hover") {
        const id = String(e.data.id || "");
        onHighlightHover?.(id ? [id] : []);
        return;
      }
      if (e.data?.type === "resume-mark-click") {
        const frameEl = frame.current;
        const rect = e.data.rect || {};
        if (!frameEl) return;
        // The preview is scaled with a CSS transform, so map frame coordinates through that scale.
        const box = frameEl.getBoundingClientRect();
        const scale = frameEl.offsetWidth ? box.width / frameEl.offsetWidth : 1;
        const at = (value: unknown) => (Number(value) || 0) * scale;
        onMarkClick?.({
          matchIds: (Array.isArray(e.data.matchIds) ? e.data.matchIds : []).map(String),
          lineId: String(e.data.lineId || ""),
          anchor: {
            left: box.left + at(rect.left),
            top: box.top + at(rect.top),
            right: box.left + at(rect.right),
            bottom: box.top + at(rect.bottom),
          },
        });
        return;
      }
      if (e.data?.type !== "resume-pages") return;
      postMarks();
      postActive();
      const actual = e.data.actual_page_count || 1;
      const next: Fit = {
        fits: e.data.state === "measured" && actual === preferredPageCount,
        actualPageCount: actual,
        preferredPageCount,
        state: e.data.state,
        pages: e.data.pages,
        message: e.data.message,
        bulletLines: e.data.bullet_lines || {},
        itemLines: e.data.item_lines || {},
        charsPerLine: Number(e.data.chars_per_line) || 0,
        pageLines: Array.isArray(e.data.page_lines) ? e.data.page_lines : [],
      };
      measured.current = next;
      onFit(next);
    };
    addEventListener("message", fn);
    return () => removeEventListener("message", fn);
  }, [onFit, onHighlightHover, onMarkClick, preferredPageCount]);
  useEffect(() => {
    const last = measured.current;
    if (!last?.actualPageCount) return;
    onFit({
      ...last,
      preferredPageCount,
      fits: last.state === "measured" && last.actualPageCount === preferredPageCount,
    });
  }, [onFit, preferredPageCount]);
  useEffect(() => {
    frame.current?.contentWindow?.postMessage(
      { type: "resume-show-page", pageIndex: currentPage - 1 },
      "*",
    );
  }, [currentPage, html]);
  const marksKey = JSON.stringify(highlight.marks);
  const activeKey = highlight.activeIds.join("\n");
  useEffect(() => {
    postMarks();
    postActive();
  }, [marksKey, html]);
  useEffect(() => {
    postActive();
  }, [activeKey]);
  return (
    <iframe
      ref={frame}
      title="Live resume preview"
      className="preview"
      srcDoc={html}
      sandbox="allow-scripts"
    />
  );
}

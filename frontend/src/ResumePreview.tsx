import React, { useEffect, useRef, useState } from "react";
import type { Fit } from "./FitIndicator";
import type { LineAction, MatchMark } from "./matchMarks";

export type PreviewHighlight = { marks: MatchMark[]; activeIds: string[] };
export type PreviewSuggest = { lineId: string; matchIds: string[]; action: LineAction };
const emptyHighlight: PreviewHighlight = { marks: [], activeIds: [] };

export default function ResumePreview({
  compositionId,
  revision,
  revisionId,
  preferredPageCount,
  onFit,
  currentPage,
  highlight = emptyHighlight,
  onHighlightPage,
  onHighlightHover,
  onSuggest,
}: {
  compositionId: string;
  revision: number;
  revisionId?: string | null;
  preferredPageCount: number;
  onFit: (x: Fit) => void;
  currentPage: number;
  highlight?: PreviewHighlight;
  onHighlightPage?: (page: number) => void;
  onHighlightHover?: (ids: string[]) => void;
  onSuggest?: (request: PreviewSuggest) => void;
}) {
  const [html, setHtml] = useState(""),
    seq = useRef(0),
    frame = useRef<HTMLIFrameElement>(null),
    measured = useRef<Fit | null>(null),
    highlightRef = useRef(highlight),
    fromFrame = useRef(false);
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
  useEffect(() => {
    const id = ++seq.current,
      url = revisionId
        ? `/api/compositions/${compositionId}/revisions/${revisionId}/render`
        : `/api/compositions/${compositionId}/render?revision=${revision}`;
    fetch(url)
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
  }, [compositionId, revision, revisionId]);
  useEffect(() => {
    const fn = (e: MessageEvent) => {
      if (e.source !== frame.current?.contentWindow) return;
      if (e.data?.type === "resume-highlight-hover") {
        const id = String(e.data.id || "");
        fromFrame.current = Boolean(id);
        onHighlightHover?.(id ? [id] : []);
        return;
      }
      if (e.data?.type === "resume-highlight-anchor") {
        if (fromFrame.current) {
          fromFrame.current = false;
          return;
        }
        const frameEl = frame.current;
        const pane = frameEl?.closest<HTMLElement>(".stage");
        const offset = Number(e.data.top);
        if (!frameEl || !pane || !Number.isFinite(offset)) return;
        const top = frameEl.getBoundingClientRect().top + offset;
        const paneRect = pane.getBoundingClientRect();
        if (top < paneRect.top + 24 || top > paneRect.bottom - 48) {
          pane.scrollBy({ top: top - paneRect.top - 72 });
        }
        return;
      }
      if (e.data?.type === "resume-suggest") {
        const action = e.data.action === "rewrite" ? "rewrite" : "add_skill";
        const lineId = String(e.data.lineId || "");
        if (lineId)
          onSuggest?.({
            lineId,
            matchIds: (Array.isArray(e.data.matchIds) ? e.data.matchIds : []).map(String),
            action,
          });
        return;
      }
      if (e.data?.type === "resume-highlight-page") {
        const page = Number(e.data.pageIndex) + 1;
        if (page >= 1) onHighlightPage?.(page);
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
      };
      measured.current = next;
      onFit(next);
    };
    addEventListener("message", fn);
    return () => removeEventListener("message", fn);
  }, [onFit, onHighlightHover, onHighlightPage, onSuggest, preferredPageCount]);
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
    />
  );
}

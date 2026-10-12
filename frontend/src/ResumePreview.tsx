import React, { useEffect, useRef, useState } from "react";
import type { Fit } from "./FitIndicator";
export default function ResumePreview({
  compositionId,
  revision,
  revisionId,
  preferredPageCount,
  onFit,
  currentPage,
  highlight = { terms: [], lines: [], excerpts: [] },
  onHighlightPage,
}: {
  compositionId: string;
  revision: number;
  revisionId?: string | null;
  preferredPageCount: number;
  onFit: (x: Fit) => void;
  currentPage: number;
  highlight?: { terms: string[]; lines: string[]; excerpts: string[] };
  onHighlightPage?: (page: number) => void;
}) {
  const [html, setHtml] = useState(""),
    seq = useRef(0),
    frame = useRef<HTMLIFrameElement>(null),
    measured = useRef<Fit | null>(null),
    highlightRef = useRef(highlight);
  highlightRef.current = highlight;
  const postHighlight = () => {
    const current = highlightRef.current;
    frame.current?.contentWindow?.postMessage(
      {
        type: "resume-highlight",
        terms: current.terms,
        lines: current.lines,
        excerpts: current.excerpts,
      },
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
          // #region agent log
          fetch(
            "http://127.0.0.1:7353/ingest/d7c1cc8b-c0a3-49b7-960e-6eca5743ef25",
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-Debug-Session-Id": "1b8194",
              },
              body: JSON.stringify({
                sessionId: "1b8194",
                runId: "pre-fix",
                hypothesisId: "C",
                location: "ResumePreview.tsx:render",
                message: "preview error detail",
                data: {
                  url,
                  detailType: Array.isArray(detail) ? "array" : typeof detail,
                  detailLength: Array.isArray(detail) ? detail.length : null,
                  stringified: String(detail ?? "").slice(0, 240),
                },
                timestamp: Date.now(),
              }),
            },
          ).catch(() => {});
          // #endregion
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
      if (e.data?.type === "resume-highlight-page") {
        const page = Number(e.data.pageIndex) + 1;
        if (page >= 1) onHighlightPage?.(page);
        return;
      }
      if (e.data?.type !== "resume-pages") return;
      postHighlight();
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
  }, [onFit, onHighlightPage, preferredPageCount]);
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
  useEffect(() => {
    postHighlight();
  }, [highlight, html]);
  return (
    <iframe
      ref={frame}
      title="Live resume preview"
      className="preview"
      srcDoc={html}
    />
  );
}

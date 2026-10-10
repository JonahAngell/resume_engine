import React, { useEffect, useRef, useState } from "react";
import type { Fit } from "./FitIndicator";
export default function ResumePreview({
  compositionId,
  revision,
  revisionId,
  preferredPageCount,
  onFit,
  currentPage,
}: {
  compositionId: string;
  revision: number;
  revisionId?: string | null;
  preferredPageCount: number;
  onFit: (x: Fit) => void;
  currentPage: number;
}) {
  const [html, setHtml] = useState(""),
    seq = useRef(0),
    frame = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    const id = ++seq.current,
      url = revisionId
        ? `/api/compositions/${compositionId}/revisions/${revisionId}/render`
        : `/api/compositions/${compositionId}/render?revision=${revision}`;
    fetch(url)
      .then(async (r) => {
        if (!r.ok)
          throw new Error(
            (await r.json().catch(() => ({}))).detail || "Preview failed",
          );
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
      if (
        e.source !== frame.current?.contentWindow ||
        e.data?.type !== "resume-pages"
      )
        return;
      const actual = e.data.actual_page_count || 1;
      onFit({
        fits: e.data.state === "measured" && actual <= preferredPageCount,
        actualPageCount: actual,
        preferredPageCount,
        state: e.data.state,
        pages: e.data.pages,
        message: e.data.message,
      });
    };
    addEventListener("message", fn);
    return () => removeEventListener("message", fn);
  }, [onFit, preferredPageCount]);
  useEffect(() => {
    frame.current?.contentWindow?.postMessage(
      { type: "resume-show-page", pageIndex: currentPage - 1 },
      "*",
    );
  }, [currentPage, html]);
  return (
    <iframe
      ref={frame}
      title="Live resume preview"
      className="preview"
      srcDoc={html}
    />
  );
}

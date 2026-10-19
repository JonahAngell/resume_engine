import React from "react";
export type Fit = {
  fits: boolean;
  actualPageCount?: number;
  preferredPageCount?: number;
  state?: string;
  pages?: any[];
  message?: string;
  /** Rendered lines per bullet, keyed by the preview's `{parentId}-bullet-{index}` id. */
  bulletLines?: Record<string, number>;
  /** Rendered lines per entry, keyed by item id. */
  itemLines?: Record<string, number>;
  /** Approximate characters that fit on one bullet line. */
  charsPerLine?: number;
  /** Lines of content on each page. */
  pageLines?: number[];
};

/** Lines of content past the target page count, or 0 when the resume fits. */
export function linesOver(fit: Fit | null) {
  if (!fit?.pageLines || !fit.preferredPageCount) return 0;
  return fit.pageLines.slice(fit.preferredPageCount).reduce((sum, n) => sum + n, 0);
}
export default function FitIndicator({
  fit,
  compact = false,
}: {
  fit: Fit | null;
  compact?: boolean;
}) {
  if (!fit)
    return (
      <div className={`fit pending ${compact ? "compact" : ""}`} role="status">
        ⏳ Measuring…
      </div>
    );
  if (fit.state === "measurement-error")
    return (
      <div className={`fit bad ${compact ? "compact" : ""}`} role="alert">
        ⚠ {compact ? "Couldn’t measure" : "Couldn’t measure the resume."}
      </div>
    );
  const a = fit.actualPageCount || 1,
    p = fit.preferredPageCount || 1,
    pages = (n: number) => `${n} ${n === 1 ? "page" : "pages"}`,
    label = fit.fits
      ? `Matches target length (${pages(a)}).`
      : a > p
        ? `Exceeds target length by ${pages(a - p)}. Export is blocked.`
        : `Shorter than target length (${a} of ${pages(p)}). Export is blocked.`;
  return (
    <div
      className={`fit ${fit.fits ? "ok" : "bad"} ${compact ? "compact" : ""}`}
      role="status"
      aria-label={label}
    >
      {fit.fits ? "✓" : "⚠"}{" "}
      {compact
        ? fit.fits
          ? `Matches ${p} ${p === 1 ? "page" : "pages"}`
          : `${a} of ${p} pages`
        : label}
    </div>
  );
}

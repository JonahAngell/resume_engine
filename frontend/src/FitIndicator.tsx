import React from "react";
export type Fit = {
  fits: boolean;
  actualPageCount?: number;
  preferredPageCount?: number;
  state?: string;
  pages?: any[];
  message?: string;
};
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
    label = fit.fits
      ? `Fits preferred length (${a} of ${p} ${p === 1 ? "page" : "pages"}).`
      : `Exceeds preferred length by ${Math.max(1, a - p)} ${a - p === 1 ? "page" : "pages"}. Export is blocked.`;
  return (
    <div
      className={`fit ${fit.fits ? "ok" : "bad"} ${compact ? "compact" : ""}`}
      role="status"
      aria-label={label}
    >
      {fit.fits ? "✓" : "⚠"}{" "}
      {compact
        ? fit.fits
          ? `Fits ${p} ${p === 1 ? "page" : "pages"}`
          : `${a} of ${p} pages`
        : label}
    </div>
  );
}

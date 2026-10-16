import React from "react";

/** A small circular gauge for 0–100 scores. */
export default function ScoreRing({
  value,
  label,
  size = 76,
}: {
  value: number;
  label: string;
  size?: number;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  const radius = 15.5;
  const circumference = 2 * Math.PI * radius;
  const tone = clamped >= 75 ? "good" : clamped >= 55 ? "fair" : "low";
  return (
    <div className={`score-ring tone-${tone}`} style={{ width: size, height: size }} role="img" aria-label={`${label}: ${clamped} out of 100`}>
      <svg viewBox="0 0 36 36" aria-hidden="true">
        <circle className="score-ring-track" cx="18" cy="18" r={radius} />
        <circle
          className="score-ring-value"
          cx="18"
          cy="18"
          r={radius}
          strokeDasharray={`${(clamped / 100) * circumference} ${circumference}`}
        />
      </svg>
      <strong>{clamped}</strong>
    </div>
  );
}

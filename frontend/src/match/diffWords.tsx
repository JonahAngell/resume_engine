import React from "react";

/** Words in `proposed` that are not in `original`, for a light diff highlight. One span, so grid parents keep it inline. */
export function diffWords(original: string, proposed: string) {
  const pool = new Map<string, number>();
  for (const word of original.toLowerCase().match(/[\w'-]+/g) || []) pool.set(word, (pool.get(word) || 0) + 1);
  const parts = proposed.split(/(\s+)/).map((part, index) => {
    const key = (part.toLowerCase().match(/[\w'-]+/) || [""])[0];
    if (!key) return <React.Fragment key={index}>{part}</React.Fragment>;
    const left = pool.get(key) || 0;
    if (left > 0) {
      pool.set(key, left - 1);
      return <React.Fragment key={index}>{part}</React.Fragment>;
    }
    return (
      <ins key={index} className="diff-add">
        {part}
      </ins>
    );
  });
  return <span>{parts}</span>;
}

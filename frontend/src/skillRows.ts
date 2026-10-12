/** Item count for a skill group, ignoring blank names. */
function skillItemCount(group: { items?: unknown[] } | null | undefined): number {
  return (group?.items || []).filter((item) => {
    const text = typeof item === "string" ? item : (item as { name?: string })?.name || "";
    return String(text).trim().length > 0;
  }).length;
}

/**
 * Pick a row count that packs each skill group down the column, then across.
 * Prefers a filled table whose width and height are close, so a group of 4
 * stays one column and a longer group wraps beside it.
 */
export function autoFitSkillRows(groups: { items?: unknown[] }[] | null | undefined): number {
  const counts = (groups || []).map(skillItemCount).filter((count) => count > 0);
  if (!counts.length) return 4;
  const total = counts.reduce((sum, count) => sum + count, 0);
  const limit = Math.min(20, Math.max(...counts));
  let best = Math.min(4, limit);
  let bestScore = Infinity;
  for (let rows = 1; rows <= limit; rows++) {
    const columns = counts.reduce((sum, count) => sum + Math.ceil(count / rows), 0);
    const height = Math.max(...counts.map((count) => Math.min(count, rows)));
    const waste = columns * height - total;
    const score = waste * 100 + Math.abs(columns - height) * 10 + height;
    if (score < bestScore) {
      bestScore = score;
      best = rows;
    }
  }
  return best;
}

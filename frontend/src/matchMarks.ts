import type { RequirementRow, VariantTarget } from "./match/types";

export type LineAction = "add_skill" | "rewrite";
/** A suggested line: its preview id, its text (used when the id is not in the preview), and what the chip offers. */
export type LineTarget = { line: string; excerpt: string; action: LineAction };

export type MatchMark = {
  id: string;
  kind: "match" | "suggestion";
  terms: string[];
  lineIds: string[];
  excerpts: string[];
  /** Suggested lines in the preview: a rewrite or Add to Skills. */
  targets?: LineTarget[];
  /** What the item popover shows when this highlight is clicked. */
  items?: MarkItem[];
};

export type MarkItem = {
  keyword: string;
  group: string;
  status: "matched" | "suggested";
  manual: boolean;
  requirement: string;
  category: string;
  rewrites: VariantTarget[];
  addSkill: boolean;
  /** Offer Work into resume: a missing keyword that isn't Skills-only. */
  workIn: boolean;
};

export type CompareJob = {
  id: string;
  title: string;
  company: string;
  role: string;
  body: string;
};

function mergeTargets(left: LineTarget[] = [], right: LineTarget[] = []) {
  const merged = new Map(left.map((item) => [item.line, item]));
  for (const item of right) {
    const current = merged.get(item.line);
    // A rewrite on a line wins: Add to Skills is always also reachable from the panel.
    merged.set(item.line, current?.action === "rewrite" ? current : item);
  }
  return [...merged.values()];
}
function mergeItems(left: MarkItem[] = [], right: MarkItem[] = []) {
  const merged = [...left];
  for (const item of right) {
    if (!merged.some((x) => x.requirement === item.requirement && x.keyword === item.keyword)) merged.push(item);
  }
  return merged;
}

export function matchMarkId(term: string) {
  const key = term.trim().toLowerCase();
  return key ? `kw:${key}` : "";
}

function unique(values: string[]) {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}

function addMark(map: Map<string, MatchMark>, mark: MatchMark) {
  const current = map.get(mark.id);
  if (!current) {
    map.set(mark.id, {
      id: mark.id,
      kind: mark.kind,
      terms: unique(mark.terms),
      lineIds: mark.kind === "match" ? [] : unique(mark.lineIds),
      excerpts: mark.kind === "match" ? [] : unique(mark.excerpts),
      targets: mark.kind === "match" ? [] : mergeTargets([], mark.targets),
      items: mergeItems([], mark.items),
    });
    return;
  }
  current.terms = unique([...current.terms, ...mark.terms]);
  current.items = mergeItems(current.items, mark.items);
  if (current.kind === "match" || mark.kind === "match") {
    current.kind = "match";
    current.lineIds = [];
    current.excerpts = [];
    current.targets = [];
    return;
  }
  current.lineIds = unique([...current.lineIds, ...mark.lineIds]);
  current.excerpts = unique([...current.excerpts, ...mark.excerpts]);
  current.targets = mergeTargets(current.targets, mark.targets);
}

function rowItem(row: RequirementRow, keyword: string, found: boolean, workIn = false): MarkItem {
  const key = keyword.trim().toLowerCase();
  const mine = (row.suggestions || []).filter((item) => item.keyword.trim().toLowerCase() === key);
  const category = row.category || row.kind || "";
  return {
    keyword,
    group: row.group,
    status: found ? "matched" : "suggested",
    manual: !!row.manual,
    requirement: row.text,
    category,
    rewrites: found
      ? []
      : mine
          .filter((item) => item.action === "rewrite" && item.placement_id)
          .map((item) => ({
            placementId: item.placement_id as string,
            lineId: item.line_id,
            excerpt: item.bullet_excerpt,
            keyword: item.keyword,
            requirement: row.text,
            category,
            incorporate: true,
          })),
    addSkill: !found && mine.some((item) => item.action === "add_skill"),
    workIn: !found && workIn,
  };
}

export function buildMatchMarks(rows: RequirementRow[]): MatchMark[] {
  const marks = new Map<string, MatchMark>();
  for (const row of rows) {
    if (row.kind === "education" || row.kind === "degree") {
      const label = (row.label || row.keywords?.[0]?.keyword || "").trim();
      const id = matchMarkId(label);
      if (!id) continue;
      const found = !!(row.matched || row.manual || row.keywords?.some((item) => item.found));
      const terms = [label];
      if (found && row.detail && !row.detail.startsWith("This resume")) {
        terms.push(...row.detail.split(",").map((part) => part.trim()));
      }
      addMark(marks, {
        id,
        kind: found ? "match" : "suggestion",
        terms,
        lineIds: [],
        excerpts: [],
        items: [rowItem(row, label, found)],
      });
      continue;
    }
    for (const keyword of row.keywords || []) {
      const term = keyword.keyword.trim();
      const id = matchMarkId(term);
      if (!id) continue;
      const found = keyword.found || !!row.manual;
      // The user said they lack it: no yellow highlight. It still counts as missing in scores.
      if (!found && keyword.skipped) continue;
      const suggestions = (row.suggestions || []).filter(
        (item) => item.keyword.trim().toLowerCase() === term.toLowerCase(),
      );
      addMark(marks, {
        id,
        kind: found ? "match" : "suggestion",
        terms: [term],
        lineIds: found ? [] : suggestions.map((item) => item.line_id || ""),
        excerpts: found ? [] : suggestions.map((item) => item.bullet_excerpt || ""),
        targets: found
          ? []
          : suggestions
              .filter((item) => item.line_id && item.action)
              .map((item) => ({
                line: item.line_id as string,
                excerpt: item.bullet_excerpt || "",
                action: item.action as LineAction,
              })),
        items: [rowItem(row, term, found, !keyword.skill)],
      });
    }
  }
  return [...marks.values()];
}

export function activeIdsForTerms(terms: string[]) {
  return unique(terms.map(matchMarkId));
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export type HighlightSegment = { text: string; mark?: MatchMark };

export function highlightSegments(text: string, marks: MatchMark[]): HighlightSegment[] {
  const ordered = marks
    .flatMap((mark) => mark.terms.map((term) => ({ term: term.trim(), mark })))
    .filter((item) => item.term)
    .sort((left, right) => right.term.length - left.term.length);
  const seen = new Set<string>();
  const pieces: string[] = [];
  const byTerm = new Map<string, MatchMark>();
  for (const item of ordered) {
    const key = item.term.toLowerCase();
    const preferred = matchMarkId(item.term) === item.mark.id;
    if (!byTerm.has(key) || preferred) byTerm.set(key, item.mark);
    if (seen.has(key)) continue;
    seen.add(key);
    pieces.push(`(?<!\\w)${escapeRegExp(item.term)}(?!\\w)`);
  }
  if (!pieces.length || !text) return [{ text }];
  const pattern = new RegExp(pieces.join("|"), "gi");
  const segments: HighlightSegment[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text))) {
    if (match.index > cursor) segments.push({ text: text.slice(cursor, match.index) });
    const mark = byTerm.get(match[0].toLowerCase());
    segments.push({ text: match[0], mark });
    cursor = match.index + match[0].length;
    if (match.index === pattern.lastIndex) pattern.lastIndex += 1;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor) });
  return segments.length ? segments : [{ text }];
}

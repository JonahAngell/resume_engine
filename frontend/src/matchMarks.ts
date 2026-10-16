export type MatchMark = {
  id: string;
  kind: "match" | "suggestion";
  terms: string[];
  lineIds: string[];
  excerpts: string[];
};

export type CompareJob = {
  id: string;
  title: string;
  company: string;
  role: string;
  body: string;
};

type MarkKeyword = { keyword: string; found: boolean };
type MarkSuggestion = { keyword: string; bullet_excerpt?: string; line_id?: string };
type MarkRow = {
  kind?: string;
  label?: string;
  detail?: string;
  matched?: boolean;
  manual?: boolean;
  keywords?: MarkKeyword[];
  suggestions?: MarkSuggestion[];
};

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
    });
    return;
  }
  current.terms = unique([...current.terms, ...mark.terms]);
  if (current.kind === "match" || mark.kind === "match") {
    current.kind = "match";
    current.lineIds = [];
    current.excerpts = [];
    return;
  }
  current.lineIds = unique([...current.lineIds, ...mark.lineIds]);
  current.excerpts = unique([...current.excerpts, ...mark.excerpts]);
}

export function buildMatchMarks(rows: MarkRow[]): MatchMark[] {
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
      addMark(marks, { id, kind: found ? "match" : "suggestion", terms, lineIds: [], excerpts: [] });
      continue;
    }
    for (const keyword of row.keywords || []) {
      const term = keyword.keyword.trim();
      const id = matchMarkId(term);
      if (!id) continue;
      const found = keyword.found || !!row.manual;
      const suggestions = (row.suggestions || []).filter(
        (item) => item.keyword.trim().toLowerCase() === term.toLowerCase(),
      );
      addMark(marks, {
        id,
        kind: found ? "match" : "suggestion",
        terms: [term],
        lineIds: found ? [] : suggestions.map((item) => item.line_id || ""),
        excerpts: found ? [] : suggestions.map((item) => item.bullet_excerpt || ""),
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

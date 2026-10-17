import React from "react";

const PLACEHOLDER = /\[[^[\]\n]{1,30}\]/g;

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** True while a draft still has a [placeholder] the user must replace. */
export function hasPlaceholder(text: string) {
  return new RegExp(PLACEHOLDER.source).test(text);
}

/** Draft text with the job keyword and any [placeholders] marked. */
export default function KeywordText({ text, keyword }: { text: string; keyword: string }) {
  const parts = [PLACEHOLDER.source];
  if (keyword.trim()) parts.unshift(`(?<!\\w)${escapeRegExp(keyword.trim())}(?!\\w)`);
  const pattern = new RegExp(parts.join("|"), "gi");
  const out: React.ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text))) {
    if (match.index > cursor) out.push(text.slice(cursor, match.index));
    const placeholder = match[0].startsWith("[");
    out.push(
      <mark key={match.index} className={placeholder ? "assist-placeholder" : "assist-keyword"}>
        {match[0]}
      </mark>,
    );
    cursor = match.index + match[0].length;
    if (match.index === pattern.lastIndex) pattern.lastIndex += 1;
  }
  if (cursor < text.length) out.push(text.slice(cursor));
  return <>{out}</>;
}

import React, { useEffect, useRef, useState } from "react";
import { activeIdsForTerms } from "../matchMarks";
import type { JobMatchState } from "./useJobMatch";
import {
  groupLabel,
  rewriteTargets,
  skillKeywords,
  type AssistRequest,
  type JobMatch,
  type RequirementKeyword,
  type RequirementRow,
} from "./types";

type Filter = "all" | "missing" | "matched";

export function rowIds(row: RequirementRow) {
  if (row.kind === "education" || row.kind === "degree" || row.category === "degree") {
    return activeIdsForTerms([row.label || ""]);
  }
  return activeIdsForTerms(row.keywords.map((item) => item.keyword));
}

function chipClass(item: Pick<RequirementKeyword, "found" | "relation">) {
  if (item.found) return "keyword-chip";
  if (item.relation === "cluster" || item.relation === "combination") return "keyword-chip related";
  return "keyword-chip missing";
}

export function rowStatus(row: RequirementRow) {
  if (row.manual) return { label: "Marked", tone: "matched" };
  if (row.matched) return { label: "Matched", tone: "matched" };
  return { label: "Suggested", tone: "suggested" };
}

export function rowKey(row: RequirementRow) {
  return `${row.group}:${row.text}`;
}

export function RowActions({
  row,
  state,
  onAssist,
  compact = false,
}: {
  row: RequirementRow;
  state: JobMatchState;
  onAssist: (request: AssistRequest) => void;
  compact?: boolean;
}) {
  if (row.matched && !row.manual) return null;
  const rewrites = row.matched ? [] : rewriteTargets(row);
  const skills = row.matched ? [] : skillKeywords(row);
  return (
    <div className="row-actions">
      {skills.map((keyword) => (
        <button key={`skill-${keyword}`} type="button" disabled={state.busy} onClick={() => onAssist({ kind: "skill", keyword })}>
          Add {keyword} to Skills
        </button>
      ))}
      {rewrites.slice(0, compact ? 1 : rewrites.length).map((target) => (
        <button
          key={`rewrite-${target.placementId}-${target.keyword}`}
          type="button"
          className="primary"
          disabled={state.busy}
          title={target.excerpt}
          onClick={() => onAssist({ kind: "rewrite", target })}
        >
          Generate AI revision{rewrites.length > 1 && !compact ? `: “${target.excerpt.slice(0, 32)}…”` : ""}
        </button>
      ))}
      {!compact && (
        <button type="button" disabled={state.busy} onClick={() => state.markRequirement(row)}>
          {row.manual ? "Clear match" : "Mark as match"}
        </button>
      )}
    </div>
  );
}

function RequirementItem({
  row,
  state,
  open,
  setOpen,
  onActive,
  onAssist,
}: {
  row: RequirementRow;
  state: JobMatchState;
  open: boolean;
  setOpen: (open: boolean) => void;
  onActive: (ids: string[]) => void;
  onAssist: (request: AssistRequest) => void;
}) {
  const status = rowStatus(row);
  const tags = row.matched ? [] : row.suggestions.filter((item) => item.bullet_id && item.keyword);
  return (
    <li
      className={`req-item tone-${status.tone} ${open ? "open" : ""}`}
      data-req-key={rowKey(row)}
      onMouseEnter={() => onActive(rowIds(row))}
      onMouseLeave={() => onActive([])}
    >
      <button type="button" className="req-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className={`status-dot tone-${status.tone}`} aria-hidden="true" />
        <span className="req-main">
          <span className="req-chips">
            {row.match_mode === "any" && row.keywords.length > 1 && <span className="qual-any">Any of</span>}
            {row.keywords.length > 0 ? (
              row.keywords.map((item) => (
                <span className={chipClass(item)} key={item.keyword} title={item.evidence?.explanation || ""}>
                  {item.keyword}
                </span>
              ))
            ) : (
              <span className="qual-label">{row.label || row.text}</span>
            )}
          </span>
          <span className="req-text">{row.text}</span>
        </span>
        <span className={`badge status-${status.tone}`}>{status.label}</span>
      </button>
      {open && (
        <div className="req-detail">
          {(row.kind === "education" || row.kind === "degree") && row.detail && <p>{row.detail}</p>}
          {row.keywords
            .filter((item) => item.evidence && item.found)
            .map((item) => (
              <p key={`ev-${item.keyword}`} className="req-evidence">
                <strong>{item.keyword}:</strong> {item.evidence?.explanation}
              </p>
            ))}
          {!row.matched &&
            row.suggestions.map((item, index) => (
              <p key={`${item.keyword}-${item.line_id || index}`} className="req-hint">
                <strong>{item.keyword}.</strong> {item.suggestion}
                {item.bullet_excerpt && <span className="req-quote"> “{item.bullet_excerpt}”</span>}
              </p>
            ))}
          <RowActions row={row} state={state} onAssist={onAssist} />
          <div className="row-actions secondary">
            {tags.map((item) => (
              <button
                key={`tag-${item.bullet_id}-${item.keyword}`}
                type="button"
                className="link-button"
                disabled={state.busy}
                onClick={() => state.addTag(item.bullet_id as string, item.keyword)}
              >
                Tag “{item.bullet_excerpt.slice(0, 28)}…” with {item.keyword}
              </button>
            ))}
            <button type="button" className="link-button danger-text" disabled={state.busy} onClick={() => state.dismissRequirement(row)}>
              Dismiss requirement
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

export default function RequirementsTab({
  match,
  state,
  focus,
  onActive,
  onAssist,
}: {
  match: JobMatch;
  state: JobMatchState;
  focus: { key: string; nonce: number } | null;
  onActive: (ids: string[]) => void;
  onAssist: (request: AssistRequest) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!focus) return;
    setFilter("all");
    setOpen((current) => ({ ...current, [focus.key]: true }));
    requestAnimationFrame(() => {
      const element = [...(list.current?.querySelectorAll<HTMLElement>("[data-req-key]") || [])].find(
        (item) => item.dataset.reqKey === focus.key,
      );
      element?.scrollIntoView({ block: "center" });
      element?.querySelector<HTMLElement>(".req-toggle")?.focus();
    });
  }, [focus?.nonce]);

  const groups: [string, RequirementRow[]][] = [
    ["required", match.required],
    ["preferred", match.preferred],
    ["responsibilities", match.responsibilities || []],
  ];
  const visible = (row: RequirementRow) =>
    filter === "all" ? true : filter === "matched" ? row.matched : !row.matched;
  const total = groups.reduce((sum, [, rows]) => sum + rows.length, 0);

  return (
    <div className="req-tab" ref={list}>
      <div className="segmented" role="group" aria-label="Filter requirements">
        {(
          [
            ["all", "All"],
            ["missing", "Suggested"],
            ["matched", "Matched"],
          ] as const
        ).map(([value, label]) => (
          <button key={value} type="button" aria-pressed={filter === value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>
            {label}
          </button>
        ))}
      </div>
      {total === 0 && <p className="empty-state">No qualifications were found in this description.</p>}
      {groups.map(([group, rows]) => {
        if (!rows.length) return null;
        const shown = rows.filter(visible);
        const matched = rows.filter((row) => row.matched).length;
        return (
          <section key={group} className="req-group" aria-label={groupLabel(group)}>
            <h3>
              <span>{group === "responsibilities" ? "Responsibilities" : groupLabel(group)}</span>
              <span className="req-count">
                {matched}/{rows.length} matched
              </span>
            </h3>
            {shown.length === 0 ? (
              <p className="empty-state small">{filter === "matched" ? "Nothing matched yet." : "All matched."}</p>
            ) : (
              <ul className="req-list">
                {shown.map((row) => (
                  <RequirementItem
                    key={rowKey(row)}
                    row={row}
                    state={state}
                    open={!!open[rowKey(row)]}
                    setOpen={(value) => setOpen((current) => ({ ...current, [rowKey(row)]: value }))}
                    onActive={onActive}
                    onAssist={onAssist}
                  />
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}

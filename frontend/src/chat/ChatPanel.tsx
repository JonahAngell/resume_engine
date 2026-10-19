import { useEffect, useId, useRef, useState } from "react";
import { api, ApiError } from "../api";
import AddSkillDialog from "../AddSkillDialog";
import ChoiceList from "../ChoiceList";
import type { JobMatchState } from "../match/useJobMatch";
import ProposalCard, { type ChatProposal, type ProposalOutcome } from "./ProposalCard";

type ChatTurn = {
  status: "ok" | "unavailable" | "rate_limited" | "invalid";
  detail: string;
  model: string;
  revision: number;
  reply: string;
  proposals: ChatProposal[];
  dropped: number;
};

type ChatEntry = {
  id: string;
  role: "user" | "assistant";
  content: string;
  proposals?: ChatProposal[];
  outcomes?: Record<string, ProposalOutcome>;
  model?: string;
  dropped?: number;
  failed?: boolean;
};

export type ChatResume = {
  id: string;
  name: string;
  revision: number;
  summary_variant_id?: string | null;
};

const HISTORY = 12;
const PLACEHOLDER = /\[[^[\]\n]{1,30}\]/;

const STARTERS_WITH_JOB = [
  "How well does my resume match this job?",
  "What are my biggest gaps for this role?",
  "Tighten my summary for this job.",
  "Which bullets should I cut, swap or reorder?",
];
const STARTERS_NO_JOB = [
  "What are the weakest bullets on this resume?",
  "Tighten my summary.",
  "Which bullets should I reorder?",
];

function storageKey(compositionId: string, jobId: string) {
  return `resume-engine-chat:${compositionId}:${jobId || "none"}`;
}

function readHistory(key: string): ChatEntry[] {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function writeHistory(key: string, entries: ChatEntry[]) {
  try {
    if (entries.length) sessionStorage.setItem(key, JSON.stringify(entries));
    else sessionStorage.removeItem(key);
  } catch {
    // Keeping the conversation across reloads is a convenience only.
  }
}

const newId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

/** Floating AI chat about the open resume and the selected job. Edits apply only on Accept. */
export default function ChatPanel({
  comp,
  jobState,
  onApplied,
}: {
  comp: ChatResume;
  jobState: JobMatchState;
  onApplied: (composition: any) => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [picking, setPicking] = useState(false);
  const [skill, setSkill] = useState<{ keyword: string; entryId: string; proposalId: string } | null>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const job = jobState.selected;
  const key = storageKey(comp.id, jobState.jobId);

  useEffect(() => {
    setEntries(readHistory(key));
    setError("");
  }, [key]);

  useEffect(() => setPicking(false), [jobState.jobId]);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [entries, sending, open]);

  const update = (next: ChatEntry[] | ((current: ChatEntry[]) => ChatEntry[])) => {
    setEntries((current) => {
      const value = typeof next === "function" ? next(current) : next;
      writeHistory(key, value);
      return value;
    });
  };

  const close = () => {
    setOpen(false);
    opener.current?.focus();
  };

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || sending) return;
    const asked: ChatEntry = { id: newId(), role: "user", content };
    const history = [...entries.filter((entry) => !entry.failed), asked]
      .slice(-HISTORY)
      .map((entry) => ({ role: entry.role, content: entry.content }));
    update((current) => [...current, asked]);
    setDraft("");
    setSending(true);
    setError("");
    try {
      const turn = await api<ChatTurn>(`/api/compositions/${comp.id}/ai-chat`, {
        method: "POST",
        body: JSON.stringify({ job_id: jobState.jobId || null, messages: history }),
      });
      const answer: ChatEntry =
        turn.status === "ok"
          ? {
              id: newId(),
              role: "assistant",
              content: turn.reply || "Here are some changes you can review.",
              proposals: turn.proposals,
              outcomes: {},
              model: turn.model,
              dropped: turn.dropped,
            }
          : { id: newId(), role: "assistant", content: turn.detail, failed: true };
      update((current) => [...current, answer]);
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setSending(false);
      input.current?.focus();
    }
  };

  const mark = (entryId: string, proposalId: string, outcome: ProposalOutcome) =>
    update((current) =>
      current.map((entry) =>
        entry.id === entryId ? { ...entry, outcomes: { ...(entry.outcomes || {}), [proposalId]: outcome } } : entry,
      ),
    );

  const accept = async (entry: ChatEntry, card: ChatProposal, text: string) => {
    if (card.kind === "add_skill") {
      setSkill({ keyword: card.keyword, entryId: entry.id, proposalId: card.id });
      return;
    }
    const base = `/api/compositions/${comp.id}`;
    const revision = comp.revision;
    const body = text.trim();
    const source = body === card.proposed.trim() ? "draft" : "edited";
    const name = `Chat edit (${job?.company || job?.role || "resume"})`.slice(0, 120);
    const post = (url: string, payload: object, method = "POST") =>
      api(url, { method, body: JSON.stringify({ revision, ...payload }) });
    setSaving(card.id);
    setError("");
    try {
      let next;
      if (card.kind === "rewrite") {
        next = await post(`${base}/bullet-placements/${card.placement_id}/ai-variants/accept`, {
          name,
          body,
          source,
          job_id: jobState.jobId || null,
          model: entry.model || "",
        });
      } else if (card.kind === "summary") {
        if (!comp.summary_variant_id) throw new Error("Choose a summary for this resume first.");
        next = await post(`${base}/summaries/${comp.summary_variant_id}/save`, {
          mode: "new",
          name: `Summary for ${job?.role || job?.title || "this resume"}`.slice(0, 120),
          body,
        });
      } else if (card.kind === "new_bullet") {
        if (PLACEHOLDER.test(body)) throw new Error("Replace the [placeholders] with your own details first.");
        next = await post(`${base}/ai-keyword-assist/accept-new`, {
          parent_id: card.parent_id,
          body,
          source,
          job_id: jobState.jobId || null,
          model: entry.model || "",
        });
      } else if (card.kind === "remove") {
        next = await api(`${base}/bullet-placements/${card.placement_id}?revision=${revision}`, { method: "DELETE" });
      } else if (card.kind === "reorder") {
        next = await post(
          `${base}/bullet-placements/order`,
          {
            destination_section: card.section,
            destination_parent_type: card.parent_type || "content_item",
            destination_parent_id: card.parent_id,
            ids: card.order,
          },
          "PUT",
        );
      } else if (card.placement_id) {
        next = await post(`${base}/bullet-placements/replace-many`, {
          items: [{ placement_id: card.placement_id, bullet_id: card.bullet_id, variant_id: card.variant_id }],
        });
      } else {
        next = await post(`${base}/bullet-placements`, {
          bullet_id: card.bullet_id,
          variant_id: card.variant_id,
          destination_section: card.section,
          destination_parent_type: "content_item",
          destination_parent_id: card.parent_id,
        });
      }
      await onApplied(next);
      mark(entry.id, card.id, "applied");
    } catch (reason: any) {
      setError(
        reason instanceof ApiError && reason.status === 409 && /changed/i.test(reason.message)
          ? "This resume changed. Ask again so the suggestion uses the latest version."
          : reason instanceof ApiError && reason.status === 404
            ? "That part of the resume is no longer there. Ask again for a fresh suggestion."
            : reason.message,
      );
    } finally {
      setSaving("");
    }
  };

  const clear = () => {
    update([]);
    setError("");
    input.current?.focus();
  };

  const starters = job ? STARTERS_WITH_JOB : STARTERS_NO_JOB;

  return (
    <>
      {!open && (
        <button ref={opener} type="button" className="chat-launcher primary" onClick={() => setOpen(true)}>
          <span aria-hidden="true">✦</span> Ask AI
        </button>
      )}
      {open && (
        <section
          ref={panel}
          className="chat-panel"
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          onKeyDown={(event) => {
            if (event.key === "Escape" && !skill) {
              event.stopPropagation();
              close();
            }
          }}
        >
          <header className="chat-head">
            <div className="chat-title">
              <h2 id={titleId}>Resume assistant</h2>
              <div className="chat-actions">
                {entries.length > 0 && (
                  <button type="button" className="link-button" onClick={clear}>
                    Clear chat
                  </button>
                )}
                <button type="button" className="icon-button" aria-label="Close assistant" onClick={close}>
                  ×
                </button>
              </div>
            </div>
            <p className="chat-context">
              <span title={comp.name}>Resume: {comp.name}</span>
              {job && !picking ? (
                <span>
                  Job: <strong title={job.title}>{job.title}</strong>{" "}
                  <button type="button" className="link-button" onClick={() => setPicking(true)}>
                    Change
                  </button>
                </span>
              ) : !picking ? (
                <span>
                  No job selected.{" "}
                  {jobState.jobs.length > 0 && (
                    <button type="button" className="link-button" onClick={() => setPicking(true)}>
                      Choose a job
                    </button>
                  )}
                </span>
              ) : null}
            </p>
            {picking && (
              <div className="chat-picker">
                <ChoiceList
                  label="Job description"
                  search="always"
                  value={jobState.jobId}
                  noMatch="No matching job descriptions."
                  options={[{ value: "", label: "No job" }, ...jobState.jobs.map((item) => ({ value: item.id, label: item.title }))]}
                  onChange={jobState.setJobId}
                />
                <button type="button" className="link-button" onClick={() => setPicking(false)}>
                  Cancel
                </button>
              </div>
            )}
          </header>
          <div ref={list} className="chat-messages" aria-live="polite">
            {entries.length === 0 && (
              <div className="chat-empty">
                <p>
                  Ask about this resume{job ? " and how it matches the selected job" : ""}. The assistant only uses your resume
                  {job ? ", your library and this one job posting" : " and your library"}. Any change it suggests waits for your Accept.
                </p>
                <div className="chat-starters">
                  {starters.map((text) => (
                    <button key={text} type="button" disabled={sending} onClick={() => send(text)}>
                      {text}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {entries.map((entry) => (
              <div key={entry.id} className={`chat-message from-${entry.role}${entry.failed ? " failed" : ""}`}>
                <p className="chat-bubble">{entry.content}</p>
                {(entry.proposals || []).length > 0 && (
                  <ul className="chat-proposals" aria-label="Suggested changes">
                    {(entry.proposals || []).map((card) => (
                      <ProposalCard
                        key={card.id}
                        card={card}
                        outcome={entry.outcomes?.[card.id]}
                        saving={saving === card.id}
                        disabled={!!saving}
                        summaryReady={!!comp.summary_variant_id}
                        onAccept={(text) => accept(entry, card, text)}
                        onDismiss={() => mark(entry.id, card.id, "dismissed")}
                      />
                    ))}
                  </ul>
                )}
                {!!entry.dropped && (
                  <p className="chat-note">
                    {entry.dropped} unsafe or invalid suggestion{entry.dropped === 1 ? " was" : "s were"} filtered out.
                  </p>
                )}
              </div>
            ))}
            {sending && (
              <div className="chat-message from-assistant">
                <p className="chat-bubble chat-typing">Thinking…</p>
              </div>
            )}
          </div>
          {error && (
            <p role="alert" className="error chat-error">
              {error}
            </p>
          )}
          <form
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              send(draft);
            }}
          >
            <label className="sr-only" htmlFor={`${titleId}-input`}>
              Message the assistant
            </label>
            <textarea
              id={`${titleId}-input`}
              ref={input}
              rows={2}
              maxLength={2000}
              value={draft}
              placeholder={job ? `Ask about this resume and ${job.role || "the job"}…` : "Ask about this resume…"}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  send(draft);
                }
              }}
            />
            <button type="submit" className="primary" disabled={sending || !draft.trim()}>
              Send
            </button>
          </form>
          <p className="chat-note chat-footnote">AI never changes the match score. Check every suggestion before you accept it.</p>
        </section>
      )}
      {skill && (
        <AddSkillDialog
          compositionId={comp.id}
          revision={comp.revision}
          keyword={skill.keyword}
          onApplied={async (next) => {
            await onApplied(next);
            mark(skill.entryId, skill.proposalId, "applied");
          }}
          close={() => setSkill(null)}
        />
      )}
    </>
  );
}

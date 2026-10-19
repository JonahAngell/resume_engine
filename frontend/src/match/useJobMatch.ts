import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { CompareJob } from "../matchMarks";
import type { JobDescription, JobMatch, KeywordReview, RequirementRow } from "./types";

/** Jobs, the selected job and its deterministic match for one resume. Shared by the dashboard and both documents. */
export function useJobMatch({
  compositionId,
  revision,
  linkedJobId,
  active,
  reloadLibrary,
}: {
  compositionId: string;
  revision: number;
  linkedJobId: string;
  active: boolean;
  reloadLibrary: () => Promise<void> | void;
}) {
  const [jobs, setJobs] = useState<JobDescription[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [jobId, setJobIdState] = useState("");
  const [match, setMatch] = useState<JobMatch | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [generation, setGeneration] = useState(0);
  const request = useRef(0);
  const manual = useRef(false);
  const selected = jobs.find((job) => job.id === jobId) || null;
  const compareJob: CompareJob | null = selected
    ? { id: selected.id, title: selected.title, company: selected.company, role: selected.role, body: selected.body }
    : null;

  useEffect(() => {
    manual.current = false;
    setJobIdState("");
    setMatch(null);
  }, [compositionId]);

  const loadJobs = useCallback(() => {
    let cancelled = false;
    api<JobDescription[]>("/api/job-descriptions")
      .then((rows) => {
        if (cancelled) return;
        setJobs(rows);
        setLoaded(true);
      })
      .catch((reason: Error) => {
        if (cancelled) return;
        setError(reason.message);
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(loadJobs, [loadJobs]);

  // A resume can be linked to a job saved after this list loaded (New from AI Recommendation).
  const reloadedFor = useRef("");
  useEffect(() => {
    if (!loaded || !linkedJobId || reloadedFor.current === linkedJobId) return;
    if (jobs.some((job) => job.id === linkedJobId)) return;
    reloadedFor.current = linkedJobId;
    return loadJobs();
  }, [loaded, linkedJobId, jobs, loadJobs]);

  useEffect(() => {
    if (manual.current || jobs.length === 0) return;
    setJobIdState(jobs.some((job) => job.id === linkedJobId) ? linkedJobId : "");
  }, [jobs, compositionId, linkedJobId]);

  useEffect(() => {
    setMatch(null);
  }, [jobId]);

  useEffect(() => {
    if (!active || !jobId) return;
    const token = ++request.current;
    let cancelled = false;
    api<JobMatch>(`/api/job-descriptions/${jobId}/match`, {
      method: "POST",
      body: JSON.stringify({ composition_id: compositionId }),
    })
      .then((result) => {
        if (!cancelled && token === request.current) setMatch(result);
      })
      .catch((reason: Error) => {
        if (!cancelled && token === request.current) setError(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, [active, jobId, compositionId, revision, generation]);

  const setJobId = useCallback((next: string) => {
    manual.current = true;
    setJobIdState(next);
    setError("");
  }, []);

  const refresh = useCallback(() => setGeneration((value) => value + 1), []);

  const reviewOf = (job: JobDescription): KeywordReview => ({
    dismissed: job.keyword_review?.dismissed || [],
    added: job.keyword_review?.added || [],
    matched: job.keyword_review?.matched || [],
    skipped: job.keyword_review?.skipped || [],
  });

  const saveReview = async (review: KeywordReview) => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const saved = await api<JobDescription>(`/api/job-descriptions/${selected.id}`, {
        method: "PUT",
        body: JSON.stringify({
          company: selected.company,
          role: selected.role,
          title: selected.title,
          body: selected.body,
          composition_id: compositionId,
          keyword_review: review,
        }),
      });
      setJobs((rows) => rows.map((row) => (row.id === saved.id ? saved : row)));
      refresh();
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  };

  const sameText = (left: string, right: string) => left.trim().toLowerCase() === right.trim().toLowerCase();

  const dismissRequirement = (row: RequirementRow) => {
    if (!selected) return;
    const review = reviewOf(selected);
    if (review.dismissed.some((text) => sameText(text, row.text))) return;
    saveReview({ ...review, dismissed: [...review.dismissed, row.text] });
  };

  /** Toggle a requirement in keyword_review.matched. The next deterministic match treats it as met. */
  const markRequirement = (row: Pick<RequirementRow, "text">, value?: boolean) => {
    if (!selected) return;
    const review = reviewOf(selected);
    const marked = review.matched.some((text) => sameText(text, row.text));
    const next = value ?? !marked;
    if (next === marked) return;
    saveReview({
      ...review,
      matched: next ? [...review.matched, row.text] : review.matched.filter((text) => !sameText(text, row.text)),
    });
  };

  /** Toggle a keyword in keyword_review.skipped. It stops highlighting but still counts as missing. */
  const skipKeyword = (keyword: string, value = true) => {
    if (!selected || !keyword.trim()) return;
    const review = reviewOf(selected);
    const skipped = review.skipped.some((text) => sameText(text, keyword));
    if (value === skipped) return;
    saveReview({
      ...review,
      skipped: value ? [...review.skipped, keyword.trim()] : review.skipped.filter((text) => !sameText(text, keyword)),
    });
  };

  const addTag = async (bulletId: string, keyword: string) => {
    if (!selected || !keyword) return;
    setBusy(true);
    setError("");
    try {
      await api("/api/library-management/bulk", {
        method: "POST",
        body: JSON.stringify({ ids: [bulletId], action: "add-tags", tag_names: [keyword] }),
      });
      await reloadLibrary();
      refresh();
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  };

  return {
    jobs,
    loaded,
    jobId,
    setJobId,
    selected,
    compareJob,
    match,
    busy,
    error,
    setError,
    refresh,
    dismissRequirement,
    markRequirement,
    skipKeyword,
    addTag,
  };
}

export type JobMatchState = ReturnType<typeof useJobMatch>;

export type AddedRequirement = { group: "required" | "preferred"; text: string };

export type KeywordReview = {
  dismissed: string[];
  added: AddedRequirement[];
  matched: string[];
};

export type JobDescription = {
  id: string;
  company: string;
  role: string;
  title: string;
  body: string;
  composition_id: string | null;
  keyword_review?: KeywordReview;
};

export type KeywordEvidence = {
  source_requirement: string;
  matched_text: string;
  relation: string;
  section: string;
  confidence: number;
  explanation: string;
};

export type RequirementKeyword = {
  keyword: string;
  found: boolean;
  where?: string;
  relation?: string;
  evidence?: KeywordEvidence | null;
};

export type TagSuggestion = {
  keyword: string;
  bullet_id: string | null;
  bullet_excerpt: string;
  section: string;
  suggestion: string;
  line_id?: string;
  placement_id?: string;
  action?: "add_skill" | "rewrite" | "";
};

export type RequirementRow = {
  text: string;
  group: string;
  kind?: string;
  category?: string;
  section?: string;
  weight?: number;
  label?: string;
  match_mode?: "any" | "all";
  matched: boolean;
  manual?: boolean;
  detail?: string;
  keywords: RequirementKeyword[];
  suggestions: TagSuggestion[];
};

export type ScoreComponents = {
  required_coverage: number;
  preferred_coverage: number;
  responsibility_alignment: number;
  domain_alignment: number;
  tools_alignment: number;
  evidence_quality: number;
};

export type EligibilityGate = {
  status: "pass" | "fail" | "unknown" | "not_stated";
  detail: string;
};

export type JobMatch = {
  composition_id: string;
  required_count: number;
  required_matched: number;
  preferred_count: number;
  preferred_matched: number;
  required: RequirementRow[];
  preferred: RequirementRow[];
  responsibilities?: RequirementRow[];
  eligibility_rows?: RequirementRow[];
  scores?: ScoreComponents;
  eligibility?: Record<string, EligibilityGate>;
  families?: { id: string; label: string; confidence: number }[];
};

/** A placed bullet the Suggest wording dialog can rewrite. */
export type VariantTarget = {
  placementId: string;
  /** The preview line id, so a click on one resume line can offer that line's revision. */
  lineId?: string;
  excerpt: string;
  keyword: string;
  requirement: string;
  category: string;
};

/** Opens Add to Skills or Suggest wording from anywhere on the Job match tab. */
export type AssistRequest =
  | { kind: "skill"; keyword: string }
  | { kind: "rewrite"; target: VariantTarget };

export type DashboardTab = "overview" | "requirements" | "coach" | "ats";

export type AiStatus = "ok" | "unavailable" | "rate_limited" | "invalid";

export type CoachSuggestion = {
  id: string;
  kind: "rewrite" | "summary" | "add_skill";
  requirement: string;
  group: string;
  category: string;
  keyword: string;
  placement_id: string;
  original: string;
  proposed: string;
  rationale: string;
  priority: "high" | "medium" | "low";
};

export type CoachEquivalent = {
  id: string;
  requirement: string;
  group: string;
  placement_id: string;
  bullet: string;
  rationale: string;
};

export type CoachResult = {
  status: AiStatus;
  detail: string;
  model: string;
  revision: number;
  suggestions: CoachSuggestion[];
  equivalents: CoachEquivalent[];
  dropped: number;
};

export type AtsComponent = {
  id: string;
  label: string;
  weight: number;
  earned: number;
  ratio: number;
  detail: string;
  tips: string[];
};

export type AtsScore = {
  score: number;
  band: "Strong" | "Fair" | "Needs work";
  components: AtsComponent[];
  methodology: { id: string; label: string; weight: number; rule: string; why: string }[];
  disclaimer: string;
  revision: number;
};

export function allRows(match: JobMatch | null): RequirementRow[] {
  if (!match) return [];
  return [...match.required, ...match.preferred, ...(match.responsibilities || [])];
}

export function groupLabel(group: string) {
  if (group === "required") return "Required";
  if (group === "preferred") return "Preferred";
  if (group === "responsibilities" || group === "responsibility") return "Responsibility";
  return group;
}

/** Headline match score: 70% required coverage, 30% preferred coverage. Deterministic. */
export function headlineScore(match: JobMatch | null) {
  const scores = match?.scores;
  if (!match || !scores) return 0;
  const hasPreferred = match.preferred_count > 0;
  const value = hasPreferred
    ? scores.required_coverage * 0.7 + scores.preferred_coverage * 0.3
    : scores.required_coverage;
  return Math.round(value * 100);
}

export function rewriteTargets(row: RequirementRow): VariantTarget[] {
  return row.suggestions
    .filter((item) => item.action === "rewrite" && item.placement_id)
    .map((item) => ({
      placementId: item.placement_id as string,
      lineId: item.line_id,
      excerpt: item.bullet_excerpt,
      keyword: item.keyword,
      requirement: row.text,
      category: row.category || row.kind || "",
    }));
}

export function skillKeywords(row: RequirementRow): string[] {
  return [
    ...new Set(
      row.suggestions
        .filter((item) => item.action === "add_skill" && item.keyword)
        .map((item) => item.keyword),
    ),
  ];
}

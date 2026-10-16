# Resume Engine matching recommendations

## Taxonomy changes in this package

- Split `product-management` from `project-management` to prevent Jira/Smartsheet project evidence from being treated as equivalent to product discovery, roadmaps, user research, or lifecycle ownership.
- Added `program-portfolio-management` for portfolio reviews, governance, dependencies, funding, budgets, gate reviews, and IFP-style programme work.
- Expanded `finance`, `tax-technology`, and `timekeeping` using the supplied postings.
- Added `data-transformation` and `emerging-technology` clusters for the finance transformation and emerging-tech postings.
- Added conservative aliases and cross-functional combinations. Combinations require multiple signals and therefore reduce single-keyword false positives.

## Recommended job_match.py redesign

1. Parse the posting into sections before extracting terms: responsibilities, required qualifications, preferred qualifications, education, schedule/location, and compensation/disclaimer.
2. Replace the current phrase-length `kind` heuristic with explicit categories: tool, domain, responsibility, methodology, credential, degree, experience duration, and soft skill.
3. Give every requirement a weight: required 1.0, preferred 0.45, responsibility 0.65, and boilerplate 0.0. Keep these values configurable and tune them against labelled examples.
4. Track evidence strength separately: exact mention, alias, same cluster, combination, and optional semantic/AI match. Do not count all of these as equal.
5. Match at bullet level and preserve evidence: source requirement, matched resume text, relation type, section, confidence, and explanation.
6. Add negation and context handling so “no experience required”, “willing to learn”, and tool names appearing only in job-posting examples do not become hard requirements.
7. Add title/family classification before matching. Use multi-label output because finance transformation, HRIS, tax technology, and technical programme roles overlap.
8. Separate eligibility gates from relevance: degree, years, certification, schedule, travel, work location, and employment type should not be blended into a keyword percentage.
9. Calibrate with the Kaggle data only after de-duplication, HTML removal, PII stripping, and category/title quality checks. The dataset is useful for vocabulary discovery, not as truth for fit scoring.
10. Return score components rather than one opaque score: required coverage, preferred coverage, responsibility alignment, domain alignment, tools alignment, and evidence quality.

## OpenRouter architecture

Use AI as an optional enrichment layer, never as the sole matcher.

- Deterministic pass first: YAML taxonomy, aliases, combinations, requirement parser, and exact evidence.
- AI pass second: classify job families, categorise extracted terms, map genuinely equivalent phrases, suggest missing taxonomy candidates, and draft resume suggestions grounded in supplied resume evidence.
- Validation pass: require structured JSON, validate with Pydantic, reject unknown categories, verify every quoted evidence span exists in the source, and discard unsupported suggestions.
- Merge policy: deterministic matches win. AI may add a candidate relation with confidence and provenance, but should not silently convert an inferred skill into a claimed skill.
- Fallback: on timeout, HTTP 429, invalid JSON, unavailable free model, or low confidence, return the deterministic result without blocking the user.
- Privacy: never send names, contact details, employee IDs, confidential internal details, or full resume history when a redacted excerpt is sufficient.
- Cache by hash of redacted job description, resume version, prompt version, model ID, and taxonomy version.
- Log model ID, prompt version, latency, validation outcome, and token usage, but not raw personal data.

## Suggested AI tasks

- `classify_job`: multi-label families, seniority, domain, and confidence.
- `extract_requirements`: structured required/preferred rows with exact source spans.
- `map_semantics`: candidate taxonomy relation plus rationale and confidence.
- `categorise_bullet`: action, domain, skill, tool, outcome, and metric tags.
- `suggest_resume_changes`: evidence-grounded rewrite suggestions with a strict no-fabrication rule.

## Evaluation set

Build a small hand-labelled fixture from the supplied postings plus representative Resume Engine resumes. Measure precision and recall for requirement extraction, exact/related match accuracy, job-family classification, bullet category accuracy, unsupported suggestion rate, and deterministic fallback success. Keep the Kaggle rows out of the final test set if they were used for vocabulary discovery.

# Expanding the related-skills dictionary

The placement ranker reads [`backend/app/related_skills.yaml`](../backend/app/related_skills.yaml). Edit that file to teach it new tools, spellings, phrases, and combinations. You do not need to change the ranker.

Matching lowercases text and applies aliases before it compares words. Punctuation becomes spaces, so `scikit-learn` and `scikit learn` are the same. A few tech names are kept whole before that happens: `.NET` stays `dotnet`, `node.js` stays `nodejs` (the same rule covers `next.js` and `react.js`), and the language `R` stays `r`. `R&D` stays `rnd`, so it is not the language R. A name or phrase matches only as a whole term, so `sql` does not match inside `mysql`, and `learning` does not match `machine learning`.

A keyword with no dictionary entry still ranks on shared words alone.

## Add a name to a cluster

Names in the same cluster count as related to each other. A bullet that says `pandas` can become a home for a missing `Python` keyword.

```yaml
clusters:
  - id: python
    names:
      - python
      - pandas
      - numpy
```

Add the new name under `names`. Keep one concept per cluster. Reuse an existing `id` when the tool belongs with tools that are already listed.

## Add an alias

Aliases map a spelling to the canonical name before cluster lookup. Use an alias for an abbreviation instead of copying the whole cluster.

```yaml
aliases:
  k8s: kubernetes
  sklearn: scikit-learn
```

Point an alias at a canonical name, not at another alias. `k8s: kubernetes` is enough for both the keyword and the resume text.

## Add a phrase

Phrases are multi-word members of a cluster. They match only as a whole phrase.

```yaml
clusters:
  - id: python
    names:
      - python
    phrases:
      - machine learning
```

`Shipped a machine learning model` relates to Python. `Still learning the stack` does not, because `learning` alone is not the phrase.

Put a multi-word tool in `phrases` as well, for example `power bi` or `google cloud`.

## Add a combination

A combination matches only when every term under `when` is present. Use one when two skills together should count toward a different cluster, even though neither word is that keyword.

```yaml
combinations:
  - when:
      - python
      - sql
    relates_to: data-engineering
```

`relates_to` is a cluster `id`. The keyword has to belong to that cluster, as a name or a phrase. `Moved Python models onto SQL warehouses` can then rank for `data engineering`. A line that mentions only Python does not.

`when` needs at least two terms. A single related tool belongs in a cluster, not a combination.

## Check the ranking

When a new entry should change which line ranks first, add a focused test in [`tests/test_job_match.py`](../tests/test_job_match.py). Run:

```bash
pytest -q tests/test_related_skills.py tests/test_related_skills_dictionary.py tests/test_job_match.py
```

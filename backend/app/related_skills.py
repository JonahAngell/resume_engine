"""Load the related-skills dictionary and look terms up in resume text."""

import re
from pathlib import Path

import yaml

DICTIONARY_PATH = Path(__file__).with_name("related_skills.yaml")


# Placeholders use only letters and digits so the punctuation pass cannot split them.
_R_AND_D = re.compile(r"\br&d\b")
_DOTTED_JS = re.compile(r"\b([a-z][a-z0-9]*)\.js\b")
_DOT_NET = re.compile(r"\.net\b")
_R_LANGUAGE = re.compile(r"(?<![a-z0-9])r(?![a-z0-9&])")


def _normalize_base(value: str) -> str:
    """Lowercase, keep tech names whole, then turn other punctuation into spaces."""
    text = (value or "").lower()
    text = _R_AND_D.sub(" rnd ", text)
    text = _DOTTED_JS.sub(lambda match: f" {match.group(1)}js ", text)
    text = _DOT_NET.sub(" dotnet ", text)
    text = _R_LANGUAGE.sub(" r ", text)
    text = re.sub(r"[^a-z0-9+#]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class RelatedSkills:
    def __init__(self, path: Path = DICTIONARY_PATH):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        alias_pairs = raw.get("aliases") or {}
        self.aliases = {}
        self.alias_terms: list[tuple[str, str, str]] = []
        for key, value in alias_pairs.items():
            display = str(key).strip()
            normalized = _normalize_base(display)
            canonical = _normalize_base(str(value))
            if not normalized or not canonical:
                continue
            self.aliases[normalized] = canonical
            self.alias_terms.append((display, normalized, canonical))
        self.clusters: dict[str, list[tuple[str, str]]] = {}
        self.membership: dict[str, set[str]] = {}
        for cluster in raw.get("clusters") or []:
            cluster_id = str(cluster.get("id") or "").strip()
            if not cluster_id:
                continue
            terms: list[tuple[str, str]] = []
            seen: set[str] = set()
            for display in [*(cluster.get("names") or []), *(cluster.get("phrases") or [])]:
                label = str(display).strip()
                normalized = self._canonicalize(label)
                if not label or not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                terms.append((label, normalized))
                self.membership.setdefault(normalized, set()).add(cluster_id)
            self.clusters[cluster_id] = terms
        self.combinations = []
        for combo in raw.get("combinations") or []:
            relates_to = str(combo.get("relates_to") or "").strip()
            when = []
            for term in combo.get("when") or []:
                label = str(term).strip()
                normalized = self._canonicalize(label)
                if label and normalized:
                    when.append((label, normalized))
            if relates_to and len(when) >= 2:
                self.combinations.append({"relates_to": relates_to, "when": when})

    def _canonicalize(self, value: str) -> str:
        text = _normalize_base(value)
        if text in self.aliases:
            return self.aliases[text]
        parts = [self.aliases.get(part, part) for part in text.split()]
        joined = " ".join(parts)
        return self.aliases.get(joined, joined)

    def _clusters_for(self, keyword: str) -> set[str]:
        return set(self.membership.get(self._canonicalize(keyword), ()))

    def _contained_term(self, text: str, terms: list[tuple[str, str]]) -> str | None:
        raw = f" {_normalize_base(text)} "
        canonical = f" {self._canonicalize(text)} "
        for label, normalized in sorted(terms, key=lambda item: len(item[1]), reverse=True):
            if f" {normalized} " in raw or f" {normalized} " in canonical:
                return label
        return None

    def related_mention(self, keyword: str, text: str) -> str | None:
        """Return a dictionary term in `text` that shares a cluster with `keyword`."""
        keyword_key = self._canonicalize(keyword)
        cluster_ids = self._clusters_for(keyword)
        if not cluster_ids:
            return None
        terms = []
        seen: set[str] = set()
        cluster_keys = {keyword_key}
        for cluster_id in cluster_ids:
            for label, normalized in self.clusters.get(cluster_id, []):
                cluster_keys.add(normalized)
                if normalized == keyword_key or normalized in seen:
                    continue
                seen.add(normalized)
                terms.append((label, normalized))
        for display, normalized, canonical in self.alias_terms:
            if canonical in cluster_keys and normalized != keyword_key and normalized not in seen:
                seen.add(normalized)
                terms.append((display, normalized))
        return self._contained_term(text, terms)

    def combination_mention(self, keyword: str, text: str) -> str | None:
        """Return the joined terms when every term in a combination is present."""
        cluster_ids = self._clusters_for(keyword)
        if not cluster_ids:
            return None
        for combo in self.combinations:
            if combo["relates_to"] not in cluster_ids:
                continue
            if all(self._contained_term(text, [term]) for term in combo["when"]):
                return " and ".join(label for label, _normalized in combo["when"])
        return None


DICTIONARY = RelatedSkills()


def related_mention(keyword: str, text: str) -> str | None:
    return DICTIONARY.related_mention(keyword, text)


def combination_mention(keyword: str, text: str) -> str | None:
    return DICTIONARY.combination_mention(keyword, text)

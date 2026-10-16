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
_ACRONYMS = {
    "acp", "ai", "api", "aws", "bi", "ca", "cad", "cd", "ci", "cpa", "cpo", "csm",
    "dax", "edp", "elt", "epm", "erp", "etl", "fp", "gaap", "gcp", "hr", "hris",
    "ibm", "json", "kpi", "llm", "llms", "mba", "nlp", "pmp", "qa", "roi", "sap", "sql",
    "sso", "ssrs", "tdd", "ui", "ux", "vba", "xml",
}


def _normalize_base(value: str) -> str:
    """Lowercase, keep tech names whole, then turn other punctuation into spaces."""
    text = (value or "").lower()
    text = _R_AND_D.sub(" rnd ", text)
    text = _DOTTED_JS.sub(lambda match: f" {match.group(1)}js ", text)
    text = _DOT_NET.sub(" dotnet ", text)
    text = _R_LANGUAGE.sub(" r ", text)
    text = re.sub(r"[^a-z0-9+#]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _smart_title(label: str) -> str:
    def one(part: str) -> str:
        if not part:
            return part
        if part.lower() in _ACRONYMS or any(char.isdigit() for char in part):
            return part.upper()
        return part.capitalize()

    words = []
    for word in label.split():
        slashed = []
        for piece in word.split("/"):
            slashed.append("-".join(one(bit) for bit in piece.split("-")))
        words.append("/".join(slashed))
    return " ".join(words)


def _display_label(label: str) -> str:
    if any(char.isupper() for char in label):
        return label
    return _smart_title(label)


def _source_phrase(text: str, window: tuple[str, ...]) -> str:
    parts = [re.escape(word) for word in window]
    pattern = re.compile(r"(?<!\w)" + r"[\W_]+".join(parts) + r"(?!\w)", re.IGNORECASE)
    match = pattern.search(text or "")
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(0)).strip(" ,;:()[]{}")


def _hint_word(value: str) -> str:
    word = _normalize_base(str(value))
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def hint_words(name: str) -> set[str]:
    """Group-name tokens in the form `group_hints` words use."""
    return {_hint_word(token) for token in _normalize_base(name).split()} - {""}


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
        self.cluster_category: dict[str, str] = {}
        for category, cluster_ids in (raw.get("categories") or {}).items():
            label = str(category).strip()
            for cluster_id in cluster_ids or []:
                cleaned = str(cluster_id).strip()
                if label and cleaned:
                    self.cluster_category[cleaned] = label
        self.families = []
        for family in raw.get("families") or []:
            family_id = str(family.get("id") or "").strip()
            label = str(family.get("label") or family_id).strip()
            clusters = [str(item).strip() for item in family.get("clusters") or [] if str(item).strip()]
            if family_id and clusters:
                self.families.append({"id": family_id, "label": label, "clusters": clusters})
        self.group_hints: dict[str, dict] = {}
        for hint_id, hint in (raw.get("group_hints") or {}).items():
            words = {_hint_word(word) for word in (hint or {}).get("words") or []}
            words.discard("")
            title = str((hint or {}).get("title") or hint_id).strip()
            if words:
                self.group_hints[str(hint_id)] = {"title": title, "words": words}
        self.cluster_hints = {
            str(cluster_id): [str(item) for item in hints or []]
            for cluster_id, hints in (raw.get("cluster_hints") or {}).items()
        }
        self.category_hints = {
            str(category): [str(item) for item in hints or []]
            for category, hints in (raw.get("category_hints") or {}).items()
        }
        self.display_of: dict[str, str] = {}
        self.surfaces: dict[str, set[str]] = {}
        self._phrases_by_size: dict[int, dict[tuple[str, ...], tuple[str, bool]]] = {}
        self._max_phrase = 1
        for terms in self.clusters.values():
            for label, canonical in terms:
                self.display_of.setdefault(canonical, _display_label(label))
                self._remember_surface(canonical, _normalize_base(label))
                self._remember_surface(canonical, canonical)
                self._add_phrase(_normalize_base(label), canonical, False)
                if _normalize_base(label) != canonical:
                    self._add_phrase(canonical, canonical, False)
        for _display, normalized, canonical in self.alias_terms:
            target = canonical if canonical in self.membership else self._canonicalize(canonical)
            if target not in self.membership:
                continue
            self._remember_surface(target, normalized)
            self._add_phrase(normalized, target, normalized != target)

    def _remember_surface(self, canonical: str, surface: str) -> None:
        if surface:
            self.surfaces.setdefault(canonical, set()).add(surface)

    def _add_phrase(self, surface: str, canonical: str, via_alias: bool) -> None:
        words = tuple(surface.split())
        if not words or (len(words) == 1 and len(words[0]) < 2):
            return
        if canonical not in self.membership:
            return
        bucket = self._phrases_by_size.setdefault(len(words), {})
        current = bucket.get(words)
        if current and (not current[1] or via_alias):
            return
        bucket[words] = (canonical, via_alias)
        self._max_phrase = max(self._max_phrase, len(words))

    def _canonicalize(self, value: str) -> str:
        text = _normalize_base(value)
        if text in self.aliases:
            return self.aliases[text]
        parts = [self.aliases.get(part, part) for part in text.split()]
        joined = " ".join(parts)
        return self.aliases.get(joined, joined)

    def match_terms(self, text: str) -> list[str]:
        """Return canonical tool and skill labels in the order they appear."""
        words = _normalize_base(text).split()
        if not words:
            return []
        occupied = [False] * len(words)
        found: list[tuple[int, str]] = []
        for size in range(self._max_phrase, 0, -1):
            phrases = self._phrases_by_size.get(size)
            if not phrases:
                continue
            for index in range(len(words) - size + 1):
                if occupied[index]:
                    continue
                window = tuple(words[index : index + size])
                entry = phrases.get(window)
                if not entry or any(occupied[index : index + size]):
                    continue
                canonical, via_alias = entry
                for offset in range(size):
                    occupied[index + offset] = True
                found.append((index, self._term_display(text, window, canonical, via_alias)))
        found.sort()
        displays: list[str] = []
        seen: set[str] = set()
        for _index, display in found:
            key = display.lower()
            if not display or key in seen:
                continue
            seen.add(key)
            displays.append(display)
        return displays

    def _term_display(self, text: str, window: tuple[str, ...], canonical: str, via_alias: bool) -> str:
        label = self.display_of.get(canonical, _smart_title(canonical))
        if via_alias:
            return label
        source = _source_phrase(text, window)
        if source and any(char.isupper() for char in source):
            return source
        return label

    def mentions(self, keyword: str, text: str) -> bool:
        """True when `text` contains this term or an alias, not a cluster sibling."""
        canonical = self._canonicalize(keyword)
        if canonical not in self.membership:
            return False
        terms = [(surface, surface) for surface in self.surfaces.get(canonical, set())]
        if not terms:
            return False
        return self._contained_term(text, terms) is not None

    def covers_token(self, keyword: str, token: str) -> bool:
        canonical = self._canonicalize(keyword)
        token_norm = _normalize_base(token)
        if not token_norm or canonical not in self.surfaces:
            return False
        padded = f" {token_norm} "
        return any(padded in f" {surface} " for surface in self.surfaces[canonical])

    def is_known(self, keyword: str) -> bool:
        return self._canonicalize(keyword) in self.membership

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

    def category_for_term(self, keyword: str) -> str | None:
        categories = {
            self.cluster_category.get(cluster_id)
            for cluster_id in self._clusters_for(keyword)
            if self.cluster_category.get(cluster_id)
        }
        if not categories:
            return None
        for preferred in ("tool", "methodology", "domain"):
            if preferred in categories:
                return preferred
        return sorted(categories)[0]

    def canonical(self, value: str) -> str:
        return self._canonicalize(value)

    def display_for(self, keyword: str) -> str:
        """Display label for a skill: the posting's casing when it has any, else the dictionary's."""
        text = " ".join((keyword or "").split())
        if any(char.isupper() for char in text):
            return text
        canonical = self._canonicalize(text)
        return self.display_of.get(canonical) or _smart_title(text)

    def hints_for_term(self, keyword: str) -> list[str]:
        """Hint set ids for a term, cluster hints first, then category hints."""
        found: list[str] = []
        clusters = sorted(self._clusters_for(keyword))
        for cluster_id in clusters:
            for hint in self.cluster_hints.get(cluster_id, []):
                if hint not in found:
                    found.append(hint)
        if not found:
            for cluster_id in clusters:
                category = self.cluster_category.get(cluster_id)
                for hint in self.category_hints.get(category or "", []):
                    if hint not in found:
                        found.append(hint)
        return found

    def clusters_in_text(self, text: str) -> set[str]:
        found: set[str] = set()
        for display in self.match_terms(text):
            found.update(self._clusters_for(display))
        return found


DICTIONARY = RelatedSkills()


def related_mention(keyword: str, text: str) -> str | None:
    return DICTIONARY.related_mention(keyword, text)


def combination_mention(keyword: str, text: str) -> str | None:
    return DICTIONARY.combination_mention(keyword, text)


def find_terms(text: str) -> list[str]:
    return DICTIONARY.match_terms(text)


def mentions(keyword: str, text: str) -> bool:
    return DICTIONARY.mentions(keyword, text)


def is_known_term(keyword: str) -> bool:
    return DICTIONARY.is_known(keyword)


def covers_token(keyword: str, token: str) -> bool:
    return DICTIONARY.covers_token(keyword, token)


def category_for_term(keyword: str) -> str | None:
    return DICTIONARY.category_for_term(keyword)


def clusters_in_text(text: str) -> set[str]:
    return DICTIONARY.clusters_in_text(text)


def job_families() -> list[dict]:
    return [dict(item) for item in DICTIONARY.families]


def canonical_term(value: str) -> str:
    return DICTIONARY.canonical(value)


def display_for(keyword: str) -> str:
    return DICTIONARY.display_for(keyword)


def hints_for_term(keyword: str) -> list[str]:
    return DICTIONARY.hints_for_term(keyword)

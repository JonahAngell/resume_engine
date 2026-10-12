from app.related_skills import _normalize_base, combination_mention, related_mention


def test_protected_tech_names_survive_punctuation():
    assert _normalize_base(".NET") == "dotnet"
    assert _normalize_base("ASP.NET") == "asp dotnet"
    assert _normalize_base("node.js") == "nodejs"
    assert _normalize_base("Next.js") == "nextjs"
    assert _normalize_base("R") == "r"
    assert _normalize_base("R programming") == "r programming"
    assert _normalize_base("R&D") == "rnd"
    assert _normalize_base("scikit-learn") == "scikit learn"


def test_alias_matches_the_canonical_skill():
    assert related_mention("Python", "Trained models with sklearn") == "scikit-learn"
    assert related_mention("Kubernetes", "Rolled out k8s for the platform") == "k8s"


def test_phrase_matches_only_as_a_whole():
    assert related_mention("Python", "Still learning the stack") is None
    assert related_mention("Python", "Shipped a machine learning model") == "machine learning"


def test_combination_matches_only_when_every_term_is_present():
    assert combination_mention("data engineering", "Wrote Python scripts") is None
    assert combination_mention("data engineering", "Moved Python jobs into SQL") == "Python and SQL"


def test_unknown_keyword_has_no_related_mention():
    assert related_mention("underwater basket weaving", "Built dashboards in pandas") is None

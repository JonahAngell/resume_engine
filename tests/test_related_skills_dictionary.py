"""Lint the related-skills dictionary so new entries stay wired to real clusters."""

from app.related_skills import DICTIONARY


def test_every_alias_points_at_a_cluster_term():
    missing = [
        f"{display} -> {canonical}"
        for display, _normalized, canonical in DICTIONARY.alias_terms
        if canonical not in DICTIONARY.membership
    ]
    assert missing == []


def test_every_combination_names_a_cluster():
    missing = [
        combo["relates_to"]
        for combo in DICTIONARY.combinations
        if combo["relates_to"] not in DICTIONARY.clusters
    ]
    assert missing == []

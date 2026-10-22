import asyncio
import json
from uuid import UUID, uuid4

from app.ai_client import AiCallError, AiCompletion
from app.ai_recommend import MAX_BULLETS, MAX_BULLETS_PER_ENTRY, MAX_ENTRIES, recommend_resume

JOB = """Senior Product Analyst

Required Qualifications
- Financial forecasting with SQL dashboards
- Experience with Looker
"""


def _id():
    return str(uuid4())


def _bullets(texts):
    rows = []
    for order, variants in enumerate(texts):
        bullet_id = _id()
        for index, body in enumerate(variants):
            rows.append(
                {"id": bullet_id, "sort_order": order, "archived_at": None, "variant_id": _id(),
                 "body": body, "is_default": index == 0, "variant_archived_at": None}
            )
    return rows


def _entry(title, organization, texts, archived=False):
    return {"id": _id(), "title": title, "organization": organization, "name": organization,
            "date_label": "2020–2023", "archived_at": "2024-01-01" if archived else None,
            "bullets": _bullets(texts)}


def library():
    jobs = [
        _entry("Analyst", "Parkline", [
            ["Ran weekly staffing reports", "Built SQL dashboards for financial forecasting"],
            ["Led onboarding for new hires"],
            ["Owned Looker reporting for venue teams"],
            ["Planned team offsites"],
        ]),
        *[_entry(f"Role {n}", f"Company {n}", [[f"Did task {n}.{i}"] for i in range(6)]) for n in range(5)],
        _entry("Old", "Archived Co", [["Financial forecasting in SQL"]], archived=True),
    ]
    return {
        "profiles": [{"name": "Nia Calder", "email": "nia@example.com", "phone": "555-123-4567",
                      "field_variants": []}],
        "summary_variants": [
            {"id": _id(), "name": "default", "body": "Operations generalist.", "archived_at": None},
            {"id": _id(), "name": "Analytics", "body": "Analyst focused on SQL and financial forecasting.",
             "archived_at": None},
        ],
        "education": [{"id": _id(), "archived_at": None}],
        "tool_groups": [
            {"id": _id(), "name": "Analytics", "archived_at": None, "items": [{"name": "Looker"}, {"name": "SQL"}]},
            {"id": _id(), "name": "Design", "archived_at": None, "items": [{"name": "Figma"}]},
        ],
        "employment": jobs,
        "projects": [_entry("Forecast model", "Side project", [["Built a Looker forecast"]])],
        "leadership": [],
        "interests": [{"id": _id(), "body": "Climbing", "archived_at": None}],
        "custom_sections": [],
    }


def model(data):
    async def complete(messages, schema, name):
        complete.calls.append(messages)
        return AiCompletion(data, "m:free")

    complete.calls = []
    return complete


def run(lib, complete):
    return asyncio.run(recommend_resume(JOB, lib, complete=complete))


def _variant_ids(entry):
    return {row["variant_id"]: row for row in entry["bullets"]}


def test_maps_model_keys_to_library_records():
    lib = library()
    probe = model({"entries": []})
    run(lib, probe)
    request = json.loads(probe.calls[0][1]["content"])
    first = request["entries"][0]
    # The best keyword match is offered first, with its strongest wording first.
    assert "Parkline" in first["title"]
    sql = next(v for b in first["bullets"] for v in b["variants"] if "SQL dashboards" in v["text"])
    summary = next(s["key"] for s in request["summaries"] if "SQL" in s["text"])
    group = next(g["key"] for g in request["skill_groups"] if g["name"] == "Analytics")
    result = run(lib, model({
        "entries": [{"key": first["key"], "bullets": [sql["key"], "b999v1"], "reason": "Matches forecasting."},
                    {"key": "e404", "bullets": []}],
        "summary": summary,
        "skill_groups": [group, "g99"],
        "interests": True,
    }))
    assert result["status"] == "ok" and result["method"] == "ai"
    assert result["dropped"] == 2
    selection = result["selection"]
    parkline = lib["employment"][0]
    # The project the model skipped is added after its pick.
    assert list(selection.items["content_item"]) == [UUID(parkline["id"]), UUID(lib["projects"][0]["id"])]
    chosen = _variant_ids(parkline)[str(next(iter(selection.bullets.values())))]
    assert chosen["body"] == "Built SQL dashboards for financial forecasting"
    assert selection.summary_id == UUID(lib["summary_variants"][1]["id"])
    assert list(selection.items["tool_group"]) == [UUID(lib["tool_groups"][0]["id"])]
    assert selection.items["interest"] and selection.items["education_item"]
    assert result["entries"][0]["reason"] == "Matches forecasting."


def test_prompt_has_no_ids_or_contact_details_or_archived_records():
    lib = library()
    probe = model({"entries": []})
    run(lib, probe)
    content = probe.calls[0][1]["content"]
    assert lib["employment"][0]["id"] not in content
    assert lib["employment"][0]["bullets"][0]["variant_id"] not in content
    assert "nia@example.com" not in content and "555-123-4567" not in content
    assert "Archived Co" not in content


def test_enforces_one_page_budget():
    lib = library()
    probe = model({"entries": []})
    run(lib, probe)
    request = json.loads(probe.calls[0][1]["content"])
    entries = [{"key": e["key"], "bullets": [b["variants"][0]["key"] for b in e["bullets"]]}
               for e in request["entries"]]
    result = run(lib, model({"entries": entries}))
    kinds = [e["section"] for e in result["entries"]]
    assert kinds.count("work_experience") == MAX_ENTRIES["employment"]
    assert kinds.count("projects") <= MAX_ENTRIES["project"]
    assert all(e["bullets"] <= MAX_BULLETS_PER_ENTRY for e in result["entries"])
    assert result["bullet_count"] <= MAX_BULLETS == len(result["selection"].bullets)


def test_falls_back_to_keywords_when_model_fails():
    async def failing(messages, schema, name):
        raise AiCallError("rate_limited")

    lib = library()
    result = run(lib, failing)
    assert result["status"] == "rate_limited" and result["method"] == "keywords"
    selection = result["selection"]
    assert UUID(lib["employment"][0]["id"]) in selection.items["content_item"]
    assert UUID(lib["employment"][-1]["id"]) not in selection.items["content_item"]
    parkline = _variant_ids(lib["employment"][0])
    picked = [parkline[str(v)]["body"] for v in selection.bullets.values() if str(v) in parkline]
    assert "Built SQL dashboards for financial forecasting" in picked
    assert "Ran weekly staffing reports" not in picked
    # Only skill groups that match the posting.
    assert list(selection.items["tool_group"]) == [UUID(lib["tool_groups"][0]["id"])]
    assert len(selection.bullets) <= MAX_BULLETS


def test_invalid_response_falls_back():
    result = run(library(), model({"entries": [{"key": "nope", "bullets": []}]}))
    assert result["status"] == "invalid" and result["method"] == "keywords"
    assert result["selection"].items["content_item"]


def _project_ids(lib, selection):
    return [UUID(p["id"]) for p in lib["projects"] if UUID(p["id"]) in selection.items["content_item"]]


def _project_bullets(lib, selection):
    ids = {row["variant_id"] for p in lib["projects"] for row in p["bullets"]}
    return [v for v in selection.bullets.values() if str(v) in ids]


def test_projects_are_offered_with_bullets_even_after_a_long_job_history():
    lib = library()
    lib["employment"] += [
        _entry(f"Extra {n}", f"Firm {n}", [[f"Task {n}.{i}.{v}" for v in range(3)] for i in range(5)])
        for n in range(30)
    ]
    probe = model({"entries": []})
    run(lib, probe)
    request = json.loads(probe.calls[0][1]["content"])
    projects = [e for e in request["entries"] if e["type"] == "project"]
    assert projects and projects[0]["bullets"]


def test_adds_a_project_when_the_model_skips_projects():
    lib = library()
    probe = model({"entries": []})
    run(lib, probe)
    request = json.loads(probe.calls[0][1]["content"])
    job = next(e for e in request["entries"] if e["type"] == "job")
    result = run(lib, model({"entries": [{"key": job["key"], "bullets": []}]}))
    assert result["method"] == "ai"
    assert _project_ids(lib, result["selection"]) and _project_bullets(lib, result["selection"])
    assert "projects" in [e["section"] for e in result["entries"]]


def test_keyword_fallback_keeps_a_project_without_keyword_matches():
    async def failing(messages, schema, name):
        raise AiCallError("unavailable")

    lib = library()
    lib["projects"] = [_entry("Garden app", "Side project", [["Planted tomatoes"]])]
    result = run(lib, failing)
    assert result["method"] == "keywords"
    assert _project_ids(lib, result["selection"]) and _project_bullets(lib, result["selection"])

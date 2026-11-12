"""End to end: skill group and interest variants in the library, on resumes and in defaults sets."""

import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


@pytest.fixture()
def http(monkeypatch):
    name = f"skvar_{uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base, _, _ = URL.rpartition("/")
    monkeypatch.setenv("DATABASE_URL", f"{base}/{name}")
    monkeypatch.delenv("STUDIOSHARE_DB_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    from app import main

    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def seeded(http):
    response = http.post("/api/library/import-seed", json={"seed_key": "nia-calder-resume-v1"})
    assert response.status_code == 200, response.text
    library = http.get("/api/library").json()
    return library, response.json()["composition_id"]


def comp(http, cid):
    response = http.get(f"/api/compositions/{cid}")
    assert response.status_code == 200, response.text
    return response.json()


def group_on(resume, group_id, name=None):
    for group in resume["tool_groups"]:
        if str(group.get("id")) == str(group_id) or (name and group["name"] == name):
            return group
    return None


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json()


def test_skill_group_variant_library_and_resume(http):
    library, cid = seeded(http)
    group = next(g for g in library["tool_groups"] if len(g["items"]) >= 3)
    tools = group["items"]
    assert group["field_variants"] == []

    # Only the group's own tools are allowed.
    other_tool = next(t["id"] for g in library["tool_groups"] if g["id"] != group["id"] for t in g["items"])
    bad = http.post(f"/api/library/tool-groups/{group['id']}/variants",
                    json={"name": "Bad", "group_name": "X", "tool_ids": [other_tool]})
    assert bad.status_code == 422
    assert http.post(f"/api/library/tool-groups/{group['id']}/variants", json={"name": "No label"}).status_code == 422

    variant = ok(http.post(f"/api/library/tool-groups/{group['id']}/variants", json={
        "name": "Data focus", "group_name": "Data Tools",
        "tool_ids": [tools[2]["id"], tools[0]["id"]]}), 201)
    assert variant["tool_ids"] == [tools[2]["id"], tools[0]["id"]]
    dup = http.post(f"/api/library/tool-groups/{group['id']}/variants",
                    json={"name": "Data focus", "group_name": "Y"})
    assert dup.status_code == 409
    library = http.get("/api/library").json()
    assert [v["name"] for v in next(g for g in library["tool_groups"] if g["id"] == group["id"])["field_variants"]] == ["Data focus"]

    # Choosing the variant swaps the label and the tools, in the variant's order.
    state = comp(http, cid)
    state = ok(http.put(f"/api/compositions/{cid}/item-variant", json={
        "revision": state["revision"], "section": "tool_groups", "item_id": group["id"], "variant_id": variant["id"]}))
    shown = group_on(state["resume"], group["id"], "Data Tools")
    assert shown["name"] == "Data Tools"
    assert shown["items"] == [tools[2]["name"], tools[0]["name"]]

    # Per-resume hiding still applies on top.
    state = ok(http.put(f"/api/compositions/{cid}/tools/{tools[0]['id']}",
                        json={"revision": state["revision"], "included": False}))
    assert group_on(state["resume"], group["id"], "Data Tools")["items"] == [tools[2]["name"]]

    # Editing the variant in the library refreshes the resume.
    ok(http.put(f"/api/library/tool-group-variants/{variant['id']}", json={"group_name": "Analytics"}))
    state = comp(http, cid)
    assert group_on(state["resume"], group["id"], "Analytics")["name"] == "Analytics"

    # Back to the group itself.
    state = ok(http.put(f"/api/compositions/{cid}/item-variant", json={
        "revision": state["revision"], "section": "tool_groups", "item_id": group["id"], "variant_id": None}))
    assert group_on(state["resume"], group["id"], group["name"])["name"] == group["name"]

    # A variant of another group is refused.
    other = next(g for g in library["tool_groups"] if g["id"] != group["id"])
    assert http.put(f"/api/compositions/{cid}/item-variant", json={
        "revision": state["revision"], "section": "tool_groups", "item_id": other["id"],
        "variant_id": variant["id"]}).status_code == 404

    # Default + archive: new resumes use the default; archiving clears it.
    ok(http.put(f"/api/library/tool-group-variants/{variant['id']}", json={"is_default": True}))
    fresh = ok(http.post("/api/compositions", json={"entire_library": True}), 201)
    assert group_on(fresh["resume"], group["id"], "Analytics")["name"] == "Analytics"
    archived = ok(http.post(f"/api/library/tool-group-variants/{variant['id']}/archive"))
    assert archived["archived_at"] and not archived["is_default"]
    # The resume that already used it keeps it; choosing it anew is refused.
    assert group_on(comp(http, fresh["id"])["resume"], group["id"], "Analytics")["name"] == "Analytics"
    state = comp(http, cid)
    assert http.put(f"/api/compositions/{cid}/item-variant", json={
        "revision": state["revision"], "section": "tool_groups", "item_id": group["id"],
        "variant_id": variant["id"]}).status_code == 409
    newer = ok(http.post("/api/compositions", json={"entire_library": True}), 201)
    assert group_on(newer["resume"], group["id"], group["name"])["name"] == group["name"]
    assert ok(http.post(f"/api/library/tool-group-variants/{variant['id']}/restore"))["archived_at"] is None


def test_skill_group_save_modes(http):
    library, cid = seeded(http)
    group = next(g for g in library["tool_groups"] if len(g["items"]) >= 2)
    tools = group["items"]
    state = comp(http, cid)
    state = ok(http.put(f"/api/compositions/{cid}/tools/{tools[0]['id']}",
                        json={"revision": state["revision"], "included": False}))

    # Save as a variant: label plus the tools this resume shows.
    state = ok(http.post(f"/api/compositions/{cid}/tool-groups/{group['id']}/save", json={
        "revision": state["revision"], "mode": "variant", "group_name": "Short list", "name": "Short"}))
    assert group_on(state["resume"], group["id"], "Short list")["items"] == [t["name"] for t in tools[1:]]
    variant = next(g for g in http.get("/api/library").json()["tool_groups"] if g["id"] == group["id"])["field_variants"][0]
    assert variant["name"] == "Short" and variant["tool_ids"] == [t["id"] for t in tools[1:]]

    # Overwrite while a variant is chosen updates that variant, not the group.
    state = ok(http.post(f"/api/compositions/{cid}/tool-groups/{group['id']}/save", json={
        "revision": state["revision"], "mode": "overwrite", "group_name": "Shorter list"}))
    library = http.get("/api/library").json()
    row = next(g for g in library["tool_groups"] if g["id"] == group["id"])
    assert row["name"] == group["name"]
    assert row["field_variants"][0]["group_name"] == "Shorter list"

    # New: a separate group with copies of the shown tools takes its place on this resume.
    state = ok(http.post(f"/api/compositions/{cid}/tool-groups/{group['id']}/save", json={
        "revision": state["revision"], "mode": "new", "group_name": "Brand new"}))
    library = http.get("/api/library").json()
    created = next(g for g in library["tool_groups"] if g["name"] == "Brand new")
    assert [t["name"] for t in created["items"]] == [t["name"] for t in tools[1:]]
    assert group_on(state["resume"], created["id"], "Brand new")["items"] == [t["name"] for t in tools[1:]]
    assert group_on(state["resume"], group["id"]) is None

    # Stale revision.
    assert http.post(f"/api/compositions/{cid}/tool-groups/{created['id']}/save", json={
        "revision": 1, "mode": "overwrite", "group_name": "X"}).status_code == 409


def test_interest_variants_and_save_modes(http):
    library, cid = seeded(http)
    interest = library["interests"][0]
    variant = ok(http.post(f"/api/library/interests/{interest['id']}/variants",
                           json={"name": "Short", "body": "Climbing"}), 201)
    assert http.post(f"/api/library/interests/{interest['id']}/variants", json={"name": "x"}).status_code == 422

    state = comp(http, cid)
    state = ok(http.put(f"/api/compositions/{cid}/item-variant", json={
        "revision": state["revision"], "section": "personal_interests", "item_id": interest["id"],
        "variant_id": variant["id"]}))
    assert "Climbing" in state["resume"]["personal_interests"]
    assert interest["body"] not in state["resume"]["personal_interests"]
    item = next(i for i in state["resume"]["personal_interest_items"] if str(i["id"]) == interest["id"])
    assert item["body"] == "Climbing"

    # Overwrite edits the chosen variant.
    state = ok(http.post(f"/api/compositions/{cid}/interests/{interest['id']}/save", json={
        "revision": state["revision"], "mode": "overwrite", "body": "Bouldering"}))
    assert "Bouldering" in state["resume"]["personal_interests"]
    library = http.get("/api/library").json()
    row = next(i for i in library["interests"] if i["id"] == interest["id"])
    assert row["body"] == interest["body"] and row["field_variants"][0]["body"] == "Bouldering"

    # Save as another variant, auto-named.
    state = ok(http.post(f"/api/compositions/{cid}/interests/{interest['id']}/save", json={
        "revision": state["revision"], "mode": "variant", "body": "Trail running"}))
    library = http.get("/api/library").json()
    names = [v["name"] for v in next(i for i in library["interests"] if i["id"] == interest["id"])["field_variants"]]
    assert names == ["Short", "Variant"]
    assert "Trail running" in state["resume"]["personal_interests"]

    # New interest replaces it on this resume.
    state = ok(http.post(f"/api/compositions/{cid}/interests/{interest['id']}/save", json={
        "revision": state["revision"], "mode": "new", "body": "Chess"}))
    library = http.get("/api/library").json()
    assert any(i["body"] == "Chess" for i in library["interests"])
    assert "Chess" in state["resume"]["personal_interests"]
    assert not any(str(i["id"]) == interest["id"] for i in state["resume"]["personal_interest_items"])


def test_defaults_set_carries_skill_and_interest_variants(http):
    library, cid = seeded(http)
    group = next(g for g in library["tool_groups"] if len(g["items"]) >= 2)
    interest = library["interests"][0]
    gv = ok(http.post(f"/api/library/tool-groups/{group['id']}/variants", json={
        "name": "Pick", "group_name": "Picked", "tool_ids": [group["items"][1]["id"]]}), 201)
    iv = ok(http.post(f"/api/library/interests/{interest['id']}/variants",
                      json={"name": "Alt", "body": "Sailing"}), 201)
    a = http.post("/api/default-sets", json={"name": "Set A"}).json()
    for item_type, item_id, variant_id in (("tool_group", group["id"], gv["id"]), ("interest", interest["id"], iv["id"])):
        ok(http.put("/api/default-sets/memberships", json={
            "item_type": item_type, "item_id": item_id,
            "memberships": [{"set_id": a["id"], "variant_id": variant_id}]}))
    # A variant of a different record is refused.
    other = next(i for i in library["interests"] if i["id"] != interest["id"])
    assert http.put("/api/default-sets/memberships", json={
        "item_type": "interest", "item_id": other["id"],
        "memberships": [{"set_id": a["id"], "variant_id": iv["id"]}]}).status_code in (404, 409, 422)

    made = http.post("/api/compositions", json={"default_set_id": a["id"]}).json()
    assert group_on(made["resume"], group["id"], "Picked")["items"] == [group["items"][1]["name"]]
    assert made["resume"]["personal_interests"] == ["Sailing"]

    # Saving a resume as a defaults set keeps its chosen variants.
    saved = http.post(f"/api/compositions/{made['id']}/default-set", json={"name": "From resume"})
    assert saved.status_code in (200, 201), saved.text
    members = http.get("/api/default-sets").json()["members"]
    set_id = saved.json()["id"]
    picks = {(m["item_type"], m["item_id"]): m["variant_id"] for m in members if m["set_id"] == set_id}
    assert picks[("tool_group", group["id"])] == gv["id"]
    assert picks[("interest", interest["id"])] == iv["id"]

"""Save a reviewed import draft into the library and a new resume."""

from pydantic import ValidationError

from .editing_repository import add_item, create_composition, historical_date, many
from .editing_schemas import HistoricalItemWrite
from .library_repository import (
    _education_render,
    _profile_label_taken,
    create_education,
    create_interest,
    create_profile,
    create_summary,
    create_tool,
    create_tool_group,
)
from .library_schemas import (
    EducationWrite,
    InterestWrite,
    ProfileWrite,
    SummaryWrite,
    ToolGroupWrite,
    ToolWrite,
)
from .resume_import import ImportDraft, ImportEntry
from .schemas import Education, Experience, Header, Project, Resume, ToolGroup

MONTHS = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
LIBRARY_SECTION = {
    "employment": "experience",
    "project": "projects",
    "leadership": "leadership",
}
DESTINATION = {
    "employment": ("work_experience", "content_item"),
    "project": ("projects", "content_item"),
    "leadership": ("leadership", "content_item"),
    "education": ("education", "education_item"),
}
KIND = {"employment": "employment", "project": "project", "leadership": "leadership"}


def _kept(draft: ImportDraft) -> list[ImportEntry]:
    return [entry for entry in draft.entries if entry.included and entry.section != "skip"]


def _message(exc: ValidationError) -> str:
    error = exc.errors()[0]
    text = str(error.get("msg") or "Check the imported records and try again.")
    return text.removeprefix("Value error, ")


def _validate(draft: ImportDraft) -> None:
    kept = _kept(draft)
    profile = draft.profile.included
    summary = draft.summary.included and bool(draft.summary.body.strip())
    if draft.summary.included and not draft.summary.body.strip():
        raise ValueError("Summary text is required.")
    if profile and not draft.profile.name.strip():
        raise ValueError("Name is required.")
    if not profile and not summary and not kept:
        raise ValueError("Choose at least one record to add.")
    for entry in kept:
        if entry.section in {"employment", "leadership"}:
            if not entry.organization.strip() or not entry.title.strip():
                raise ValueError("Organization and title are required.")
        elif entry.section == "project":
            if not entry.name.strip():
                raise ValueError("Project name is required.")
        elif entry.section == "education":
            if not entry.institution.strip():
                raise ValueError("Institution is required.")
        elif entry.section == "skills":
            if not entry.name.strip():
                raise ValueError("Skill group name is required.")
            if not [tool for tool in entry.tools if tool.strip()]:
                raise ValueError(f"Add at least one skill to {entry.name.strip()}.")
        elif entry.section == "interests":
            if not entry.body.strip():
                raise ValueError("Interest text is required.")
        else:
            raise ValueError("Choose a section for each included record.")
        if entry.section in KIND:
            try:
                _historical(entry)
            except ValidationError as exc:
                raise ValueError(_message(exc)) from exc


def _historical(entry: ImportEntry) -> HistoricalItemWrite:
    return HistoricalItemWrite(
        kind=KIND[entry.section],
        name=entry.name.strip() or None,
        subtitle=entry.subtitle.strip() or None,
        organization=entry.organization.strip() or None,
        location=entry.location.strip() or None,
        title=entry.title.strip() or None,
        date_label=_role_label(entry),
        start_year=entry.start_year,
        start_month=entry.start_month,
        end_year=None if entry.is_current else entry.end_year,
        end_month=None if entry.is_current else entry.end_month,
        is_current=entry.is_current,
        bullets=[bullet.strip() for bullet in entry.bullets if bullet.strip()],
    )


def _role_label(entry: ImportEntry) -> str:
    if entry.date_label.strip():
        return entry.date_label.strip()
    return historical_date(
        {
            "date_label": "",
            "start_year": entry.start_year,
            "start_month": entry.start_month,
            "end_year": None if entry.is_current else entry.end_year,
            "end_month": None if entry.is_current else entry.end_month,
            "is_current": entry.is_current,
        }
    )


def _graduation_label(entry: ImportEntry) -> str:
    if entry.display_date.strip():
        return entry.display_date.strip()
    if not entry.graduation_year:
        return ""
    if entry.graduation_month:
        return f"{MONTHS[entry.graduation_month]} {entry.graduation_year}"
    return str(entry.graduation_year)


async def _unique_label(conn, user_id, label: str) -> str:
    base = (label or "Imported profile").strip()[:120] or "Imported profile"
    candidate = base
    number = 2
    while await _profile_label_taken(conn, user_id, candidate):
        suffix = f" ({number})"
        candidate = f"{base[: 120 - len(suffix)]}{suffix}"
        number += 1
    return candidate


async def _warnings(conn, user_id, entries: list[ImportEntry]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if entry.section in {"employment", "leadership"}:
            row = await many(
                conn,
                """SELECT id FROM content_items
                   WHERE user_id=%s AND kind=%s AND archived_at IS NULL
                     AND lower(organization)=lower(%s) AND lower(title)=lower(%s)
                   LIMIT 1""",
                (user_id, entry.section, entry.organization.strip(), entry.title.strip()),
            )
            text = f"{entry.organization.strip()} — {entry.title.strip()} is already in your library."
        elif entry.section == "education":
            row = await many(
                conn,
                """SELECT id FROM education_items
                   WHERE user_id=%s AND archived_at IS NULL AND lower(institution)=lower(%s)
                   LIMIT 1""",
                (user_id, entry.institution.strip()),
            )
            text = f"{entry.institution.strip()} is already in your library."
        else:
            continue
        if row and text not in seen:
            seen.add(text)
            found.append(text)
    return found


async def _place(conn, composition_id, rows, destination_section, destination_type, parent_id) -> None:
    for index, row in enumerate(rows):
        await conn.execute(
            """INSERT INTO composition_bullets(
                   composition_id,bullet_id,variant_id,destination_section,destination_parent_type,
                   destination_parent_id,sort_order,wording_snapshot,snapshot_source_updated_at
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                composition_id,
                row["bullet_id"],
                row["variant_id"],
                destination_section,
                destination_type,
                parent_id,
                index,
                row["body"],
                row["updated_at"],
            ),
        )


async def _education_bullets(conn, user_id, education_id, bodies: list[str]):
    created = []
    for index, body in enumerate(bodies):
        bullet = await many(
            conn,
            """INSERT INTO bullets(user_id,education_item_id,section,sort_order)
               VALUES(%s,%s,'education',%s) RETURNING id""",
            (user_id, education_id, index),
        )
        variant = await many(
            conn,
            """INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order)
               VALUES(%s,%s,'Default',%s,true,0) RETURNING id,body,updated_at""",
            (user_id, bullet[0]["id"], body),
        )
        created.append(
            {
                "bullet_id": bullet[0]["id"],
                "variant_id": variant[0]["id"],
                "body": variant[0]["body"],
                "updated_at": variant[0]["updated_at"],
            }
        )
    return created


async def _historical_bullets(conn, user_id, item_id, library_section):
    await conn.execute(
        "UPDATE bullets SET section=%s WHERE user_id=%s AND parent_id=%s",
        (library_section, user_id, item_id),
    )
    return await many(
        conn,
        """SELECT b.id bullet_id, v.id variant_id, v.body, v.updated_at
           FROM bullets b
           JOIN bullet_variants v ON v.bullet_id=b.id AND v.is_default
           WHERE b.user_id=%s AND b.parent_id=%s
           ORDER BY b.sort_order, b.id""",
        (user_id, item_id),
    )


async def commit_import(conn, user_id, draft: ImportDraft, display_name: str) -> dict:
    _validate(draft)
    kept = _kept(draft)
    async with conn.transaction():
        warnings = await _warnings(conn, user_id, kept)
        profile_id = None
        header = Header(name=(display_name or "Resume").strip() or "Resume")
        if draft.profile.included:
            label = await _unique_label(conn, user_id, draft.profile.label)
            try:
                payload = ProfileWrite(
                    label=label,
                    name=draft.profile.name.strip()[:200],
                    phone=draft.profile.phone.strip(),
                    email=draft.profile.email.strip(),
                    linkedin_label=draft.profile.linkedin_label.strip()[:300],
                    linkedin_url=draft.profile.linkedin_url.strip(),
                )
            except ValidationError as exc:
                raise ValueError(_message(exc)) from exc
            row, error = await create_profile(conn, user_id, payload)
            if error or not row:
                raise ValueError("A profile with that name already exists.")
            profile_id = row["id"]
            header = Header(
                name=row["name"],
                phone=row["phone"] or "",
                email=row["email"] or "",
                linkedin_label=row["linkedin_label"] or "",
                linkedin_url=row["linkedin_url"] or "",
            )
        summary_id = None
        summary = ""
        if draft.summary.included and draft.summary.body.strip():
            try:
                payload = SummaryWrite(
                    name=(draft.summary.name.strip() or "Imported summary")[:120],
                    body=draft.summary.body.strip(),
                )
            except ValidationError as exc:
                raise ValueError(_message(exc)) from exc
            row = await create_summary(conn, user_id, payload)
            summary_id = row["id"]
            summary = row["body"]

        work: list[Experience] = []
        projects: list[Project] = []
        leadership: list[Experience] = []
        education: list[Education] = []
        tools: list[ToolGroup] = []
        interests: list[str] = []
        interest_items: list[dict] = []
        links: list[tuple[str, object]] = []
        placements: list[tuple] = []

        for entry in kept:
            if entry.section in KIND:
                payload = _historical(entry)
                item_id = await add_item(conn, user_id, payload)
                bullets = await _historical_bullets(
                    conn, user_id, item_id, LIBRARY_SECTION[entry.section]
                )
                rendered = {
                    "id": str(item_id),
                    "date": payload.date_label,
                    "bullets": [row["body"] for row in bullets],
                }
                if entry.section == "project":
                    projects.append(Project(name=payload.name or "", subtitle=payload.subtitle or "", **rendered))
                    links.append(("projects", item_id))
                else:
                    target = work if entry.section == "employment" else leadership
                    target.append(
                        Experience(
                            organization=payload.organization or "",
                            location=payload.location or "",
                            title=payload.title or "",
                            **rendered,
                        )
                    )
                    links.append(
                        ("work_experience" if entry.section == "employment" else "leadership", item_id)
                    )
                destination, parent_type = DESTINATION[entry.section]
                placements.append((bullets, destination, parent_type, item_id))
            elif entry.section == "education":
                label = _graduation_label(entry)
                try:
                    payload = EducationWrite(
                        institution=entry.institution.strip(),
                        college_school=entry.college_school.strip(),
                        location=entry.location.strip(),
                        degree_type=entry.degree_type.strip(),
                        degree_major=entry.degree_major.strip(),
                        graduation_year=entry.graduation_year,
                        graduation_month=entry.graduation_month,
                        display_date=label,
                    )
                except ValidationError as exc:
                    raise ValueError(_message(exc)) from exc
                row = await create_education(conn, user_id, payload)
                bodies = [bullet.strip() for bullet in entry.bullets if bullet.strip()]
                bullet_rows = await _education_bullets(conn, user_id, row["id"], bodies)
                rendered = _education_render(row)
                rendered["bullets"] = [item["body"] for item in bullet_rows]
                education.append(Education.model_validate(rendered))
                links.append(("education", row["id"]))
                placements.append((bullet_rows, "education", "education_item", row["id"]))
            elif entry.section == "skills":
                group = await create_tool_group(
                    conn, user_id, ToolGroupWrite(name=entry.name.strip()[:120])
                )
                names: list[str] = []
                for tool in entry.tools:
                    name = tool.strip()[:120]
                    if not name:
                        continue
                    await create_tool(conn, user_id, ToolWrite(name=name, group_id=group["id"]))
                    names.append(name)
                tools.append(ToolGroup(id=str(group["id"]), name=group["name"], items=names))
                links.append(("tool_groups", group["id"]))
            elif entry.section == "interests":
                row = await create_interest(conn, user_id, InterestWrite(body=entry.body.strip()))
                interests.append(row["body"])
                interest_items.append({"id": str(row["id"]), "body": row["body"], "bullets": []})
                links.append(("personal_interests", row["id"]))

        resume = Resume(
            header=header,
            summary=summary,
            education=education,
            tool_groups=tools,
            projects=projects,
            work_experience=work,
            leadership=leadership,
            personal_interests=interests,
            personal_interest_items=interest_items,
        )
        composition = await create_composition(
            conn,
            user_id,
            None,
            "",
            resume,
            display_name=header.name,
        )
        await conn.execute(
            "UPDATE resume_compositions SET profile_id=%s, summary_variant_id=%s WHERE id=%s AND user_id=%s",
            (profile_id, summary_id, composition["id"], user_id),
        )
        orders: dict[str, int] = {}
        for section, item_id in links:
            order = orders.get(section, 0)
            orders[section] = order + 1
            await conn.execute(
                "INSERT INTO composition_items(composition_id,section,item_id,sort_order) VALUES(%s,%s,%s,%s)",
                (composition["id"], section, item_id, order),
            )
        for bullets, destination, parent_type, parent_id in placements:
            await _place(conn, composition["id"], bullets, destination, parent_type, parent_id)
        return {"composition_id": composition["id"], "warnings": warnings}

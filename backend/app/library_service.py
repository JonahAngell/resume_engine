
import hashlib, json
from pathlib import Path
from uuid import UUID
from .schemas import Resume


async def import_seed(
    conn, user_id: UUID, seed_path: Path, seed_key: str
) -> tuple[bool, UUID]:
    raw = seed_path.read_bytes()
    resume = Resume.model_validate_json(raw)
    digest = hashlib.sha256(raw).hexdigest()
    existing = await (
        await conn.execute(
            "SELECT composition_id, seed_sha256 FROM seed_imports WHERE user_id=%s AND seed_key=%s",
            (user_id, seed_key),
        )
    ).fetchone()
    if existing:
        if existing[1] != digest:
            raise ValueError(
                "Seed key already exists with different content; use a new seed key."
            )
        return False, existing[0]
    data = resume.model_dump()
    async with conn.transaction():
        profile_id = (
            await (
                await conn.execute(
                    "INSERT INTO profiles(user_id,label,name,phone,email,linkedin_label,linkedin_url,sort_order) VALUES (%s,'Default',%s,%s,%s,%s,%s,0) RETURNING id",
                    (
                        user_id,
                        data["header"]["name"],
                        data["header"]["phone"],
                        data["header"]["email"],
                        data["header"]["linkedin_label"],
                        data["header"]["linkedin_url"],
                    ),
                )
            ).fetchone()
        )[0]
        summary_id = (
            await (
                await conn.execute(
                    "INSERT INTO summary_variants(user_id,name,body,sort_order) VALUES (%s,'Seed summary',%s,0) RETURNING id",
                    (user_id, data["summary"]),
                )
            ).fetchone()
        )[0]
        education_ids = []
        for i, item in enumerate(data["education"]):
            education_id = (
                await (
                    await conn.execute(
                        "INSERT INTO education_items(user_id,institution,location,degree,graduation_date,sort_order) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                        (
                            user_id,
                            item["institution"],
                            item["location"],
                            item["degree"],
                            item["graduation_date"],
                            i,
                        ),
                    )
                ).fetchone()
            )[0]
            education_ids.append(education_id)
            item["id"] = str(education_id)
        tool_group_ids = []
        for gi, group in enumerate(data["tool_groups"]):
            gid = (
                await (
                    await conn.execute(
                        "INSERT INTO tool_groups(user_id,name,sort_order) VALUES (%s,%s,%s) RETURNING id",
                        (user_id, group["name"], gi),
                    )
                ).fetchone()
            )[0]
            tool_group_ids.append(gid)
            group["id"] = str(gid)
            for ti, name in enumerate(group["items"]):
                await conn.execute(
                    "INSERT INTO tools(user_id,group_id,name,sort_order) VALUES (%s,%s,%s,%s)",
                    (user_id, gid, name, ti),
                )
        historical_ids = {"project": [], "employment": [], "leadership": []}
        bullet_selections = []

        async def add_items(kind, items):
            for i, item in enumerate(items):
                parent = (
                    await (
                        await conn.execute(
                            "INSERT INTO content_items(user_id,kind,name,subtitle,organization,location,title,date_label,sort_order) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                            (
                                user_id,
                                kind,
                                item.get("name"),
                                item.get("subtitle"),
                                item.get("organization"),
                                item.get("location"),
                                item.get("title"),
                                item["date"],
                                i,
                            ),
                        )
                    ).fetchone()
                )[0]
                historical_ids[kind].append(parent)
                item["id"] = str(parent)
                for bi, body in enumerate(item["bullets"]):
                    bullet = (
                        await (
                            await conn.execute(
                                "INSERT INTO bullets(user_id,parent_id,sort_order) VALUES (%s,%s,%s) RETURNING id",
                                (user_id, parent, bi),
                            )
                        ).fetchone()
                    )[0]
                    variant = (
                        await (
                            await conn.execute(
                                "INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order) VALUES (%s,%s,'Seed wording',%s,true,0) RETURNING id",
                                (user_id, bullet, body),
                            )
                        ).fetchone()
                    )[0]
                    bullet_selections.append((bullet, variant, bi, parent, kind, body))

        await add_items("project", data["projects"])
        await add_items("employment", data["work_experience"])
        await add_items("leadership", data["leadership"])
        interest_ids = []
        data["personal_interest_items"] = []
        for i, body in enumerate(data["personal_interests"]):
            interest_id = (
                await (
                    await conn.execute(
                        "INSERT INTO interests(user_id,body,sort_order) VALUES (%s,%s,%s) RETURNING id",
                        (user_id, body, i),
                    )
                ).fetchone()
            )[0]
            interest_ids.append(interest_id)
            data["personal_interest_items"].append(
                {"id": str(interest_id), "body": body, "bullets": []}
            )
        composition = (
            await (
                await conn.execute(
                    "INSERT INTO resume_compositions(user_id,name,summary_variant_id,profile_id,render_payload) VALUES (%s,'Seed Resume',%s,%s,%s::jsonb) RETURNING id",
                    (user_id, summary_id, profile_id, json.dumps(data)),
                )
            ).fetchone()
        )[0]
        for i, item_id in enumerate(education_ids):
            await conn.execute(
                "INSERT INTO composition_items(composition_id,section,item_id,sort_order) VALUES(%s,'education',%s,%s)",
                (composition, item_id, i),
            )
        for i, item_id in enumerate(tool_group_ids):
            await conn.execute(
                "INSERT INTO composition_items(composition_id,section,item_id,sort_order) VALUES(%s,'tool_groups',%s,%s)",
                (composition, item_id, i),
            )
        for kind, section in (
            ("project", "projects"),
            ("employment", "work_experience"),
            ("leadership", "leadership"),
        ):
            for i, item_id in enumerate(historical_ids[kind]):
                await conn.execute(
                    "INSERT INTO composition_items(composition_id,section,item_id,sort_order) VALUES(%s,%s,%s,%s)",
                    (composition, section, item_id, i),
                )
        for i, item_id in enumerate(interest_ids):
            await conn.execute(
                "INSERT INTO composition_items(composition_id,section,item_id,sort_order) VALUES(%s,'personal_interests',%s,%s)",
                (composition, item_id, i),
            )
        for bullet_id, variant_id, order, parent_id, kind, body in bullet_selections:
            section = {"project":"projects","employment":"work_experience","leadership":"leadership"}[kind]
            await conn.execute(
                "INSERT INTO composition_bullets(composition_id,bullet_id,variant_id,destination_section,destination_parent_type,destination_parent_id,sort_order,wording_snapshot,snapshot_source_updated_at) VALUES(%s,%s,%s,%s,'content_item',%s,%s,%s,now())",
                (composition, bullet_id, variant_id, section, parent_id, order, body),
            )
        await conn.execute(
            "INSERT INTO seed_imports(user_id,seed_key,seed_sha256,composition_id) VALUES (%s,%s,%s,%s)",
            (user_id, seed_key, digest, composition),
        )
    return True, composition

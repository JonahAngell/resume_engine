import base64
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .schemas import Resume
from .phase2l import preprocess_resume

TEMPLATE_DIR = Path(__file__).parent / "templates"
FONT_DIR = TEMPLATE_DIR / "fonts"
TEMPLATE_STYLES = {"classic", "sheets", "harvard", "dais", "sre"}
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html", "xml"])
)

_FONT_FACES = (
    ("EB Garamond", 400, "normal", "eb-garamond-400.woff2"),
    ("EB Garamond", 700, "normal", "eb-garamond-700.woff2"),
    ("EB Garamond", 400, "italic", "eb-garamond-400-italic.woff2"),
    ("EB Garamond", 700, "italic", "eb-garamond-700-italic.woff2"),
    ("Carlito", 400, "normal", "carlito-400.woff2"),
    ("Carlito", 700, "normal", "carlito-700.woff2"),
    ("Carlito", 400, "italic", "carlito-400-italic.woff2"),
    ("Carlito", 700, "italic", "carlito-700-italic.woff2"),
    ("Tinos", 400, "normal", "tinos-400.woff2"),
    ("Tinos", 700, "normal", "tinos-700.woff2"),
    ("Tinos", 400, "italic", "tinos-400-italic.woff2"),
    ("Tinos", 700, "italic", "tinos-700-italic.woff2"),
)


def normalize_template_style(value: str | None, fallback: str = "classic") -> str:
    candidate = value if value in TEMPLATE_STYLES else fallback
    return candidate if candidate in TEMPLATE_STYLES else "classic"


def normalize_skill_row_max(value, fallback: int = 4) -> int:
    try:
        number = int(value if value is not None else fallback)
    except (TypeError, ValueError):
        number = fallback
    return min(20, max(1, number))


def skill_table(groups, row_max: int) -> dict:
    """Fill each skill group down `row_max` rows, then wrap into the next column."""
    limit = normalize_skill_row_max(row_max)
    blocks = []
    height = 0
    for index, group in enumerate(groups or []):
        items = [str(item).strip() for item in (group.get("items") or []) if str(item).strip()]
        columns = [items[start : start + limit] for start in range(0, len(items), limit)] or [[]]
        height = max(height, *(len(column) for column in columns))
        name = str(group.get("name") or "").strip()
        blocks.append(
            {
                "id": group.get("id") or index,
                "label": name if name.endswith(":") else f"{name}:",
                "columns": columns,
                "bullets": group.get("bullets") or [],
            }
        )
    return {"blocks": blocks, "rows": height}


# The only embedded family each template's CSS asks for; "classic" uses system Arial.
STYLE_FONTS = {"classic": None, "sheets": "EB Garamond", "harvard": "Carlito", "sre": "Carlito", "dais": "Tinos"}


def _font_css(only_family: str) -> str:
    rules = []
    for family, weight, style, filename in _FONT_FACES:
        if family != only_family:
            continue
        path = FONT_DIR / filename
        if not path.exists():
            continue
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            "@font-face{"
            f"font-family:'{family}';"
            f"font-style:{style};"
            f"font-weight:{weight};"
            f"src:url(data:font/woff2;base64,{encoded}) format('woff2');"
            "font-display:swap;"
            "}"
        )
    return "\n".join(rules)


# Built once at import; each response embeds only its template's family (about 100 KB, or none).
FONT_CSS_BY_FAMILY = {family: _font_css(family) for family in {f for f, *_ in _FONT_FACES}}


def font_css_for(style: str) -> str:
    family = STYLE_FONTS.get(style)
    return FONT_CSS_BY_FAMILY.get(family, "") if family else ""


def render_resume(resume: Resume | dict, measure: bool = True, renderer_contract_version: str = "legacy", sort_modes: dict | None = None, date_format: str = "long", template_style: str = "classic", skill_row_max: int = 4) -> str:
    data = resume.model_dump() if isinstance(resume, Resume) else resume
    style = normalize_template_style(template_style)
    prepared = preprocess_resume(data, sort_modes, date_format)
    return env.get_template("resume.html").render(
        resume=prepared, measure=measure,
        renderer_contract_version=renderer_contract_version,
        template_style=style,
        font_css=font_css_for(style),
        skill_table=skill_table(prepared.get("tool_groups"), skill_row_max),
    )

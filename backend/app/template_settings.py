"""Appearance settings for custom templates, and the CSS they add to a built-in style.

A custom template is a built-in style (its layout and section names) plus settings. Settings are
always complete: a new template copies its base's defaults, and stored settings are merged over
them when read, so a field added later still has a value. Only fields that differ from the base's
defaults produce CSS, so a template that changes nothing renders exactly like its base.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BASE_STYLES = ("classic", "sheets", "harvard", "dais", "sre")
BASE_LABELS = {"classic": "Default", "sheets": "Ruled Serif", "harvard": "Harvard Style", "dais": "Times Serif", "sre": "Skill Table"}

# id -> (label, CSS font-family stack, embedded family or None for a system font)
FONTS: dict[str, tuple[str, str, str | None]] = {
    "arial": ("Arial", "Arial, 'Liberation Sans', Helvetica, sans-serif", None),
    "carlito": ("Carlito (Calibri-like)", "Carlito, Calibri, 'Segoe UI', sans-serif", "Carlito"),
    "lato": ("Lato", "Lato, 'Helvetica Neue', Arial, sans-serif", "Lato"),
    "inter": ("Inter", "Inter, 'Segoe UI', Arial, sans-serif", "Inter"),
    "eb-garamond": ("EB Garamond", "'EB Garamond', Garamond, 'Times New Roman', serif", "EB Garamond"),
    "tinos": ("Tinos (Times-like)", "Tinos, 'Liberation Serif', 'Times New Roman', Times, serif", "Tinos"),
    "source-serif": ("Source Serif 4", "'Source Serif 4', Georgia, 'Times New Roman', serif", "Source Serif 4"),
}
BULLETS = {"disc": "•", "dash": "–", "square": "▪", "circle": "◦", "arrow": "›"}

FontId = Literal["arial", "carlito", "lato", "inter", "eb-garamond", "tinos", "source-serif"]
BulletId = Literal["disc", "dash", "square", "circle", "arrow"]
ToolsLayout = Literal["table", "inline"]
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class Sizes(BaseModel):
    """Font sizes in points."""

    model_config = ConfigDict(extra="forbid")
    name: float = Field(ge=10, le=32)
    heading: float = Field(ge=8, le=18)
    title: float = Field(ge=8, le=16)
    body: float = Field(ge=8, le=14)
    contact: float = Field(ge=7, le=14)


class Margins(BaseModel):
    """Page margins in inches."""

    model_config = ConfigDict(extra="forbid")
    top: float = Field(ge=0.3, le=1.25)
    right: float = Field(ge=0.3, le=1.25)
    bottom: float = Field(ge=0.15, le=1.25)
    left: float = Field(ge=0.3, le=1.25)


class TemplateSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    font: FontId
    sizes: Sizes
    text_color: str
    accent_color: str
    rule_color: str
    heading_case: Literal["upper", "normal"]
    heading_bold: bool
    heading_rule: Literal["none", "underline", "box"]
    bullet: BulletId
    date_position: Literal["right", "inline"]
    margins: Margins
    line_height: float = Field(ge=1.0, le=1.6)
    section_gap: float = Field(ge=0, le=24, description="Points after each section.")
    bullet_gap: float = Field(ge=0, le=8, description="Points after each bullet.")
    tools_layout: ToolsLayout

    @field_validator("text_color", "accent_color", "rule_color")
    @classmethod
    def _hex(cls, value: str) -> str:
        if not _HEX.match(value or ""):
            raise ValueError("Use a colour like #1f2a44")
        return value.lower()


def _defaults(font, sizes, rule_color, case, rule, margins, line_height, section_gap, bullet_gap, tools, accent="#17233d"):
    name, heading, title, body, contact = sizes
    top, right, bottom, left = margins
    return {
        "font": font,
        "sizes": {"name": name, "heading": heading, "title": title, "body": body, "contact": contact},
        "text_color": "#17233d",
        "accent_color": accent,
        "rule_color": rule_color,
        "heading_case": case,
        "heading_bold": True,
        "heading_rule": rule,
        "bullet": "disc",
        "date_position": "right",
        "margins": {"top": top, "right": right, "bottom": bottom, "left": left},
        "line_height": line_height,
        "section_gap": section_gap,
        "bullet_gap": bullet_gap,
        "tools_layout": tools,
    }


# What each built-in style looks like, in settings terms (taken from resume.html).
BASE_DEFAULTS: dict[str, dict] = {
    "classic": _defaults("arial", (20, 10, 10, 10, 8.5), "#456fa8", "upper", "underline", (0.55, 0.62, 0.55, 0.62), 1.15, 7.5, 0.75, "inline"),
    "sheets": _defaults("eb-garamond", (18, 11, 12, 12, 8.5), "#222222", "upper", "box", (0.5, 0.5, 0.5, 0.5), 1.15, 7.5, 0.75, "inline"),
    "harvard": _defaults("carlito", (16, 12, 11, 11, 8.5), "#17233d", "normal", "none", (0.89, 0.42, 0.19, 0.42), 1.15, 7.5, 0.75, "inline"),
    "dais": _defaults("tinos", (14, 11, 11, 11, 8.5), "#17233d", "upper", "none", (0.31, 0.5, 0.38, 0.5), 1.15, 7.5, 0.75, "inline"),
    "sre": _defaults("carlito", (14, 11, 11, 11, 11), "#000000", "upper", "underline", (0.5, 0.5, 0.5, 0.5), 1.22, 0, 0, "table"),
}


def defaults_for(base_style: str) -> dict:
    return _copy(BASE_DEFAULTS.get(base_style) or BASE_DEFAULTS["classic"])


def _copy(value: dict) -> dict:
    return {key: dict(item) if isinstance(item, dict) else item for key, item in value.items()}


def resolve_settings(base_style: str, stored: dict | None) -> dict:
    """The full, valid settings for a template: stored values over the base's defaults.

    A stored value that no longer validates (a removed font, an out-of-range number) falls back
    to the default for that field, so an old template always renders.
    """
    merged = defaults_for(base_style)
    for key, value in (stored or {}).items():
        if key not in merged:
            continue
        if isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **{k: v for k, v in value.items() if k in merged[key]}}
        else:
            merged[key] = value
    try:
        return TemplateSettings.model_validate(merged).model_dump()
    except ValueError:
        fallback = defaults_for(base_style)
        for key in list(merged):
            candidate = {**fallback, key: merged[key]}
            try:
                TemplateSettings.model_validate(candidate)
                fallback[key] = merged[key]
            except ValueError:
                continue
        return TemplateSettings.model_validate(fallback).model_dump()


def strict_settings(base_style: str, settings: dict | None) -> dict:
    """Settings from a request: merged over the base's defaults, then validated. Raises
    pydantic.ValidationError (a ValueError) instead of falling back, so the user sees the error."""
    merged = defaults_for(base_style)
    for key, value in (settings or {}).items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return TemplateSettings.model_validate(merged).model_dump()


def _changed(base_style: str, settings: dict) -> dict:
    defaults = defaults_for(base_style)
    out = {}
    for key, value in settings.items():
        if isinstance(value, dict):
            diff = {k: v for k, v in value.items() if defaults.get(key, {}).get(k) != v}
            if diff:
                out[key] = diff
        elif defaults.get(key) != value:
            out[key] = value
    return out


def embedded_family(settings: dict | None) -> str | None:
    if not settings:
        return None
    return FONTS.get(settings.get("font"), (None, None, None))[2]


def _num(value: float) -> str:
    return f"{value:g}"


def settings_css(base_style: str, settings: dict | None) -> str:
    """CSS for the settings that differ from the base style. Every rule is scoped under
    `body.custom-template`, which outranks the `.template-<style>` rules it overrides."""
    if not settings:
        return ""
    changed = _changed(base_style, settings)
    if not changed:
        return ""
    s = settings
    root = "body.custom-template"
    rules: list[str] = []

    def add(selector: str, body: str) -> None:
        selectors = ", ".join(f"{root} {part}".rstrip() for part in selector.split(","))
        rules.append(f"{selectors} {{ {body} }}")

    if "font" in changed:
        add("", f"font-family: {FONTS[s['font']][1]};")
    sizes = changed.get("sizes", {})
    if "body" in sizes:
        add("", f"font-size: {_num(s['sizes']['body'])}pt;")
    if "name" in sizes:
        add(".header h1", f"font-size: {_num(s['sizes']['name'])}pt;")
    if "heading" in sizes:
        add(".section-title", f"font-size: {_num(s['sizes']['heading'])}pt;")
    if "title" in sizes:
        add(".row b, .row .role", f"font-size: {_num(s['sizes']['title'])}pt;")
    if "contact" in sizes:
        add(".contact", f"font-size: {_num(s['sizes']['contact'])}pt;")
    if "text_color" in changed:
        add("", f"color: {s['text_color']};")
    if "accent_color" in changed:
        add(".header h1, .section-title", f"color: {s['accent_color']};")
    if "heading_case" in changed:
        add(".section-title", "text-transform: uppercase;" if s["heading_case"] == "upper" else "text-transform: none; letter-spacing: 0;")
    if "heading_bold" in changed:
        add(".section-title", f"font-weight: {700 if s['heading_bold'] else 400};")
    if "heading_rule" in changed:
        rule = s["heading_rule"]
        line = f"1px solid {s['rule_color']}"
        if rule == "none":
            add(".section-title", "border-top: 0; border-bottom: 0; padding-top: 0; padding-bottom: 0;")
        elif rule == "underline":
            add(".section-title", f"border-top: 0; border-bottom: {line}; padding-top: 0; padding-bottom: 2px;")
        else:
            add(".section-title", f"border-top: {line}; border-bottom: {line}; padding: 1px 0;")
    elif "rule_color" in changed:
        add(".section-title", f"border-color: {s['rule_color']};")
    if "bullet" in changed:
        mark = BULLETS[s["bullet"]]
        if base_style == "sre":
            add("li::before", f'content: "{mark}";')
        else:
            add("ul", "list-style: none; padding-left: 14pt;")
            add("li", "position: relative;")
            add("li::before", f'content: "{mark}"; position: absolute; left: -11pt;')
    if "date_position" in changed and s["date_position"] == "inline":
        add(".row", "justify-content: flex-start; flex-wrap: wrap; gap: 0;")
        add(".row > :not(:first-child):not(:empty)::before", 'content: " · "; white-space: pre; font-weight: 400; font-style: normal;')
    if "margins" in changed:
        m = s["margins"]
        add(
            "",
            f"--pad-top: {_num(m['top'])}in; --pad-right: {_num(m['right'])}in; "
            f"--pad-bottom: {_num(m['bottom'])}in; --pad-left: {_num(m['left'])}in; "
            f"--content-height: {_num(round(11 - m['top'] - m['bottom'], 4))}in;",
        )
    if "line_height" in changed:
        add(", li, .item, .skill-table th, .skill-table td", f"line-height: {_num(s['line_height'])};")
    if "section_gap" in changed:
        add(".section", f"margin-bottom: {_num(s['section_gap'])}pt;")
    if "bullet_gap" in changed:
        add("li", f"margin-top: 0; margin-bottom: {_num(s['bullet_gap'])}pt;")
    return "\n".join(rules)


def options() -> dict:
    """Choices and limits for the designer UI."""
    limits = {}
    for name, model in (("sizes", Sizes), ("margins", Margins), ("", TemplateSettings)):
        for field, info in model.model_fields.items():
            bounds = {m.__class__.__name__: getattr(m, m.__class__.__name__.lower(), None) for m in info.metadata}
            if "Ge" in bounds or "Le" in bounds:
                limits[f"{name}.{field}" if name else field] = {"min": bounds.get("Ge"), "max": bounds.get("Le")}
    return {
        "fonts": [{"id": key, "label": label} for key, (label, *_rest) in FONTS.items()],
        "bullets": [{"id": key, "mark": mark} for key, mark in BULLETS.items()],
        "bases": [{"id": key, "label": BASE_LABELS[key], "defaults": defaults_for(key)} for key in BASE_STYLES],
        "limits": limits,
    }

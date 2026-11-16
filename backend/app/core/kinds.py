"""Submittal kinds: a per-project list in project.settings["submittal_kinds"].

Records store the kind's code, so renaming a kind changes how it shows everywhere without touching
records (or their approval stamps). Records made before the list existed hold the name text itself;
kind_name() still resolves those.
"""
import secrets

from app.models.core import Project

DEFAULT_SUBMITTAL_KINDS = [
    {"code": "material", "name_ar": "مواد", "name_en": "Material"},
    {"code": "shop_drawing", "name_ar": "مخططات تنفيذية", "name_en": "Shop drawing"},
    {"code": "method_statement", "name_ar": "طريقة تنفيذ", "name_en": "Method statement"},
    {"code": "sample", "name_ar": "عينة", "name_en": "Sample"},
    {"code": "document", "name_ar": "وثيقة", "name_en": "Document"},
]


def submittal_kinds(project: Project) -> list[dict]:
    saved = (project.settings or {}).get("submittal_kinds")
    if saved is None:
        return [{**k, "active": True} for k in DEFAULT_SUBMITTAL_KINDS]
    return [{"active": True, **k} for k in saved]


def active_codes(project: Project) -> set[str]:
    return {k["code"] for k in submittal_kinds(project) if k["active"]}


def kind_name(project: Project, value: str | None) -> dict | None:
    """{"ar", "en"} for a stored value: a code from the project's list, or legacy name text."""
    if not value:
        return None
    for k in submittal_kinds(project) + DEFAULT_SUBMITTAL_KINDS:
        if value in (k["code"], k["name_ar"], k["name_en"]):
            return {"ar": k["name_ar"], "en": k["name_en"]}
    return {"ar": value, "en": value}


def new_code() -> str:
    return "k_" + secrets.token_hex(3)

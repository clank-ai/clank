"""An entry's properties, for the agent (design 0010 §4): each value as plain text (a relation as the titles of the
entries it points to, looked up by the caller), and each property of a data source described by its name, its type,
its options (a select's, a multi-select's or a status's) and, for a relation, the data source it points to."""

from collections.abc import Callable
from typing import Any

OPTIONS = ("select", "multi_select", "status")


def property_text(value: dict[str, Any], title_of: Callable[[str], str | None]) -> str:
    """A property's value as plain text; `title_of` names a related entry by its id (None when it cannot)."""
    kind = value.get("type", "")
    found = value.get(kind)
    if kind in ("title", "rich_text"):
        return "".join(str(run.get("plain_text", "")) for run in found or [])
    if kind == "number":
        return _number(found)
    if kind in ("select", "status"):
        return str((found or {}).get("name", ""))
    if kind == "multi_select":
        return ", ".join(str(each.get("name", "")) for each in found or [])
    if kind == "date":
        return _date(found)
    if kind == "checkbox":
        return "yes" if found else "no"
    if kind in ("url", "email", "phone_number", "created_time", "last_edited_time"):
        return str(found or "")
    if kind == "relation":
        return "; ".join(title_of(each["id"]) or each["id"] for each in found or [])
    if kind in ("people", "created_by", "last_edited_by"):
        people = found if isinstance(found, list) else [found or {}]
        return ", ".join(str(each.get("name") or each.get("id", "")) for each in people)
    if kind == "files":
        return ", ".join(str(each.get("name", "")) for each in found or [])
    if kind == "formula":
        inner = (found or {}).get("type", "")
        return property_text({"type": inner, inner: (found or {}).get(inner)}, title_of) if inner else ""
    if kind == "rollup":
        return _rollup(found or {}, title_of)
    if kind == "unique_id":
        prefix, number = (found or {}).get("prefix"), (found or {}).get("number")
        return f"{prefix}-{number}" if prefix else str(number if number is not None else "")
    if kind == "verification":
        return str((found or {}).get("state", ""))
    return ""


def property_schema(name: str, value: dict[str, Any], source_name: Callable[[str], str | None]) -> dict[str, Any]:
    """A data source's property, described: its name and type, its options, or the data source a relation points to
    (by its name when it is shared, else its id)."""
    kind = value.get("type", "")
    described: dict[str, Any] = {"name": name, "type": kind}
    config = value.get(kind) or {}
    if kind in OPTIONS:
        described["options"] = [str(option.get("name", "")) for option in config.get("options") or []]
    if kind == "relation":
        target = str(config.get("data_source_id") or "")
        described["points_to"] = source_name(target) or target
    return described


def _number(found: Any) -> str:
    if found is None:
        return ""
    if isinstance(found, float) and found.is_integer():
        return str(int(found))
    return str(found)


def _date(found: Any) -> str:
    if not found:
        return ""
    start, end = found.get("start") or "", found.get("end")
    return f"{start} → {end}" if end else str(start)


def _rollup(found: dict[str, Any], title_of: Callable[[str], str | None]) -> str:
    kind = found.get("type", "")
    if kind == "array":
        return ", ".join(property_text(each, title_of) for each in found.get("array") or [])
    if kind == "number":
        return _number(found.get("number"))
    if kind == "date":
        return _date(found.get("date"))
    return ""

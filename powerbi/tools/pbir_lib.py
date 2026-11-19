"""Shared PBIR (Power BI report JSON) building blocks for every report in the suite.

Report-specific design (palette, icons, navigation rail, backgrounds, pages)
lives in each report's own builder; everything here is generic Power BI
report JSON that all three reports need. Extracted from
build_overview_page.py in ARCH-01 without changing its output (proven by
regenerating Report 01 byte-for-byte).
"""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
S_VISUAL = f"{SCHEMA}/visualContainer/2.13.0/schema.json"
S_PAGE = f"{SCHEMA}/page/2.1.0/schema.json"
S_PAGES = f"{SCHEMA}/pagesMetadata/1.1.0/schema.json"
S_BOOKMARK = f"{SCHEMA}/bookmark/2.1.0/schema.json"
S_BOOKMARKS = f"{SCHEMA}/bookmarksMetadata/1.0.0/schema.json"


def literal(value) -> dict:
    """Formatting values are expressions: 'text' in quotes, numbers with D, booleans as-is."""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        text = f"{value}D"
    else:
        text = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def colour(hex_code: str) -> dict:
    return {"solid": {"color": literal(hex_code)}}


def props(selector: dict | None = None, **kwargs) -> list[dict]:
    entry = {"properties": {k: (v if isinstance(v, dict) else literal(v)) for k, v in kwargs.items()}}
    if selector:
        entry["selector"] = selector
    return [entry]


def field(kind: str, table: str, name: str) -> dict:
    return {kind: {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def proj(kind: str, table: str, name: str, label: str | None = None) -> dict:
    p = {"field": field(kind, table, name), "queryRef": f"{table}.{name}", "nativeQueryRef": name}
    if label:
        p["displayName"] = label
    return p


def count_proj(table: str, column: str, label: str) -> dict:
    """Power BI's built-in 'Count of <column>' (an implicit aggregation, not a DAX measure)."""
    return {"field": {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Entity": table}},
                                                                 "Property": column}}, "Function": 5}},
            "queryRef": f"Count({table}.{column})", "nativeQueryRef": f"Count of {column}", "displayName": label}


def value_selector(table: str, column: str, value: str) -> dict:
    """Selector for one category value, e.g. attendance_status = 'Present'."""
    return {"data": [{"scopeId": {"Comparison": {
        "ComparisonKind": 0, "Left": field("Column", table, column), "Right": {"Literal": {"Value": f"'{value}'"}}}}}]}


def container(name, x, y, w, h, z, visual, hidden=False) -> dict:
    v = {"$schema": S_VISUAL, "name": name,
         "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
         "visual": visual}
    if hidden:
        v["isHidden"] = True
    return v


def textbox(runs_by_line: list[list[tuple[str, dict]]], align: str | None = None) -> dict:
    def para(runs):
        p = {"textRuns": [{"value": t, "textStyle": s} for t, s in runs]}
        if align:
            p["horizontalTextAlignment"] = align
        return p
    return {"visualType": "textbox", "objects": {"general": [{"properties": {
        "paragraphs": [para(r) for r in runs_by_line]}}]}}


def image_from_measure(table: str, measure: str) -> dict:
    """Image visual whose picture is the SVG data-URL returned by a measure."""
    return {"visualType": "image", "objects": {
        "general": props(imageUrl={"expr": field("Measure", table, measure)}),
        "imageScaling": props(imageScalingType="Fit")}}


def image(fname: str) -> dict:
    return {"visualType": "image", "objects": {
        "general": props(imageUrl={"expr": {"ResourcePackageItem": {
            "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": fname}}}),
        "imageScaling": props(imageScalingType="Fit")}}


# Power BI expects a full font STACK in visual formatting (learned from Desktop)


FONT = {"regular": "'Segoe UI', wf_segoe-ui_normal, helvetica, arial, sans-serif",
        "semibold": "'Segoe UI Semibold', wf_segoe-ui_semibold, helvetica, arial, sans-serif",
        "bold": "'Segoe UI Bold', wf_segoe-ui_bold, helvetica, arial, sans-serif"}


def button(text: str, *, link: dict | None, fg="#9BA8B9", fill: str | None = None, fill_alpha=0,
           hover_fill="#FFFFFF", hover_alpha=92, size=10, tooltip: str | None = None) -> dict:
    """Action button. fill_alpha / hover_alpha are TRANSPARENCY percentages (100 = invisible)."""
    objects = {
        # two entries: per-state text settings, plus the master "show text" switch
        "text": props({"id": "default"}, show=bool(text), text=text, fontColor=colour(fg),
                      fontSize=size, fontFamily=FONT["semibold"]) + props(show=bool(text)),
        "fill": props({"id": "default"}, show=True, fillColor=colour(fill or "#000000"),
                      transparency=100 - fill_alpha if fill else 100),
        "outline": props({"id": "default"}, show=False),
        "icon": props({"id": "default"}, show=False),
    }
    objects["fill"] += props({"id": "hover"}, show=True, fillColor=colour(hover_fill), transparency=hover_alpha)
    vco = {}
    if link:
        vco["visualLink"] = props(show=True, **link)
    if tooltip:
        vco.setdefault("visualLink", props(show=False))
        vco["visualLink"][0]["properties"]["tooltip"] = literal(tooltip)
    return {"visualType": "actionButton", "objects": objects, "visualContainerObjects": vco,
            "drillFilterOtherVisuals": True}


def shape(fill: str, transparency: int, outline: str | None = None, outline_transparency: int = 0) -> dict:
    """Rectangle shape. Like buttons, shapes keep formatting PER STATE: the
    values live under selector {"id": "default"}, plus a master 'show' entry."""
    d = {"id": "default"}
    objects = {
        "shape": props(tileShape="rectangle"),
        "fill": props(d, show=True, fillColor=colour(fill), transparency=transparency) + props(show=True),
        "outline": (props(d, show=True, lineColor=colour(outline), weight=1, transparency=outline_transparency)
                    + props(show=True)) if outline else (props(d, show=False) + props(show=False)),
    }
    return {"visualType": "shape", "objects": objects}


def bookmark_link(name: str) -> dict:
    return {"type": "Bookmark", "bookmark": name}


def page_link(page: str) -> dict:
    return {"type": "PageNavigation", "navigationSection": page}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def number_filter(name: str, table: str, column: str, value: int) -> dict:
    """Visual filter: <table>[<column>] = whole number (e.g. has_action = 0)."""
    return {"name": name, "field": field("Column", table, column), "type": "Categorical", "howCreated": "User",
            "filter": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                           "Values": [[{"Literal": {"Value": f"{value}L"}}]]}}}]}}


def category_filter(name: str, table: str, column: str, value: str) -> dict:
    """Visual/page filter: <table>[<column>] = value (no DAX needed)."""
    return {"name": name, "field": field("Column", table, column), "type": "Categorical", "howCreated": "User",
            "filter": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                           "Values": [[{"Literal": {"Value": f"'{value}'"}}]]}}}]}}

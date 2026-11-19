"""Check that the shared semantic model only changed ADDITIVELY since a validated baseline.

Why: three reports share one model (D41). A change made while building
Report 02 must never silently break Report 01. This script compares the TMDL
in the working tree with the TMDL at a validated git reference (default: the
tag `model-v1`) and FAILS if anything that existed at the baseline was
removed or changed:

  * a table, or its import source (partition query)
  * a column, or its data type / source column / calculated expression
  * a measure, or its DAX expression
  * a relationship (from/to columns), its cross-filter direction or active flag

New tables, columns, measures and relationships are fine: they are listed.
Things Power BI Desktop rewrites on its own (lineage tags, annotations, file
order, whitespace, DAX comments) are ignored. Formatting changes
(formatString, displayFolder, isHidden, a measure moving home table) are
reported as WARNINGS, not failures.

    python powerbi/tools/check_model_additive.py                  # vs tag model-v1
    python powerbi/tools/check_model_additive.py --base a899666   # vs a commit
Exit code 0 = additive only; 1 = breaking change found.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODEL_DIR = "powerbi/workforcedevelopmentanalytics.SemanticModel/definition"


@dataclass
class Model:
    tables: dict = field(default_factory=dict)          # table -> {"source": str}
    columns: dict = field(default_factory=dict)         # (table, column) -> {dataType, sourceColumn, expression, ...}
    measures: dict = field(default_factory=dict)        # name -> {table, expression, formatString, displayFolder}
    relationships: dict = field(default_factory=dict)   # (from, to) -> {crossFilteringBehavior, isActive}


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip("\t"))


def unquote(name: str) -> str:
    name = name.strip()
    return name[1:-1].replace("''", "'") if name.startswith("'") and name.endswith("'") else name


def normalise_dax(expr: str) -> str:
    """Compare meaning, not layout: drop -- and // comments, collapse whitespace."""
    out = []
    for line in expr.splitlines():
        line = re.split(r"\s--|^--|\s//|^//", line, maxsplit=1)[0]
        out.append(line)
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def read_expression(lines: list[str], i: int, first: str) -> tuple[str, int]:
    """Read an object's expression starting after '='. Handles ```fenced``` blocks,
    same-line expressions and indented continuation lines. Returns (text, next index)."""
    first = first.strip()
    body = []
    if first.startswith("```"):
        i += 1
        while i < len(lines) and lines[i].strip() != "```":
            body.append(lines[i]); i += 1
        return "\n".join(body), i + 1
    if first:
        body.append(first)
    i += 1
    base = indent_of(lines[i - 1])
    while i < len(lines) and (not lines[i].strip() or indent_of(lines[i]) >= base + 2):
        body.append(lines[i]); i += 1
    return "\n".join(body), i


def parse_table(text: str, model: Model) -> None:
    lines = text.splitlines()
    table = unquote(re.match(r"table\s+(.+)", lines[0]).group(1))
    model.tables[table] = {"source": ""}
    i = 1
    while i < len(lines):
        line = lines[i]
        if indent_of(line) != 1 or not line.strip():
            i += 1
            continue
        s = line.strip()
        m = re.match(r"measure\s+('(?:[^']|'')*'|\S+)\s*=\s*(.*)$", s)
        if m:
            name = unquote(m.group(1))
            expr, i = read_expression(lines, i, m.group(2))
            props, i = read_props(lines, i)
            model.measures[name] = {"table": table, "expression": normalise_dax(expr),
                                    "formatString": props.get("formatString"),
                                    "displayFolder": props.get("displayFolder"), "isHidden": props.get("isHidden")}
            continue
        m = re.match(r"column\s+('(?:[^']|'')*'|[^=\s]+)\s*(?:=\s*(.*))?$", s)
        if m:
            name = unquote(m.group(1))
            expr = ""
            if m.group(2) is not None:
                expr, i = read_expression(lines, i, m.group(2))
            else:
                i += 1
            props, i = read_props(lines, i)
            model.columns[(table, name)] = {"dataType": props.get("dataType"), "sourceColumn": props.get("sourceColumn"),
                                            "expression": normalise_dax(expr), "formatString": props.get("formatString"),
                                            "isHidden": props.get("isHidden")}
            continue
        m = re.match(r"partition\s+.+?=\s*\w+", s)
        if m:
            i += 1
            src = []
            while i < len(lines) and (not lines[i].strip() or indent_of(lines[i]) >= 2):
                src.append(lines[i].strip()); i += 1
            model.tables[table]["source"] = re.sub(r"\s+", " ", " ".join(x for x in src if not x.startswith("mode:"))).strip()
            continue
        i += 1


def read_props(lines: list[str], i: int) -> tuple[dict, int]:
    """Read 'key: value' property lines at indent 2 (annotations and blank lines skipped)."""
    props = {}
    while i < len(lines):
        line = lines[i]
        if line.strip() and indent_of(line) < 2:
            break
        m = re.match(r"\t\t(\w+)\s*:\s*(.*)$", line)
        if m:
            props[m.group(1)] = m.group(2).strip()
        elif re.match(r"\t\t(\w+)\s*$", line):          # boolean flags such as 'isHidden'
            props[line.strip()] = "true"
        i += 1
    return props, i


def parse_relationships(text: str, model: Model) -> None:
    current = None
    for line in text.splitlines():
        if line.startswith("relationship "):
            current = {}
            model.relationships.setdefault("__pending__", []).append(current)
        elif current is not None:
            m = re.match(r"\t(\w+)\s*:\s*(.*)$", line)
            if m:
                current[m.group(1)] = m.group(2).strip()
    for rel in model.relationships.pop("__pending__", []):
        key = (rel.get("fromColumn"), rel.get("toColumn"))
        model.relationships[key] = {"crossFilteringBehavior": rel.get("crossFilteringBehavior", "oneDirection"),
                                    "isActive": rel.get("isActive", "true")}


def parse_model(files: dict[str, str]) -> Model:
    """files: relative path -> TMDL text (paths relative to the definition folder)."""
    model = Model()
    for path, text in sorted(files.items()):
        if path.startswith("tables/"):
            parse_table(text, model)
        elif path == "relationships.tmdl":
            parse_relationships(text, model)
    return model


def compare(base: Model, new: Model) -> tuple[list[str], list[str], list[str]]:
    """Returns (breaking, warnings, added)."""
    breaking, warnings, added = [], [], []
    for t, info in base.tables.items():
        if t not in new.tables:
            breaking.append(f"table removed: {t}")
        elif info["source"] != new.tables[t]["source"]:
            breaking.append(f"table import source changed: {t}")
    added += [f"table: {t}" for t in new.tables if t not in base.tables]
    for key, info in base.columns.items():
        if key not in new.columns:
            breaking.append(f"column removed: {key[0]}[{key[1]}]")
            continue
        for prop in ("dataType", "sourceColumn", "expression"):
            if info[prop] != new.columns[key][prop]:
                breaking.append(f"column {prop} changed: {key[0]}[{key[1]}] ({info[prop]} -> {new.columns[key][prop]})")
        for prop in ("formatString", "isHidden"):
            if info[prop] != new.columns[key][prop]:
                warnings.append(f"column {prop} changed: {key[0]}[{key[1]}]")
    added += [f"column: {t}[{c}]" for (t, c) in new.columns if (t, c) not in base.columns and t in base.tables]
    for name, info in base.measures.items():
        if name not in new.measures:
            breaking.append(f"measure removed: [{name}]")
            continue
        if info["expression"] != new.measures[name]["expression"]:
            breaking.append(f"measure expression changed: [{name}]")
        for prop in ("formatString", "displayFolder", "isHidden", "table"):
            if info[prop] != new.measures[name][prop]:
                warnings.append(f"measure {prop} changed: [{name}] ({info[prop]} -> {new.measures[name][prop]})")
    added += [f"measure: [{m}]" for m in new.measures if m not in base.measures]
    for key, info in base.relationships.items():
        if key not in new.relationships:
            breaking.append(f"relationship removed: {key[0]} -> {key[1]}")
        elif info != new.relationships[key]:
            breaking.append(f"relationship changed: {key[0]} -> {key[1]} ({info} -> {new.relationships[key]})")
    added += [f"relationship: {k[0]} -> {k[1]}" for k in new.relationships if k not in base.relationships]
    return breaking, warnings, added


def files_at_ref(ref: str) -> dict[str, str]:
    names = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, "--", MODEL_DIR], cwd=REPO,
                           capture_output=True, text=True, check=True).stdout.splitlines()
    out = {}
    for n in names:
        if n.endswith(".tmdl"):
            out[n[len(MODEL_DIR) + 1:]] = subprocess.run(["git", "show", f"{ref}:{n}"], cwd=REPO, capture_output=True,
                                                         text=True, check=True, encoding="utf-8").stdout
    return out


def files_in_tree() -> dict[str, str]:
    root = REPO / MODEL_DIR
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*.tmdl")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail if the shared model changed non-additively since a baseline.")
    parser.add_argument("--base", default="model-v1", help="git tag or commit of the validated model (default model-v1)")
    args = parser.parse_args()
    try:
        base_files = files_at_ref(args.base)
    except subprocess.CalledProcessError:
        sys.exit(f"Cannot read '{args.base}'. Create the tag first (see docs/arch01_validation.md), "
                 "or pass a commit, e.g. --base a899666")
    breaking, warnings, added = compare(parse_model(base_files), parse_model(files_in_tree()))
    print(f"Shared semantic model vs {args.base}")
    print(f"  added: {len(added)}")
    for a in added:
        print(f"    + {a}")
    for w in warnings:
        print(f"  WARNING {w}")
    for b in breaking:
        print(f"  BREAKING {b}")
    print("RESULT: " + ("FAIL - breaking change(s) found" if breaking else "OK - additive only"))
    sys.exit(1 if breaking else 0)


if __name__ == "__main__":
    main()

"""Check a PBIR report for problems Microsoft's JSON schemas can't catch.

  * every field a visual uses exists in the shared model (table + column/measure)
  * one field never has two display names in one visual
  * page-navigation and bookmark buttons point at pages / bookmarks that exist
  * visual-interaction rules point at visuals that exist
  * data visuals (charts, tables, cards, slicers) don't overlap each other

    python powerbi/tools/check_report.py powerbi/PaymentOperations.Report
    python powerbi/tools/check_report.py --all          # all three reports
Exit code 0 = no problems.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PBI = Path(__file__).resolve().parents[1]
MODEL = PBI / "workforcedevelopmentanalytics.SemanticModel" / "definition" / "tables"
REPORTS = ["workforcedevelopmentanalytics.Report", "PaymentOperations.Report", "WorkforceOutcomes.Report"]
DATA_VISUALS = {"barChart", "lineChart", "pivotTable", "tableEx", "hundredPercentStackedBarChart", "clusteredBarChart",
                "clusteredColumnChart", "columnChart", "multiRowCard", "card", "slicer", "lineClusteredColumnComboChart",
                "scatterChart"}


def model_fields() -> dict[str, set[str]]:
    out = {}
    for f in MODEL.glob("*.tmdl"):
        s = f.read_text(encoding="utf-8")
        t = re.search(r"^table '?(.+?)'?\r?$", s, re.M).group(1)
        out[t] = (set(m.replace("''", "'") for m in re.findall(r"^\tmeasure '?(.+?)'? =", s, re.M))
                  | set(re.findall(r"^\tcolumn '?([^'\r\n=]+?)'?\r?$", s, re.M)))
    return out


def check(report: Path, model: dict) -> list[str]:
    d = report / "definition"
    problems: list[str] = []
    pages = {p.name: json.loads((p / "page.json").read_text(encoding="utf-8"))
             for p in (d / "pages").iterdir() if p.is_dir()}
    visuals = {pid: {v.parent.name: json.loads(v.read_text(encoding="utf-8"))
                     for v in (d / "pages" / pid / "visuals").glob("*/visual.json")} for pid in pages}
    bms = {b.name[:-14]: json.loads(b.read_text(encoding="utf-8")) for b in (d / "bookmarks").glob("*.bookmark.json")} \
        if (d / "bookmarks").exists() else {}
    refs = set()

    def walk(o, where):
        if isinstance(o, dict):
            for k in ("Measure", "Column"):
                if k in o and isinstance(o[k], dict) and "Property" in o[k] \
                        and "Entity" in o[k].get("Expression", {}).get("SourceRef", {}):
                    refs.add((o[k]["Expression"]["SourceRef"]["Entity"], o[k]["Property"], where))
            for x in o.values():
                walk(x, where)
        elif isinstance(o, list):
            for x in o:
                walk(x, where)

    for pid, pj in pages.items():
        walk(pj, pj["displayName"])
        for name, v in visuals[pid].items():
            walk(v, f"{pj['displayName']}/{name}")
            q = v.get("visual", {}).get("query", {}).get("queryState", {})
            names = defaultdict(set)
            for role in q.values():
                for p in role["projections"]:
                    names[p["queryRef"]].add(p.get("displayName"))
            problems += [f"{pj['displayName']}/{name}: '{r}' has {len(n)} display names" for r, n in names.items() if len(n) > 1]
            vl = v.get("visual", {}).get("visualContainerObjects", {}).get("visualLink")
            if vl:
                pr = vl[0]["properties"]
                for k, pool in (("bookmark", bms), ("navigationSection", pages)):
                    if k in pr and pr[k]["expr"]["Literal"]["Value"].strip("'") not in pool:
                        problems.append(f"{pj['displayName']}/{name}: dead {k} link")
        for it in pj.get("visualInteractions", []):
            for side in ("source", "target"):
                if it[side] not in visuals[pid]:
                    problems.append(f"{pj['displayName']}: interaction {side} '{it[side]}' missing")
        shown = [(n, v["position"]) for n, v in visuals[pid].items()
                 if v["visual"]["visualType"] in DATA_VISUALS and not v.get("isHidden")]
        for i, (a, A) in enumerate(shown):
            for b_, B in shown[i + 1:]:
                if not (A["x"] + A["width"] <= B["x"] or B["x"] + B["width"] <= A["x"]
                        or A["y"] + A["height"] <= B["y"] or B["y"] + B["height"] <= A["y"]):
                    problems.append(f"{pj['displayName']}: {a} overlaps {b_}")
    problems += [f"field {t}[{p}] used in {w} is not in the model" for t, p, w in refs if p not in model.get(t, set())]
    for bn, b in bms.items():
        sec = b["explorationState"]["activeSection"]
        problems += [f"bookmark {bn}: target {n} not on its page"
                     for n in b["options"]["targetVisualNames"] if n not in visuals.get(sec, {})]
    print(f"{report.name}: {len(pages)} pages, {sum(len(v) for v in visuals.values())} visuals, "
          f"{len({(t, p) for t, p, _ in refs})} distinct fields -> {'OK' if not problems else 'PROBLEMS'}")
    for p in problems:
        print("  -", p)
    return problems


def main() -> None:
    targets = [PBI / r for r in REPORTS if (PBI / r).exists()] if sys.argv[1:] == ["--all"] else [Path(a) for a in sys.argv[1:]]
    if not targets:
        sys.exit(__doc__)
    model = model_fields()
    bad = sum(len(check(t, model)) for t in targets)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

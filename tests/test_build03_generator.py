"""Build 03 generator tests (no database needed)."""

import csv
import json
import tomllib
from collections import Counter
from datetime import date, datetime

import pytest

from conftest import REPO_ROOT

import generate_build03_data as g  # noqa: E402

CFG = REPO_ROOT / "config" / "build03_synthetic.toml"
INP = REPO_ROOT / "data" / "synthetic_horizon"


@pytest.fixture(scope="module")
def cfg():
    with open(CFG, "rb") as f:
        return tomllib.load(f)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("b03")
    manifest = g.generate(CFG, INP, out)
    docs = [json.loads(line) for line in open(out / "payment_cases_phase2.jsonl", encoding="utf-8")]
    p1 = [json.loads(line) for line in open(out / "payment_cases_phase1.jsonl", encoding="utf-8")]
    agents = list(csv.DictReader(open(out / "ops_agent.csv", newline="", encoding="utf-8")))
    deps = list(csv.DictReader(open(out / "deployment.csv", newline="", encoding="utf-8")))
    return {"out": out, "manifest": manifest, "docs": docs, "p1": p1, "agents": agents, "deps": deps}


def P(x):
    return datetime.strptime(x["$date"], "%Y-%m-%dT%H:%M:%SZ")


def test_reproducible(built, tmp_path):
    again = g.generate(CFG, INP, tmp_path)
    assert again["files"] == built["manifest"]["files"]


def test_committed_relational_files_match(built):
    committed = json.loads((INP / "build03" / "generation_manifest.json").read_text(encoding="utf-8"))
    assert committed["files"] == built["manifest"]["files"], "re-run python/generate_build03_data.py"


def test_volume_near_target(built, cfg):
    assert abs(len(built["docs"]) - cfg["volume"]["target_cases"]) / cfg["volume"]["target_cases"] < 0.03


def test_volume_is_configurable(tmp_path):
    """Scaling is one config value (benchmark before going to 100k-250k)."""
    path = tmp_path / "small.toml"
    path.write_text(CFG.read_text(encoding="utf-8").replace("target_cases = 50000", "target_cases = 5000"),
                    encoding="utf-8")
    m = g.generate(path, INP, tmp_path / "out")
    assert abs(m["files"]["payment_cases_phase2.jsonl"]["rows"] - 5000) < 250


def test_agents_graduates_and_tenured(built, cfg):
    types = Counter(a["agent_type"] for a in built["agents"])
    assert types["Tenured"] == cfg["agents"]["tenured_count"]
    assert all(a["enrolment_id"] == "" for a in built["agents"] if a["agent_type"] == "Tenured")
    assert all(a["enrolment_id"] for a in built["agents"] if a["agent_type"] == "Graduate")
    assert max(Counter(a["employee_id"] for a in built["agents"]).values()) == 1      # one agent per person


def test_deployment_only_after_recorded_approval(built):
    reviews = {r["readiness_review_id"]: r for r in csv.DictReader(open(INP / "build02" / "readiness_review.csv"))}
    for d in built["deps"]:
        r = reviews[d["readiness_review_id"]]
        assert r["decision"] == "Approved"
        assert date.fromisoformat(d["deployment_date"]) > datetime.fromisoformat(r["recorded_at"]).date()


def test_no_work_after_exit_or_before_start(built):
    agents = {a["agent_id"]: a for a in built["agents"]}
    for doc in built["docs"]:
        for a in doc["assignments"]:
            ag = agents[a["agent_id"]]
            day = P(a["assigned_at"]).date()
            assert day >= date.fromisoformat(ag["start_date"])
            assert not ag["exit_date"] or day < date.fromisoformat(ag["exit_date"])


def test_first_and_final_resolution_and_history_kept(built):
    reopened = 0
    for doc in built["docs"]:
        r = doc["resolution"]
        if r["final_resolved_at"]:
            assert P(r["final_resolved_at"]) >= P(r["first_resolved_at"]) >= P(doc["received_at"])
        types = [e["type"] for e in doc["events"]]
        if doc["rework"]:
            reopened += 1
            assert types.count("reopened") == len(doc["rework"])     # reopen is a NEW event
            assert types.count("resolved") >= 1
            assert P(r["first_resolved_at"]) < P(doc["rework"][0]["at"])
    assert reopened > 0


def test_qa_weighted_six_items(built, cfg):
    sampled = [d["qa"] for d in built["docs"] if d["qa"]]
    assert sampled
    for qa in sampled:
        assert len(qa["checklist"]) == 6 and sum(c["weight"] for c in qa["checklist"]) == 100
        assert qa["score"] == sum(c["weight"] for c in qa["checklist"] if c["passed"])
        assert qa["passed"] == (qa["score"] >= cfg["qa"]["pass_mark"])
    assert len(sampled) < len(built["docs"]) * 0.2                    # QA is a SAMPLE, not every case


def test_realistic_learning_curve(built, cfg):
    """Accuracy: graduates start ~86-92% and improve; tenured stay best. QA pass is the proxy."""
    agents = {a["agent_id"]: a for a in built["agents"]}
    band = Counter(), Counter()
    for d in built["docs"]:
        if not d["qa"]:
            continue
        ag = agents[d["assignments"][-1]["agent_id"]]
        days = (P(d["received_at"]).date() - date.fromisoformat(ag["start_date"])).days
        k = "tenured" if ag["agent_type"] == "Tenured" else ("early" if days < 30 else "mature" if days >= 90 else "mid")
        band[0][k] += 1
        band[1][k] += d["qa"]["passed"]
    rate = {k: band[1][k] / band[0][k] for k in band[0]}
    assert 0.85 <= rate["early"] < rate["mature"] <= rate["tenured"] + 0.01
    lo, hi = cfg["productivity"]["graduate_initial_accuracy"]
    assert 0.80 < lo < hi < 0.95                                       # not an unrealistic 50% start


def test_malformed_documents_are_present_and_varied(built, cfg):
    bad = [d for d in built["p1"] if d["_id"].startswith("PC-DQ-")]
    assert len(bad) == cfg["data_quality"]["malformed_documents"]
    assert len({d["_dq_fault"] for d in bad}) == 5


def test_phase2_extends_phase1(built):
    p1 = {d["_id"]: d for d in built["p1"] if not d["_id"].startswith("PC-DQ-")}
    p2 = {d["_id"]: d for d in built["docs"]}
    assert set(p1) <= set(p2)
    changed = [i for i in p1 if p1[i] != p2[i]]
    assert changed and all(P(p2[i]["updated_at"]) > P(p1[i]["updated_at"]) for i in changed)
    assert built["manifest"]["phase2_changed_or_new"] == len(changed) + len(set(p2) - set(p1))


def test_tied_updated_at_timestamps_exist(built):
    """The incremental checkpoint must cope with ties; make sure the data has them."""
    assert max(Counter(d["updated_at"]["$date"] for d in built["docs"]).values()) >= 10

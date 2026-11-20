"""Generate Build 03 synthetic payment-operations data.

Everything is fictional. Inputs: the HORIZON dataset (Builds 01-02 simulated
forward to 2027-06-30) and config/build03_synthetic.toml. Outputs, in
data/synthetic_horizon/build03/:

  relational (committed, small)        ops_team, ops_queue, case_type, sla_policy,
                                       ops_agent, deployment  (.csv)
  MongoDB documents (NOT committed)    payment_cases_phase1.jsonl  as known on 2027-05-31
                                       payment_cases_phase2.jsonl  as known on 2027-06-30
  manifest (committed)                 generation_manifest.json (row counts + checksums)

The idea, as in Builds 01-02: simulate the full truth once, then OBSERVE it as
of a date. Phase 1 and phase 2 are two observations of the same truth, which
is what makes the incremental ETL demo realistic: phase 2 adds new cases and
changes some phase-1 cases (a reopen, a QA review, a final resolution).

    python python/generate_build03_data.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
import tomllib
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import mean, pstdev

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_synthetic_data import FIRST_NAMES, LAST_NAMES, add_business_days  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO / "config" / "build03_synthetic.toml"
DEFAULT_INPUT = REPO / "data" / "synthetic_horizon"
GENERATOR_VERSION = "build03-1.0"

RESOLUTION_CODES = {
    "returned_payment": ["funds_returned", "resubmitted_corrected", "closed_no_action"],
    "duplicate_payment": ["duplicate_recalled", "confirmed_not_duplicate"],
    "failed_validation": ["data_corrected", "returned_to_originator"],
    "missing_beneficiary": ["details_obtained", "payment_returned"],
    "screening_hit": ["false_positive_released", "escalated_to_compliance"],
}
FAIL_ITEMS = {  # which checklist items an error of each category breaks
    "procedural": [["documentation_complete"], ["correct_resolution_code"],
                   ["documentation_complete", "correct_resolution_code"]],
    "financial": [["funds_movement_correct"], ["funds_movement_correct", "beneficiary_verified"]],
    "compliance": [["screening_controls", "documentation_complete"]],
}


def stream(seed, *key) -> random.Random:
    return random.Random("|".join(map(str, (seed, *key))))


def uni(rng, lo_hi):
    lo, hi = lo_hi
    return lo + rng.random() * (hi - lo)


def pick_weighted(rng, items: dict):
    r, acc = rng.random(), 0.0
    for k, w in items.items():
        acc += w
        if r < acc:
            return k
    return k


def minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --------------------------------------------------------------------------
# 1. Agents and deployments
# --------------------------------------------------------------------------

def training_profile(inp: Path) -> dict:
    """Per enrolment: final training competency and first-attempt certification success."""
    scores = defaultdict(lambda: defaultdict(list))
    for a in read_csv(inp / "assessment.csv"):
        scores[a["enrolment_id"]][int(a["programme_week"])].append(int(a["score"]))
    final = {}
    for eid, weeks in scores.items():
        full = [w for w, s in weeks.items() if len(s) == 5]
        if full:
            final[eid] = mean(weeks[max(full)])
    certs = defaultdict(set)
    for a in read_csv(inp / "build02" / "certification_attempt.csv"):
        if a["attempt_number"] == "1" and a["result"] == "Passed":
            certs[a["enrolment_id"]].add(a["certification_id"])
    watched = {w["enrolment_id"] for w in read_csv(inp / "build02" / "watchlist_case.csv")}
    mu, sd = mean(final.values()), pstdev(final.values()) or 1
    return {eid: {"competency_z": (v - mu) / sd, "first_pass_both": len(certs[eid]) == 2, "watchlisted": eid in watched}
            for eid, v in final.items()}


def build_agents(cfg: dict, inp: Path, horizon: date, seed: int):
    enrol = {e["enrolment_id"]: e for e in read_csv(inp / "enrolment.csv")}
    people = {p["employee_id"]: p for p in read_csv(inp / "employee.csv")}
    latest = {}
    for r in sorted(read_csv(inp / "build02" / "readiness_review.csv"), key=lambda r: int(r["review_number"])):
        latest[r["enrolment_id"]] = r
    approved = [r for r in latest.values() if r["decision"] == "Approved"]
    # one agent per EMPLOYEE: the qualifying enrolment is the latest approved one
    by_employee = {}
    for r in sorted(approved, key=lambda r: r["review_date"]):
        by_employee[enrol[r["enrolment_id"]]["employee_id"]] = r
    queues = cfg["agents"]["queues"]
    qweights = {q["queue_id"]: q["weight"] for q in queues}
    qteam = {q["queue_id"]: q["team_id"] for q in queues}
    profile = training_profile(inp)
    agents, deployments = [], []
    for emp_id, r in sorted(by_employee.items()):
        eid = r["enrolment_id"]
        tp = profile.get(eid, {"competency_z": 0.0, "first_pass_both": False, "watchlisted": False})
        rng = stream(seed, "agent", eid)
        recorded = datetime.fromisoformat(r["recorded_at"]).date()
        start = add_business_days(recorded, int(uni(rng, cfg["agents"]["deploy_lag_business_days"]) + 0.5))
        queue = pick_weighted(rng, qweights)
        exit_day, exit_reason = None, None
        p_exit = cfg["exits"]["graduate_exit_probability"] * (cfg["exits"]["watchlist_exit_multiplier"] if tp["watchlisted"] else 1)
        if rng.random() < p_exit:
            exit_day = start + timedelta(days=int(uni(rng, cfg["exits"]["graduate_exit_window_days"])))
            exit_reason = "Resigned"
        if start > horizon:
            continue                               # approved, but not yet deployed by the horizon
        if exit_day and exit_day > horizon:
            exit_day, exit_reason = None, None     # a future exit is not yet known
        agent_id = f"AG-G{eid.split('-')[1]}"
        p = people[emp_id]
        agents.append({"agent_id": agent_id, "employee_id": emp_id, "enrolment_id": eid, "agent_type": "Graduate",
                       "first_name": p["first_name"], "last_name": p["last_name"], "team_id": qteam[queue],
                       "primary_queue_id": queue, "start_date": start, "exit_date": exit_day, "exit_reason": exit_reason,
                       "_z": tp["competency_z"], "_first_pass": tp["first_pass_both"], "_watch": tp["watchlisted"]})
        deployments.append({"deployment_id": f"DEP-{eid.split('-')[1]}", "enrolment_id": eid, "agent_id": agent_id,
                            "readiness_review_id": r["readiness_review_id"], "approved_review_date": r["review_date"],
                            "deployment_date": start, "team_id": qteam[queue], "queue_id": queue})
    ops_start = date.fromisoformat(cfg["run"]["ops_start"])
    for i in range(1, cfg["agents"]["tenured_count"] + 1):
        rng = stream(seed, "tenured", i)
        y0, y1 = cfg["agents"]["tenured_start_years"]
        start = date(y0, 1, 4) + timedelta(days=int(rng.random() * ((date(y1, 12, 31) - date(y0, 1, 4)).days)))
        queue = pick_weighted(rng, qweights)
        exit_day = exit_reason = None
        span = (horizon - ops_start).days
        if rng.random() < cfg["exits"]["tenured_annual_exit_probability"] * span / 365:
            exit_day, exit_reason = ops_start + timedelta(days=int(rng.random() * span)), "Resigned"
        agents.append({"agent_id": f"AG-T{i:03d}", "employee_id": f"ET-{i:04d}", "enrolment_id": None,
                       "agent_type": "Tenured", "first_name": FIRST_NAMES[int(rng.random() * len(FIRST_NAMES))],
                       "last_name": LAST_NAMES[int(rng.random() * len(LAST_NAMES))], "team_id": qteam[queue],
                       "primary_queue_id": queue, "start_date": start, "exit_date": exit_day, "exit_reason": exit_reason,
                       "_z": 0.0, "_first_pass": True, "_watch": False})
    return agents, deployments


def agent_params(cfg, a, seed):
    """Individual learning-curve parameters (hidden; not exported)."""
    p, rng = cfg["productivity"], stream(seed, "params", a["agent_id"])
    if a["agent_type"] == "Tenured":
        acc = uni(rng, p["tenured_accuracy"])
        return {"thr0": 1.0, "thr1": uni(rng, p["tenured_throughput"]), "acc0": acc, "acc1": acc, "tau": 1.0}
    z = max(-2.0, min(2.0, a["_z"]))                 # training competency, in SDs (clipped)
    tau = uni(rng, p["ramp_days"]) * (1 - p["certification_ramp_speedup"] if a["_first_pass"] else 1) \
        * (1 - p["competency_ramp_effect"] * z) * (p["watchlist_ramp_penalty"] if a["_watch"] else 1)
    acc0 = min(0.95, uni(rng, p["graduate_initial_accuracy"]) + p["training_effect"] * z)
    acc1 = uni(rng, p["graduate_mature_accuracy"]) + p["training_effect"] * z * 0.5
    if rng.random() < p["plateau_probability"]:
        acc1 = acc0 + 0.5 * (acc1 - acc0)          # imperfect improvement
    thr1 = uni(rng, p["graduate_throughput_mature"])
    return {"thr0": p["graduate_throughput_start"] * thr1, "thr1": thr1, "acc0": acc0, "acc1": min(acc1, 0.99), "tau": tau}


def curve(start_v, end_v, t, tau):
    return end_v - (end_v - start_v) * math.exp(-t / tau)


# --------------------------------------------------------------------------
# 2. The case truth
# --------------------------------------------------------------------------

def business_days(d0: date, d1: date) -> list[date]:
    out, d = [], d0
    while d <= d1:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def active_days(a, days, ops_start):
    start = max(a["start_date"], ops_start)
    return [d for d in days if d >= start and (a["exit_date"] is None or d < a["exit_date"])]


def hand_over_after_exit(events, assignments, agent, by_queue_day, horizon, seed, key):
    """An agent who has left can't act on a case. If the case's next action falls on
    or after the agent's exit date, a teammate on the same queue takes it over: a NEW
    'assigned' event and assignment are added at 08:00 on the first working day from
    the exit date (or just before that action, if earlier), and later actions are
    theirs. Nothing is erased."""
    if agent["exit_date"] is None:
        return
    late = [i for i, e in enumerate(events) if e[2] == agent["agent_id"] and e[1].date() >= agent["exit_date"]]
    if not late:
        return
    i = late[0]
    day = agent["exit_date"]
    while day.weekday() >= 5:
        day += timedelta(days=1)
    team = [o for o in by_queue_day.get((agent["primary_queue_id"], day), []) if o["agent_id"] != agent["agent_id"]]
    if not team:
        return                               # nobody to hand over to; the validation check would flag it
    successor = team[int(stream(seed, "handover", key).random() * len(team))]
    at = minute(max(events[i - 1][1] + timedelta(minutes=1),
                    min(datetime.combine(day, time(8)), events[i][1] - timedelta(minutes=1))))
    at = max(at, datetime.combine(agent["exit_date"], time(0)))
    for j in range(i, len(events)):
        if events[j][2] == agent["agent_id"]:
            events[j] = (events[j][0], max(events[j][1], at + timedelta(minutes=1)), successor["agent_id"])
    events.insert(i, ("assigned", at, successor["agent_id"]))
    assignments.append((successor["agent_id"], at))


def simulate_cases(cfg, agents, horizon, seed):
    ops_start = date.fromisoformat(cfg["run"]["ops_start"])
    days = business_days(ops_start, horizon)
    params = {a["agent_id"]: agent_params(cfg, a, seed) for a in agents}
    work = []                                    # (agent, day, t business days since start, capacity)
    for a in agents:
        pr = params[a["agent_id"]]
        for d in active_days(a, days, ops_start):
            t = len(business_days(a["start_date"], d)) - 1 if a["agent_type"] == "Graduate" else 10_000
            work.append((a, d, t, curve(pr["thr0"], pr["thr1"], t, pr["tau"])))
    rate = cfg["volume"]["target_cases"] / sum(w[3] for w in work)   # calibrate volume to the target
    by_queue_day = defaultdict(list)
    for a, d, t, _ in work:
        by_queue_day[(a["primary_queue_id"], d)].append(a)
    qtype = {q["queue_id"]: q["case_type"] for q in cfg["agents"]["queues"]}
    c, q, sla = cfg["cases"], cfg["qa"], cfg["sla"]
    weights = {i["item"]: i["weight"] for i in q["checklist"]}
    cases = []
    for a, d, t, cap in work:
        rng = stream(seed, "day", a["agent_id"], d.isoformat())
        n = int(cap * rate + rng.random())       # stochastic rounding keeps the expected volume
        pr = params[a["agent_id"]]
        acc = curve(pr["acc0"], pr["acc1"], t, pr["tau"]) + rng.gauss(0, cfg["productivity"]["daily_accuracy_noise"])
        slow = 1 + (cfg["productivity"]["new_agent_slowdown"] - 1) * math.exp(-t / pr["tau"]) \
            if a["agent_type"] == "Graduate" else 1.0
        for k in range(n):
            cr = stream(seed, "case", a["agent_id"], d.isoformat(), k)
            prio = pick_weighted(cr, c["priority_mix"])
            ctype = qtype[a["primary_queue_id"]]
            target = sla["overrides"].get(f"{ctype}_{prio}", sla["targets"][prio])
            received = minute(datetime.combine(d, time(8)) + timedelta(minutes=int(cr.random() * 480)))
            assigned = received + timedelta(minutes=5 + int(cr.random() * 85))
            agent = a
            events = [("created", received, None), ("assigned", assigned, a["agent_id"])]
            assignments = [(a["agent_id"], assigned)]
            started = assigned + timedelta(minutes=10 + int(cr.random() * 110))
            if cr.random() < c["reassignment_probability"]:
                others = [o for o in by_queue_day[(a["primary_queue_id"], d)] if o["agent_id"] != a["agent_id"]]
                if others:
                    agent = others[int(cr.random() * len(others))]
                    re_at = started + timedelta(minutes=30 + int(cr.random() * 210))
                    events.append(("in_progress", started, a["agent_id"]))
                    events.append(("assigned", re_at, agent["agent_id"]))
                    assignments.append((agent["agent_id"], re_at))
                    started = re_at + timedelta(minutes=10 + int(cr.random() * 60))
            events.append(("in_progress", started, agent["agent_id"]))
            hours = cr.lognormvariate(math.log(c["resolution_median_hours"][prio] * slow), c["resolution_sigma"])
            first_res = received + timedelta(hours=hours)
            if cr.random() < c["pending_info_probability"]:
                pend = started + timedelta(minutes=30 + int(cr.random() * 210))
                events.append(("pending_info", pend, agent["agent_id"]))
                first_res = max(first_res, pend) + timedelta(hours=uni(cr, c["pending_info_hours"]))
            first_res = minute(max(first_res, started + timedelta(minutes=10)))
            events.append(("resolved", first_res, agent["agent_id"]))
            code = RESOLUTION_CODES[ctype][int(cr.random() * len(RESOLUTION_CODES[ctype]))]
            has_error = cr.random() > acc
            sampled = cr.random() < (q["sample_rate_first_30_days"] if (agent["agent_type"] == "Graduate" and t < 30)
                                     else q["sample_rate_after"])
            qa, rework = None, []
            if sampled:
                reviewed = datetime.combine(add_business_days(first_res.date(), int(uni(cr, q["review_after_business_days"]) + 0.5)),
                                            time(q["review_hour"]))
                failed, errors = [], []
                if has_error:
                    cat = pick_weighted(cr, q["error_category_mix"])
                    failed = FAIL_ITEMS[cat][int(cr.random() * len(FAIL_ITEMS[cat]))]
                    sev = "critical" if cat in ("financial", "compliance") else ("major" if len(failed) > 1 else "minor")
                    errors.append({"category": cat, "severity": sev})
                elif cr.random() < q["random_minor_miss_probability"]:
                    failed = ["customer_communication"]
                    errors.append({"category": "procedural", "severity": "minor"})
                score = 100 - sum(weights[i] for i in failed)
                qa = {"reviewed_at": reviewed, "reviewer_role": "QA analyst", "score": score,
                      "passed": score >= q["pass_mark"],
                      "checklist": [{"item": i, "weight": w, "passed": i not in failed} for i, w in weights.items()],
                      "errors": errors}
                if not qa["passed"]:            # failed QA -> rework; history is kept, not overwritten
                    rework.append((reviewed, "qa_failed"))
                    events.append(("reopened", reviewed, None))
                    fix = reviewed + timedelta(hours=cr.lognormvariate(math.log(c["resolution_median_hours"][prio] * 0.5), 0.5))
                    events.append(("resolved", minute(fix), agent["agent_id"]))
            elif has_error and cr.random() < c["undetected_error_reopen_probability"]:
                reopen = minute(datetime.combine(first_res.date() + timedelta(days=int(uni(cr, c["reopen_after_days"]) + 0.5)),
                                                 time(9)) + timedelta(minutes=int(cr.random() * 420)))
                rework.append((reopen, "customer_reopened"))
                events.append(("reopened", reopen, None))
                fix = reopen + timedelta(hours=cr.lognormvariate(math.log(c["resolution_median_hours"][prio]), 0.5))
                events.append(("resolved", minute(fix), agent["agent_id"]))
            hand_over_after_exit(events, assignments, agent, by_queue_day, horizon, seed,
                                 f"{a['agent_id']}|{d.isoformat()}|{k}")
            cases.append({"received": received, "agent": a["agent_id"], "case_type": ctype, "priority": prio,
                          "channel": c["channels"][int(cr.random() * len(c["channels"]))],
                          "amount_band": c["amount_bands"][int(cr.random() * len(c["amount_bands"]))],
                          "queue": a["primary_queue_id"], "target": target, "events": events,
                          "assignments": assignments, "code": code, "qa": qa, "rework": rework})
    cases.sort(key=lambda x: (x["received"], x["agent"]))
    for i, x in enumerate(cases, start=1):
        x["case_id"] = f"PC-{i:06d}"
    return cases


# --------------------------------------------------------------------------
# 3. Observe as MongoDB documents
# --------------------------------------------------------------------------

def d(dt):
    """MongoDB Extended JSON date (loaded as a real BSON date by mongoimport / json_util)."""
    return {"$date": dt.strftime("%Y-%m-%dT%H:%M:%SZ")}


def observe(case, cutoff: datetime, policy: str) -> dict | None:
    if case["received"] > cutoff:
        return None
    events = [e for e in case["events"] if e[1] <= cutoff]
    events.sort(key=lambda e: e[1])
    resolved = [e[1] for e in events if e[0] == "resolved"]
    last = events[-1][0]
    status = {"resolved": "resolved", "reopened": "reopened"}.get(last, "open")
    qa = case["qa"] if case["qa"] and case["qa"]["reviewed_at"] <= cutoff else None
    rework = [r for r in case["rework"] if r[0] <= cutoff]
    stamps = [e[1] for e in events] + ([qa["reviewed_at"]] if qa else []) + [r[0] for r in rework]
    doc = {
        "_id": case["case_id"], "schema_version": 1, "case_type": case["case_type"], "priority": case["priority"],
        "channel": case["channel"], "amount_band": case["amount_band"], "received_at": d(case["received"]),
        "queue": case["queue"], "sla": {"policy_version": policy, "target_hours": case["target"]},
        "assignments": [{"agent_id": ag, "assigned_at": d(t)} for ag, t in case["assignments"] if t <= cutoff],
        "events": [{"type": t, "at": d(at), **({"by": by} if by else {})} for t, at, by in events],
        "resolution": {"code": case["code"] if resolved else None,
                       "first_resolved_at": d(resolved[0]) if resolved else None,
                       "final_resolved_at": d(resolved[-1]) if status == "resolved" else None},
        "status": status,
        "qa": None if not qa else {**{k: v for k, v in qa.items() if k != "reviewed_at"}, "sampled": True,
                                   "reviewed_at": d(qa["reviewed_at"])},
        "rework": [{"at": d(t), "reason": why} for t, why in rework],
        "updated_at": d(max(stamps)),
    }
    return doc


def malformed(docs: list[dict], n: int, seed: int) -> list[dict]:
    """Deliberately broken documents (data-quality demo). Each breaks ONE rule."""
    rng, out = stream(seed, "malformed"), []
    faults = ["missing_received_at", "resolved_before_received", "unknown_case_type", "unknown_agent", "invalid_priority"]
    for i in range(n):
        src = json.loads(json.dumps(docs[int(rng.random() * len(docs))]))
        fault = faults[i % len(faults)]
        src["_id"] = f"PC-DQ-{i + 1:04d}"
        if fault == "missing_received_at":
            src.pop("received_at")
        elif fault == "resolved_before_received":
            src["resolution"]["final_resolved_at"] = {"$date": "2026-01-01T09:00:00Z"}
            src["status"] = "resolved"
        elif fault == "unknown_case_type":
            src["case_type"] = "card_dispute"
        elif fault == "unknown_agent":
            src["assignments"] = [{"agent_id": "AG-X999", "assigned_at": src["received_at"]}]
        else:
            src["priority"] = "P9"
        src["_dq_fault"] = fault                 # kept only so tests can check the reason
        out.append(src)
    return out


# --------------------------------------------------------------------------
# 4. Write
# --------------------------------------------------------------------------

def cell(v):
    return "" if v is None else (v.isoformat() if isinstance(v, (date, datetime)) else v)


def write_csv(path: Path, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[k for k in rows[0] if not k.startswith("_")], lineterminator="\n",
                           extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: cell(v) for k, v in r.items() if not k.startswith("_")})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def generate(config_path=DEFAULT_CONFIG, input_dir=DEFAULT_INPUT, output_dir=None) -> dict:
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    output_dir = output_dir or input_dir / "build03"
    output_dir.mkdir(parents=True, exist_ok=True)
    seed, policy = cfg["run"]["seed"], cfg["run"]["policy_version"]
    horizon = date.fromisoformat(read_csv(input_dir / "data_snapshot.csv")[0]["as_of_date"])
    agents, deployments = build_agents(cfg, input_dir, horizon, seed)
    cases = simulate_cases(cfg, agents, horizon, seed)

    refs = {
        "ops_team": [{"team_id": t["team_id"], "team_name": t["team_name"]} for t in cfg["agents"]["teams"]],
        "ops_queue": [{"queue_id": q["queue_id"], "queue_name": q["queue_name"], "team_id": q["team_id"],
                       "case_type_code": q["case_type"]} for q in cfg["agents"]["queues"]],
        "case_type": [{"case_type_code": q["case_type"], "case_type_name": q["case_type_name"]} for q in cfg["agents"]["queues"]],
        "sla_policy": [{"policy_version": policy, "case_type_code": q["case_type"], "priority": p,
                        "target_hours": cfg["sla"]["overrides"].get(f"{q['case_type']}_{p}", h)}
                       for q in cfg["agents"]["queues"] for p, h in cfg["sla"]["targets"].items()],
        "ops_agent": agents,
        "deployment": deployments,
    }
    manifest = {"generator_version": GENERATOR_VERSION, "seed": seed, "horizon": horizon.isoformat(),
                "incremental_cutoff": cfg["run"]["incremental_cutoff"], "files": {}}
    for name, rows in refs.items():
        path = output_dir / f"{name}.csv"
        write_csv(path, rows)
        manifest["files"][path.name] = {"rows": len(rows), "sha256": sha(path)}

    cut1 = datetime.combine(date.fromisoformat(cfg["run"]["incremental_cutoff"]), time(23, 59))
    cut2 = datetime.combine(horizon, time(23, 59))
    phase1 = [x for x in (observe(c, cut1, policy) for c in cases) if x]
    phase2 = [x for x in (observe(c, cut2, policy) for c in cases) if x]
    bad = malformed(phase1, cfg["data_quality"]["malformed_documents"], seed)
    for name, docs in (("payment_cases_phase1.jsonl", phase1 + bad), ("payment_cases_phase2.jsonl", phase2)):
        path = output_dir / name
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for doc in docs:
                f.write(json.dumps(doc, separators=(",", ":")) + "\n")
        manifest["files"][name] = {"rows": len(docs), "sha256": sha(path)}
    p1 = {x["_id"]: x["updated_at"]["$date"] for x in phase1}
    manifest["phase2_changed_or_new"] = sum(1 for x in phase2 if p1.get(x["_id"]) != x["updated_at"]["$date"])
    (output_dir / "generation_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output-dir", type=Path)
    args = ap.parse_args()
    m = generate(args.config, args.input_dir, args.output_dir)
    print(f"Build 03 data written (horizon {m['horizon']}, incremental cutoff {m['incremental_cutoff']})")
    for name, info in m["files"].items():
        print(f"  {name:<30} {info['rows']:>7} rows")
    print(f"  phase 2 new or changed documents: {m['phase2_changed_or_new']}")


if __name__ == "__main__":
    main()

"""Generate the Build 01 synthetic training dataset.

Everything this script produces is fictional. It reads its assumptions from
config/build01_synthetic.toml and writes CSV files to data/synthetic/.

How it works (the idea worth understanding):

1. SIMULATE THE WHOLE PROGRAMME. For every cohort we simulate all 8 weeks,
   even weeks that are "in the future" relative to the as-of date. This is
   the hidden "truth" of what will happen.
2. OBSERVE IT AS OF A DATE. We then keep only the records that would exist
   on the as-of date: things that have happened AND have been recorded.

Because step 1 never looks at the as-of date, the data for an earlier as-of
date is always an exact subset of the data for a later one. This guarantees
there is no "future leakage", and the tests check it.

Usage:
    python python/generate_synthetic_data.py
    python python/generate_synthetic_data.py --seed 42 --as-of-date 2026-10-01
    python python/generate_synthetic_data.py --output-dir some/other/folder
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "build01_synthetic.toml"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "synthetic"
GENERATOR_VERSION = "build01-1.0"

# Fictional name pools. Combinations are random; they are not real people.
FIRST_NAMES = [
    "Abena", "Adwoa", "Akosua", "Ama", "Efua", "Esi", "Yaa", "Afia", "Akua", "Adjoa",
    "Kofi", "Kwame", "Kwabena", "Kwaku", "Kwesi", "Yaw", "Kojo", "Fiifi", "Ekow", "Nana",
    "Amara", "Chidi", "Ngozi", "Tunde", "Zainab", "Ibrahim", "Fatima", "Musa", "Halima", "Sani",
    "Grace", "Daniel", "Sarah", "Michael", "Joyce", "Samuel", "Linda", "Emmanuel", "Ruth", "David",
    "Priya", "Arjun", "Mei", "Lucas", "Sofia", "Omar", "Leila", "Mateo", "Hannah", "Noah",
]
LAST_NAMES = [
    "Mensah", "Owusu", "Boateng", "Asante", "Osei", "Agyeman", "Appiah", "Amoah", "Ansah", "Darko",
    "Addo", "Quaye", "Tetteh", "Lamptey", "Nkansah", "Frimpong", "Badu", "Sarpong", "Opoku", "Acheampong",
    "Okafor", "Adeyemi", "Bello", "Eze", "Abubakar", "Danjuma", "Nwosu", "Balogun", "Ogunleye", "Yakubu",
    "Carter", "Bennett", "Hughes", "Patel", "Rahman", "Silva", "Nakamura", "Novak", "Haddad", "Moreau",
]


# --------------------------------------------------------------------------
# Small helpers. We only use rng.random() and rng.gauss() so results stay
# identical across Python versions and operating systems.
# --------------------------------------------------------------------------

def pick(rng: random.Random, items: list):
    return items[int(rng.random() * len(items))]


def chance(rng: random.Random, probability: float) -> bool:
    return rng.random() < probability


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def fmt_ts(day: date, hour: int, minute: int) -> str:
    return datetime.combine(day, time(hour, minute)).strftime("%Y-%m-%d %H:%M:%S")


def add_business_days(day: date, n: int) -> date:
    """Move forward n working days (Mon-Fri)."""
    while n > 0:
        day += timedelta(days=1)
        if day.weekday() < 5:
            n -= 1
    return day


# --------------------------------------------------------------------------
# The simulated "truth" for one enrolment.
# --------------------------------------------------------------------------

@dataclass
class EnrolmentTruth:
    enrolment_id: str
    employee_id: str
    cohort_id: str
    enrolled_date: date
    cancelled_date: date | None = None       # pre-start cancellation
    withdrawn_date: date | None = None       # first day no longer in training
    completed_date: date | None = None       # last programme day
    declining: bool = False                  # hidden generator flag, not exported
    attendance: dict = field(default_factory=dict)   # session_id -> "Present"/"Absent"/None(unrecorded)
    scores: list = field(default_factory=list)       # (week, competency_id, date, score)


def load_config(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def build_sessions(cohort: dict, weeks: int, per_week: int) -> list[dict]:
    """One training session per weekday for every programme week."""
    start = date.fromisoformat(cohort["start_date"])
    if start.weekday() != 0:
        raise ValueError(f"{cohort['cohort_id']} start_date must be a Monday")
    sessions = []
    for week in range(1, weeks + 1):
        for day_index in range(per_week):
            session_date = start + timedelta(weeks=week - 1, days=day_index)
            sessions.append({
                "session_id": f"SES-{cohort['cohort_id'][4:]}-W{week:02d}-D{day_index + 1}",
                "cohort_id": cohort["cohort_id"],
                "programme_week": week,
                "session_day": day_index + 1,
                "session_date": session_date,
            })
    return sessions


def simulate(config: dict, seed: int) -> dict:
    """Simulate the complete programme for every cohort (ignores as-of date)."""
    rng = random.Random(seed)
    prog = config["programme"]
    att_cfg = config["attendance"]
    wd_cfg = config["withdrawal"]
    ass_cfg = config["assessment"]
    weeks = prog["weeks"]

    cohorts, employees, enrolments, sessions = [], [], [], []
    cohort_lookup = {}
    employee_counter = 0

    def new_employee() -> str:
        """Create a person. Their hire_date is set once we know when they enrol."""
        nonlocal employee_counter
        employee_counter += 1
        emp_id = f"EMP-{employee_counter:05d}"
        employees.append({
            "employee_id": emp_id,
            "first_name": pick(rng, FIRST_NAMES),
            "last_name": pick(rng, LAST_NAMES),
            "hire_date": None,
        })
        return emp_id

    # Cohorts and their sessions
    for c in config["cohorts"]:
        start = date.fromisoformat(c["start_date"])
        cohort_sessions = build_sessions(c, weeks, prog["sessions_per_week"])
        sessions.extend(cohort_sessions)
        row = {
            "cohort_id": c["cohort_id"],
            "cohort_name": c["cohort_name"],
            "start_date": start,
            "planned_end_date": cohort_sessions[-1]["session_date"],
            "planned_weeks": weeks,
            "delivery_mode": c["delivery_mode"],
        }
        cohorts.append(row)
        cohort_lookup[c["cohort_id"]] = (c, row, cohort_sessions)

    # Repeat enrolments are decided after earlier cohorts are simulated,
    # so process cohorts in start-date order.
    repeat_rules = config["enrolment"].get("repeat_enrolments", [])
    withdrawn_by_cohort: dict[str, list[str]] = {}
    enrol_counter = 0

    for c in sorted(config["cohorts"], key=lambda x: x["start_date"]):
        c_cfg, c_row, c_sessions = cohort_lookup[c["cohort_id"]]
        start = c_row["start_date"]

        # Who is enrolled: returning employees first, then new hires.
        returning = []
        for rule in repeat_rules:
            if rule["to_cohort"] == c["cohort_id"]:
                returning += withdrawn_by_cohort.get(rule["from_cohort"], [])[: rule["count"]]

        people = list(returning)
        while len(people) < c_cfg["enrolments"]:
            people.append(new_employee())

        declining_slots = set()
        while len(declining_slots) < att_cfg["declining_trainees_per_cohort"]:
            declining_slots.add(int(rng.random() * len(people)))

        cohort_gain = c_cfg["total_gain"]
        for i, emp_id in enumerate(people):
            enrol_counter += 1
            e = EnrolmentTruth(
                enrolment_id=f"ENR-{enrol_counter:05d}",
                employee_id=emp_id,
                cohort_id=c["cohort_id"],
                enrolled_date=start - timedelta(days=5 + int(rng.random() * 20)),
                declining=i in declining_slots,
            )
            # A new hire is hired 0-9 days BEFORE enrolling (never after).
            # Returning employees keep the hire date from their first cohort.
            employee = employees[int(emp_id.split("-")[1]) - 1]
            if employee["hire_date"] is None:
                employee["hire_date"] = e.enrolled_date - timedelta(days=int(rng.random() * 10))
            # Returning employees cannot cancel; they already chose to re-enrol.
            if emp_id not in returning and chance(rng, config["enrolment"]["pre_start_cancellation_rate"]):
                e.cancelled_date = e.enrolled_date + timedelta(days=1 + int(rng.random() * 3))
                if e.cancelled_date >= start:
                    e.cancelled_date = start - timedelta(days=1)
                enrolments.append(e)
                continue

            # Per-person learning profile
            person_level = rng.gauss(0, ass_cfg["person_sd"])
            person_speed = clamp(rng.gauss(1.0, 0.2), 0.4, 1.6)
            comp_base = {
                comp["competency_id"]: ass_cfg["baseline_mean"] + comp["baseline_offset"]
                + person_level + rng.gauss(0, ass_cfg["competency_sd"])
                for comp in ass_cfg["competencies"]
            }

            # Week by week: attendance, possible withdrawal, Friday assessment
            for week in range(1, weeks + 1):
                week_sessions = [s for s in c_sessions if s["programme_week"] == week]

                # Withdrawal happens at the start of a week (from week 2 onwards)
                if week >= 2:
                    p_wd = wd_cfg["baseline_weekly_probability"]
                    if e.declining and week >= att_cfg["declining_start_week"]:
                        p_wd = wd_cfg["declining_weekly_probability"]
                    if chance(rng, p_wd):
                        # Withdraws on a random day of this week
                        e.withdrawn_date = week_sessions[int(rng.random() * len(week_sessions))]["session_date"]

                p_present = att_cfg["base_present_probability"]
                if e.declining and week >= att_cfg["declining_start_week"]:
                    drop = att_cfg["declining_weekly_drop"] * (week - att_cfg["declining_start_week"] + 1)
                    p_present = max(att_cfg["declining_floor"], p_present - drop)

                present_on_friday = False
                for s in week_sessions:
                    if e.withdrawn_date and s["session_date"] >= e.withdrawn_date:
                        break
                    status = "Present" if chance(rng, p_present) else "Absent"
                    e.attendance[s["session_id"]] = status
                    present_on_friday = status == "Present"

                if e.withdrawn_date:
                    break   # no assessment in the week they leave

                # Friday assessment, only if they were present that day
                if present_on_friday:
                    progress = (1 - ass_cfg["learning_curve"] ** (week - 1)) / (1 - ass_cfg["learning_curve"] ** (weeks - 1))
                    gain = cohort_gain * person_speed * progress
                    if e.declining and week >= att_cfg["declining_start_week"]:
                        gain *= ass_cfg["declining_gain_factor"]
                    for comp in ass_cfg["competencies"]:
                        score = comp_base[comp["competency_id"]] + gain + rng.gauss(0, ass_cfg["weekly_noise_sd"])
                        e.scores.append((week, comp["competency_id"], week_sessions[-1]["session_date"],
                                         int(round(clamp(score, 0, 100)))))

            if e.withdrawn_date:
                withdrawn_by_cohort.setdefault(c["cohort_id"], []).append(emp_id)
            else:
                e.completed_date = c_row["planned_end_date"]
            enrolments.append(e)

    # Missing registers (unrecorded attendance). Decided per session / record,
    # using a separate RNG so changing these rates doesn't reshuffle people.
    miss_rng = random.Random(seed + 1)
    unrecorded_sessions = {
        s["session_id"] for s in sessions
        if chance(miss_rng, att_cfg["whole_session_unrecorded_probability"])
    }
    for e in enrolments:
        for session_id in list(e.attendance):
            if session_id in unrecorded_sessions or chance(miss_rng, att_cfg["single_record_unrecorded_probability"]):
                e.attendance[session_id] = None

    return {
        "cohorts": cohorts,
        "employees": employees,
        "enrolments": enrolments,
        "sessions": sessions,
        "competencies": ass_cfg["competencies"],
    }


# --------------------------------------------------------------------------
# Observe the truth as of a date, producing table rows.
# --------------------------------------------------------------------------

def observe(truth: dict, as_of: date, rubric_version: str, seed: int) -> dict[str, list[dict]]:
    """Keep only records that exist (happened AND were recorded) by as_of."""
    lag_rng = random.Random(seed + 2)   # recording delays, independent of as_of
    session_by_id = {s["session_id"]: s for s in truth["sessions"]}

    tables = {name: [] for name in [
        "cohort", "employee", "competency", "enrolment", "enrolment_status_event",
        "scheduled_session", "attendance", "assessment",
    ]}

    # Reference data: cohorts and sessions are planned in advance, so they
    # exist even for future dates (a schedule is known before it happens).
    for c in truth["cohorts"]:
        tables["cohort"].append({**c})
    for s in truth["sessions"]:
        tables["scheduled_session"].append({**s})
    for i, comp in enumerate(truth["competencies"], start=1):
        tables["competency"].append({
            "competency_id": comp["competency_id"],
            "competency_name": comp["competency_name"],
            "display_order": i,
        })

    cohort_start = {c["cohort_id"]: c["start_date"] for c in truth["cohorts"]}
    known_employees = set()
    event_code = {"enrolled": 1, "cancelled": 2, "started": 3, "withdrawn": 4, "completed": 5}
    competency_index = {c["competency_id"]: i for i, c in enumerate(truth["competencies"], start=1)}

    for e in truth["enrolments"]:
        # Draw every lag up front, in a fixed order, so the random sequence
        # never depends on as_of. (Prefix property — see module docstring.)
        lags = {
            "enrolled": 0,
            "cancelled": int(lag_rng.random() * 2),
            "started": int(lag_rng.random() * 2),
            "withdrawn": 1 + int(lag_rng.random() * 4),   # withdrawals are often logged late
            "completed": 1 + int(lag_rng.random() * 3),
        }
        assess_lag = int(lag_rng.random() * 2)

        if e.enrolled_date > as_of:
            continue
        known_employees.add(e.employee_id)
        # IDs are built from the enrolment number so a record keeps the same
        # ID whatever the as-of date (a real system never renumbers records).
        enr_num = e.enrolment_id.split("-")[1]
        tables["enrolment"].append({
            "enrolment_id": e.enrolment_id,
            "employee_id": e.employee_id,
            "cohort_id": e.cohort_id,
            "enrolled_date": e.enrolled_date,
        })

        events = [("enrolled", e.enrolled_date)]
        if e.cancelled_date:
            events.append(("cancelled", e.cancelled_date))
        else:
            events.append(("started", cohort_start[e.cohort_id]))
            if e.withdrawn_date:
                events.append(("withdrawn", e.withdrawn_date))
            if e.completed_date:
                events.append(("completed", e.completed_date))

        for event_type, effective in events:
            recorded_day = add_business_days(effective, lags[event_type]) if lags[event_type] else effective
            if recorded_day > as_of:
                continue    # happened, maybe, but nobody has recorded it yet
            tables["enrolment_status_event"].append({
                "status_event_id": f"EVT-{enr_num}-{event_code[event_type]}",
                "enrolment_id": e.enrolment_id,
                "event_type": event_type,
                "effective_date": effective,
                "recorded_at": fmt_ts(recorded_day, 17 if event_type != "enrolled" else 10, 0),
            })

        for session_id, status in e.attendance.items():
            s = session_by_id[session_id]
            if s["session_date"] > as_of or status is None:
                continue    # future session, or the mark was never recorded
            tables["attendance"].append({
                "enrolment_id": e.enrolment_id,
                "session_id": session_id,
                "attendance_status": status,
                "recorded_at": fmt_ts(s["session_date"], 18, 0),
            })

        for week, competency_id, assess_date, score in e.scores:
            recorded_day = add_business_days(assess_date, assess_lag) if assess_lag else assess_date
            if recorded_day > as_of:
                continue
            tables["assessment"].append({
                "assessment_id": f"ASM-{enr_num}-W{week:02d}-C{competency_index[competency_id]}",
                "enrolment_id": e.enrolment_id,
                "competency_id": competency_id,
                "programme_week": week,
                "attempt_number": 1,
                "assessment_date": assess_date,
                "score": score,
                "rubric_version": rubric_version,
                "recorded_at": fmt_ts(recorded_day, 16, 30),
            })

    # Only employees with at least one known enrolment exist yet.
    tables["employee"] = [emp for emp in truth["employees"] if emp["employee_id"] in known_employees]
    return tables


# --------------------------------------------------------------------------
# Writing output
# --------------------------------------------------------------------------

def _cell(value) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path.name}; check the as-of date and config")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _cell(v) for k, v in row.items()})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(config_path: Path, output_dir: Path, seed: int | None = None,
             as_of: date | None = None) -> dict:
    """Run the whole generation. Returns the manifest (also written to disk)."""
    config = load_config(config_path)
    seed = config["run"]["seed"] if seed is None else seed
    as_of = date.fromisoformat(config["run"]["as_of_date"]) if as_of is None else as_of

    truth = simulate(config, seed)
    tables = observe(truth, as_of, config["programme"]["rubric_version"], seed)
    tables["data_snapshot"] = [{
        "as_of_date": as_of,
        "seed": seed,
        "generator_version": GENERATOR_VERSION,
    }]

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "as_of_date": as_of.isoformat(),
        "config_sha256": sha256(config_path),
        "files": {},
    }
    for name, rows in tables.items():
        path = output_dir / f"{name}.csv"
        write_csv(path, rows)
        manifest["files"][path.name] = {"rows": len(rows), "sha256": sha256(path)}

    (output_dir / "generation_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, help="override run.seed from the config")
    parser.add_argument("--as-of-date", type=date.fromisoformat,
                        help="override run.as_of_date (YYYY-MM-DD)")
    args = parser.parse_args()

    manifest = generate(args.config, args.output_dir, args.seed, args.as_of_date)
    print(f"Synthetic data written to {args.output_dir}")
    print(f"  seed={manifest['seed']}  as_of_date={manifest['as_of_date']}")
    for name, info in manifest["files"].items():
        print(f"  {name:<30} {info['rows']:>6} rows  sha256={info['sha256'][:12]}")


if __name__ == "__main__":
    main()

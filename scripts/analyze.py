from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from client import resolve_client
from common import load_json, read_jsonl, workspace_paths


CONFIDENCE_PRIORITY = {"needs_review": 0, "inferred": 1, "confirmed": 2}


def merge_daily_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, tuple[int, datetime, Any, str, str]]] = defaultdict(dict)
    for record in records:
        day = record["date"]
        timestamp = datetime.fromisoformat(record["recorded_at"])
        confidence = record["confidence"]
        priority = CONFIDENCE_PRIORITY[confidence]
        for field, value in record.get("metrics", {}).items():
            candidate = (priority, timestamp, value, record["record_id"], confidence)
            current = selected[day].get(field)
            if current is None or candidate[:2] > current[:2]:
                selected[day][field] = candidate
    merged = []
    for day in sorted(selected):
        fields = selected[day]
        merged.append(
            {
                "date": day,
                "metrics": {field: item[2] for field, item in fields.items()},
                "provenance": {field: item[3] for field, item in fields.items()},
                "confidence": {field: item[4] for field, item in fields.items()},
            }
        )
    return merged


def _in_period(day: str, start: date, end: date) -> bool:
    parsed = date.fromisoformat(day)
    return start <= parsed <= end


def _average(values: list[float]) -> float | None:
    return mean(values) if values else None


def _progression_candidates(
    records: list[dict[str, Any]], start: date, end: date, rules: dict[str, Any]
) -> list[str]:
    sessions: dict[str, list[tuple[datetime, bool]]] = defaultdict(list)
    progression = rules.get("progression", {})
    required = int(progression.get("required_confirmed_sessions", 2))
    for record in records:
        if record.get("confidence") != "confirmed" or not _in_period(record["date"], start, end):
            continue
        for exercise in record.get("metrics", {}).get("exercises", []) or []:
            exercise_id = exercise.get("exercise_id")
            rep_range = exercise.get("rep_range")
            sets = exercise.get("sets") or []
            if not exercise_id or not isinstance(rep_range, list) or len(rep_range) != 2 or not sets:
                continue
            max_rpe = progression.get(
                "isolation_max_rpe" if exercise.get("category") == "isolation" else "compound_max_rpe",
                8,
            )
            eligible = all(
                item.get("qualified", True)
                and item.get("reps", 0) >= rep_range[1]
                and item.get("rpe", 99) <= max_rpe
                for item in sets
            )
            sessions[exercise_id].append((datetime.fromisoformat(record["recorded_at"]), eligible))
    candidates = []
    for exercise_id, values in sessions.items():
        recent = [eligible for _, eligible in sorted(values, reverse=True)[:required]]
        if len(recent) == required and all(recent):
            candidates.append(exercise_id)
    return sorted(candidates)


def analyze_records(
    records: list[dict[str, Any]], end_date: date, rules: dict[str, Any]
) -> dict[str, Any]:
    merged = merge_daily_records(records)
    current_start = end_date - timedelta(days=6)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    current = [item for item in merged if _in_period(item["date"], current_start, end_date)]
    previous = [item for item in merged if _in_period(item["date"], previous_start, previous_end)]

    current_weights = [float(item["metrics"]["weight_kg"]) for item in current if item["metrics"].get("weight_kg") is not None]
    previous_weights = [float(item["metrics"]["weight_kg"]) for item in previous if item["metrics"].get("weight_kg") is not None]
    current_average = _average(current_weights)
    previous_average = _average(previous_weights)
    weekly_change = (
        current_average - previous_average
        if current_average is not None and previous_average is not None
        else None
    )

    scheduled_days = [item for item in current if item["metrics"].get("training_scheduled") is True]
    observed_days = [item for item in scheduled_days if isinstance(item["metrics"].get("training_completed"), bool)]
    training_rate = (
        sum(item["metrics"]["training_completed"] is True for item in observed_days) / len(observed_days)
        if observed_days
        else None
    )
    training_coverage = len(observed_days) / len(scheduled_days) if scheduled_days else None
    nutrition_values = [
        float(item["metrics"]["nutrition_adherence"])
        for item in current
        if item["metrics"].get("nutrition_adherence") is not None
    ]

    volume_by_exercise: dict[str, float] = defaultdict(float)
    for item in current:
        for exercise in item["metrics"].get("exercises", []) or []:
            exercise_id = exercise.get("exercise_id") or "unknown"
            for work_set in exercise.get("sets", []) or []:
                if work_set.get("qualified", True) is False:
                    continue
                weight = work_set.get("weight_kg")
                reps = work_set.get("reps")
                if isinstance(weight, (int, float)) and not isinstance(weight, bool) and isinstance(reps, int):
                    volume_by_exercise[exercise_id] += float(weight) * reps

    sleeps = [float(item["metrics"]["sleep_hours"]) for item in current if item["metrics"].get("sleep_hours") is not None]
    pains = [float(item["metrics"]["pain_0_10"]) for item in current if item["metrics"].get("pain_0_10") is not None]
    fatigues = [float(item["metrics"]["fatigue_1_5"]) for item in current if item["metrics"].get("fatigue_1_5") is not None]
    safety_events = sum(len(item["metrics"].get("safety_events", []) or []) for item in current)

    flags: list[str] = []
    if len(current_weights) < 4:
        flags.append("insufficient_data")
    if pains and max(pains) >= 4:
        flags.append("pain_review")
    if safety_events:
        flags.append("safety_event")
    if (sleeps and mean(sleeps) < 6) or (fatigues and mean(fatigues) >= 4):
        flags.append("recovery_review")

    weight_rules = rules.get("weight_trend", {})
    nutrition_average = _average(nutrition_values)
    if weekly_change is not None and len(current_weights) >= 4 and len(previous_weights) >= 4:
        if previous_average and weekly_change < -(previous_average * weight_rules.get("high_loss_bodyweight_fraction", 0.01)):
            flags.append("rapid_weight_loss")
        elif (
            -weekly_change < weight_rules.get("low_loss_kg_per_week", 0.3)
            and nutrition_average is not None
            and nutrition_average >= weight_rules.get("minimum_adherence", 0.85)
        ):
            flags.append("slow_weight_change")

    candidates = _progression_candidates(records, current_start, end_date, rules)
    if "pain_review" in flags or "safety_event" in flags:
        recommendation = "safety_review"
    elif "recovery_review" in flags:
        recommendation = "deload_review"
    elif "rapid_weight_loss" in flags or "slow_weight_change" in flags:
        recommendation = "nutrition_review"
    elif candidates:
        recommendation = "eligible_low_risk_progression"
    else:
        recommendation = "hold"

    confidence_counts = {key: 0 for key in CONFIDENCE_PRIORITY}
    for record in records:
        if _in_period(record["date"], current_start, end_date):
            confidence_counts[record["confidence"]] += 1

    return {
        "period": {"start": current_start.isoformat(), "end": end_date.isoformat()},
        "data_quality": {
            "records": sum(confidence_counts.values()),
            "confidence": confidence_counts,
            "days_with_any_data": len(current),
        },
        "weight": {
            "days_present": len(current_weights),
            "average_kg": current_average,
            "previous_average_kg": previous_average,
            "weekly_change_kg": weekly_change,
        },
        "adherence": {
            "training_rate": training_rate,
            "training_coverage": training_coverage,
            "nutrition_rate": nutrition_average,
            "nutrition_days": len(nutrition_values),
        },
        "training": {
            "volume_by_exercise": dict(sorted(volume_by_exercise.items())),
            "progression_candidates": candidates,
        },
        "recovery": {
            "average_sleep_hours": _average(sleeps),
            "max_pain": max(pains) if pains else None,
            "average_fatigue": _average(fatigues),
            "safety_event_count": safety_events,
        },
        "flags": flags,
        "recommendation": recommendation,
    }


def analyze_week(root: Path, client_query: str, end_date: date) -> dict[str, Any]:
    client = resolve_client(root, client_query)
    base = root.resolve() / client["directory"]
    records = read_jsonl(base / "logs/daily.jsonl")
    rules = load_json(workspace_paths(root)["rules"])
    result = analyze_records(records, end_date, rules)
    return {"client_id": client["id"], "display_name": client["display_name"], **result}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--client", required=True)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    try:
        result = analyze_week(args.workspace, args.client, args.end_date)
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

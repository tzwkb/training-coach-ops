from __future__ import annotations

import argparse
import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from client import resolve_client
from common import atomic_write_json, load_json, workspace_paths


REQUIRED_FIELDS = {
    "client_id",
    "version",
    "effective_from",
    "effective_to",
    "phase",
    "schedule",
    "progression",
    "nutrition",
    "review_conditions",
    "approval",
}
DEFAULT_REVIEW_REASONS = {
    "calorie_change",
    "weekly_set_change",
    "weekly_cardio_change",
    "pain_exercise_change",
    "cycle_restructure",
    "initial_plan",
}


def validate_plan(plan: dict[str, Any], expected_client_id: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["plan must be an object"]
    missing = REQUIRED_FIELDS - set(plan)
    if missing:
        errors.append(f"missing fields: {', '.join(sorted(missing))}")
    if plan.get("client_id") != expected_client_id:
        errors.append("client_id mismatch")
    if isinstance(plan.get("version"), bool) or not isinstance(plan.get("version"), int) or plan.get("version", 0) < 1:
        errors.append("version must be a positive integer")
    try:
        start = date.fromisoformat(plan.get("effective_from", ""))
        end = date.fromisoformat(plan.get("effective_to", ""))
        if end < start:
            errors.append("effective_to precedes effective_from")
    except (TypeError, ValueError):
        errors.append("invalid effective date")
    if not isinstance(plan.get("phase"), dict) or not plan.get("phase"):
        errors.append("phase must be a non-empty object")
    if not isinstance(plan.get("schedule"), list):
        errors.append("schedule must be a list")
    else:
        workout_ids: list[str] = []
        for day_index, day_plan in enumerate(plan["schedule"]):
            if not isinstance(day_plan, dict) or not day_plan.get("day"):
                errors.append(f"schedule[{day_index}] missing day")
                continue
            workouts = day_plan.get("workouts", [])
            if not isinstance(workouts, list):
                errors.append(f"schedule[{day_index}].workouts must be a list")
                continue
            for workout_index, workout in enumerate(workouts):
                if not isinstance(workout, dict) or not workout.get("id"):
                    errors.append(f"schedule[{day_index}].workouts[{workout_index}] missing id")
                    continue
                workout_ids.append(workout["id"])
                sets = workout.get("sets")
                if sets is not None and (isinstance(sets, bool) or not isinstance(sets, int) or sets < 0):
                    errors.append(f"workout {workout['id']} has invalid sets")
        duplicates = sorted({item for item in workout_ids if workout_ids.count(item) > 1})
        if duplicates:
            errors.append(f"duplicate workout id: {', '.join(duplicates)}")
    if not isinstance(plan.get("progression"), dict):
        errors.append("progression must be an object")
    if not isinstance(plan.get("nutrition"), dict):
        errors.append("nutrition must be an object")
    if not isinstance(plan.get("review_conditions"), list):
        errors.append("review_conditions must be a list")
    if not isinstance(plan.get("approval"), dict):
        errors.append("approval must be an object")
    return errors


def _json_diff(current: Any, candidate: Any, path: str = "") -> list[str]:
    if type(current) is not type(candidate):
        return [path or "/"]
    if isinstance(current, dict):
        changed: list[str] = []
        for key in sorted(set(current) | set(candidate)):
            child = f"{path}/{key.replace('~', '~0').replace('/', '~1')}"
            if key not in current or key not in candidate:
                changed.append(child)
            else:
                changed.extend(_json_diff(current[key], candidate[key], child))
        return changed
    if isinstance(current, list):
        changed = []
        for index in range(max(len(current), len(candidate))):
            child = f"{path}/{index}"
            if index >= len(current) or index >= len(candidate):
                changed.append(child)
            else:
                changed.extend(_json_diff(current[index], candidate[index], child))
        return changed
    return [] if current == candidate else [path or "/"]


def _total_sets(plan: dict[str, Any]) -> int:
    return sum(
        int(workout.get("sets", 0))
        for day_plan in plan.get("schedule", [])
        for workout in day_plan.get("workouts", [])
        if isinstance(workout.get("sets", 0), int) and not isinstance(workout.get("sets", 0), bool)
    )


def diff_plans(current: dict[str, Any], candidate: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    ignored = {"version", "created_at", "change_summary", "approval"}
    current_compare = {key: value for key, value in current.items() if key not in ignored}
    candidate_compare = {key: value for key, value in candidate.items() if key not in ignored}
    changed_paths = _json_diff(current_compare, candidate_compare)
    reasons: set[str] = set()
    if current.get("nutrition", {}).get("calories") != candidate.get("nutrition", {}).get("calories"):
        reasons.add("calorie_change")
    if _total_sets(current) != _total_sets(candidate):
        reasons.add("weekly_set_change")
    if current.get("cardio", {}).get("weekly_minutes") != candidate.get("cardio", {}).get("weekly_minutes"):
        reasons.add("weekly_cardio_change")
    if current.get("phase") != candidate.get("phase"):
        reasons.add("cycle_restructure")
    explicit = candidate.get("approval", {}).get("requested_reasons", [])
    if isinstance(explicit, list):
        reasons.update(str(item) for item in explicit)
    configured = set(rules.get("review_required", DEFAULT_REVIEW_REASONS))
    review_reasons = sorted(reasons & (configured | DEFAULT_REVIEW_REASONS))
    return {
        "changed_paths": changed_paths,
        "review_reasons": review_reasons,
        "approval_required": bool(review_reasons),
        "summary": candidate.get("change_summary") or "plan update",
    }


def activate_plan(
    root: Path,
    client_query: str,
    candidate: dict[str, Any],
    expected_version: int,
    approved: bool,
) -> dict[str, Any]:
    client = resolve_client(root, client_query)
    base = root.resolve() / client["directory"]
    current_path = base / "plans/current.json"
    current = load_json(current_path) if current_path.exists() else None
    actual_version = current.get("version") if current else 0
    if actual_version != expected_version:
        raise RuntimeError("plan version conflict")

    prepared = copy.deepcopy(candidate)
    prepared["client_id"] = client["id"]
    prepared["version"] = expected_version + 1
    prepared["created_at"] = datetime.now(timezone.utc).isoformat()
    errors = validate_plan(prepared, client["id"])
    if errors:
        raise ValueError("; ".join(errors))

    rules_path = workspace_paths(root)["rules"]
    rules = load_json(rules_path, {"review_required": list(DEFAULT_REVIEW_REASONS)})
    if current is None:
        difference = {
            "changed_paths": ["/"],
            "review_reasons": ["initial_plan"],
            "approval_required": True,
            "summary": prepared.get("change_summary") or "initial plan",
        }
    else:
        difference = diff_plans(current, prepared, rules)
    if difference["approval_required"] and not approved:
        raise PermissionError(", ".join(difference["review_reasons"]))

    prepared.setdefault("approval", {})
    prepared["approval"]["status"] = "approved" if approved else "not_required"
    prepared["approval"]["review_reasons"] = difference["review_reasons"]
    if current is not None:
        archive = base / "plans/archive" / f"v{actual_version:03d}.json"
        if archive.exists():
            raise RuntimeError(f"archive already exists: {archive.name}")
        atomic_write_json(archive, current)
    atomic_write_json(current_path, prepared)

    profile_path = base / "profile.json"
    profile = load_json(profile_path)
    profile["current_plan_version"] = prepared["version"]
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(profile_path, profile)
    return {**prepared, "diff": difference}


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    activate_parser = subparsers.add_parser("activate")
    for subparser in (validate_parser, activate_parser):
        subparser.add_argument("--workspace", required=True, type=Path)
        subparser.add_argument("--client", required=True)
        subparser.add_argument("--candidate", required=True, type=Path)
    activate_parser.add_argument("--expected-version", required=True, type=int)
    activate_parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    try:
        client = resolve_client(args.workspace, args.client)
        candidate = load_json(args.candidate)
        if args.command == "validate":
            errors = validate_plan(candidate, client["id"])
            result: Any = {"ok": not errors, "errors": errors}
            code = 0 if not errors else 2
        else:
            result = activate_plan(
                args.workspace,
                args.client,
                candidate,
                args.expected_version,
                args.approved,
            )
            code = 0
    except (KeyError, OSError, PermissionError, RuntimeError, TypeError, ValueError) as error:
        result = {"error": str(error)}
        code = 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from client import resolve_client
from common import append_jsonl, atomic_write_json, read_jsonl, require_finite_number


CONFIDENCE_VALUES = {"confirmed", "inferred", "needs_review"}
NUMERIC_FIELDS = {
    "weight_kg": (20.0, 500.0),
    "waist_cm": (20.0, 300.0),
    "hip_cm": (20.0, 300.0),
    "nutrition_adherence": (0.0, 1.0),
    "steps": (0.0, 200000.0),
    "sleep_hours": (0.0, 24.0),
    "fatigue_1_5": (1.0, 5.0),
    "pain_0_10": (0.0, 10.0),
}
BOOLEAN_FIELDS = {"training_scheduled", "training_completed"}
TEXT_FIELDS = {"menstrual_status", "notes"}
LIST_FIELDS = {"exercises", "safety_events"}
ALLOWED_METRICS = set(NUMERIC_FIELDS) | BOOLEAN_FIELDS | TEXT_FIELDS | LIST_FIELDS


def _parse_date(value: Any) -> None:
    if not isinstance(value, str):
        raise ValueError("invalid date: expected ISO date string")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid date: {value}") from error


def _parse_datetime(value: Any) -> None:
    if not isinstance(value, str):
        raise ValueError("invalid recorded_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid recorded_at: {value}") from error
    if parsed.tzinfo is None:
        raise ValueError("recorded_at must include timezone")


def validate_daily_record(record: dict[str, Any], expected_client_id: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    required = {"record_id", "client_id", "date", "recorded_at", "source", "confidence", "metrics"}
    missing = required - set(record)
    if missing:
        raise ValueError(f"record missing fields: {', '.join(sorted(missing))}")
    extras = set(record) - (required | {"raw_ref"})
    if extras:
        raise ValueError(f"record has unsupported fields: {', '.join(sorted(extras))}")
    if not isinstance(record["record_id"], str) or not record["record_id"].strip():
        raise ValueError("record_id is required")
    if record["client_id"] != expected_client_id:
        raise ValueError("client_id mismatch")
    _parse_date(record["date"])
    _parse_datetime(record["recorded_at"])
    if not isinstance(record["source"], dict) or not record["source"].get("type"):
        raise ValueError("source.type is required")
    if record["confidence"] not in CONFIDENCE_VALUES:
        raise ValueError("invalid confidence")
    if not isinstance(record["metrics"], dict):
        raise ValueError("metrics must be an object")
    unsupported = set(record["metrics"]) - ALLOWED_METRICS
    if unsupported:
        raise ValueError(f"unsupported metrics: {', '.join(sorted(unsupported))}")
    for field, (minimum, maximum) in NUMERIC_FIELDS.items():
        if field not in record["metrics"] or record["metrics"][field] is None:
            continue
        value = require_finite_number(record["metrics"][field], field)
        if not minimum <= value <= maximum:
            raise ValueError(f"{field} outside allowed range")
    for field in BOOLEAN_FIELDS:
        if field in record["metrics"] and record["metrics"][field] is not None:
            if not isinstance(record["metrics"][field], bool):
                raise ValueError(f"{field} must be boolean")
    for field in TEXT_FIELDS:
        if field in record["metrics"] and record["metrics"][field] is not None:
            if not isinstance(record["metrics"][field], str):
                raise ValueError(f"{field} must be text")
    for field in LIST_FIELDS:
        if field in record["metrics"] and record["metrics"][field] is not None:
            if not isinstance(record["metrics"][field], list):
                raise ValueError(f"{field} must be a list")
    return copy.deepcopy(record)


def _safe_record_id(record: Any) -> str:
    if isinstance(record, dict):
        value = str(record.get("record_id", "unknown"))
    else:
        value = "unknown"
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.") or "unknown"


def _reject(base: Path, record: Any, error: Exception) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = base / "inbox/rejected" / f"{stamp}-{_safe_record_id(record)}.json"
    atomic_write_json(target, {"errors": [str(error)], "record": record})


def ingest_record(
    root: Path,
    client_query: str,
    record: dict[str, Any],
    raw_text: str | None,
    source_file: Path | None,
) -> dict[str, Any]:
    client = resolve_client(root, client_query)
    base = root.resolve() / client["directory"]
    if raw_text is not None and source_file is not None:
        error = ValueError("provide raw_text or source_file, not both")
        _reject(base, record, error)
        raise error
    try:
        validated = validate_daily_record(record, client["id"])
        log_path = base / "logs/daily.jsonl"
        if any(item.get("record_id") == validated["record_id"] for item in read_jsonl(log_path)):
            raise ValueError(f"duplicate record_id: {validated['record_id']}")
        if raw_text is not None:
            payload = raw_text.encode("utf-8")
            suffix = ".txt"
        elif source_file is not None:
            payload = source_file.read_bytes()
            suffix = source_file.suffix or ".bin"
        else:
            payload = b""
            suffix = ""
        if payload or raw_text == "":
            relative = Path("inbox/raw") / f"{_safe_record_id(validated)}{suffix}"
            target = base / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            validated["raw_ref"] = {
                "path": relative.as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        append_jsonl(log_path, validated)
        return validated
    except (OSError, TypeError, ValueError) as error:
        _reject(base, record, error)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--client", required=True)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--raw", type=Path)
    args = parser.parse_args()
    record = json.loads(args.record.read_text(encoding="utf-8"))
    try:
        result = ingest_record(args.workspace, args.client, record, None, args.raw)
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

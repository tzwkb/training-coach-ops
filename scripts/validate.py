from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from common import duplicate_values, load_json, workspace_paths
from plan import validate_plan


def validate_workspace(root: Path) -> dict[str, Any]:
    root = root.resolve()
    paths = workspace_paths(root)
    errors: list[str] = []
    warnings: list[str] = []
    counts = {"clients": 0, "current_plans": 0, "archived_plans": 0, "log_records": 0}
    try:
        index = load_json(paths["index"])
    except (OSError, json.JSONDecodeError) as error:
        return {"ok": False, "errors": [f"invalid client index: {error}"], "warnings": [], "counts": counts}
    clients = index.get("clients") if isinstance(index, dict) else None
    if not isinstance(clients, list):
        return {"ok": False, "errors": ["invalid client index structure"], "warnings": [], "counts": counts}
    ids = [item.get("id") for item in clients if isinstance(item, dict)]
    for duplicate in sorted(duplicate_values(item for item in ids if isinstance(item, str))):
        errors.append(f"duplicate client id: {duplicate}")
    counts["clients"] = len(clients)

    indexed_dirs: set[str] = set()
    for entry in clients:
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("directory"):
            errors.append("invalid client index entry")
            continue
        client_id = entry["id"]
        indexed_dirs.add(entry["directory"])
        base = root / entry["directory"]
        if not base.is_dir():
            errors.append(f"missing client directory: {client_id}")
            continue
        try:
            profile = load_json(base / "profile.json")
            if profile.get("client_id") != client_id:
                errors.append(f"{client_id} profile client_id mismatch")
        except (OSError, json.JSONDecodeError, AttributeError) as error:
            errors.append(f"{client_id} invalid profile: {error}")

        current_path = base / "plans/current.json"
        current_version = 0
        if current_path.exists():
            counts["current_plans"] += 1
            try:
                plan = load_json(current_path)
                plan_errors = validate_plan(plan, client_id)
                errors.extend(f"{client_id} plan {error}" for error in plan_errors)
                current_version = plan.get("version", 0) if isinstance(plan, dict) else 0
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{client_id} invalid current plan: {error}")
        archive_versions = []
        for archive in sorted((base / "plans/archive").glob("v*.json")):
            counts["archived_plans"] += 1
            match = re.fullmatch(r"v(\d+)\.json", archive.name)
            if not match:
                errors.append(f"{client_id} invalid archive name: {archive.name}")
                continue
            archive_versions.append(int(match.group(1)))
        if archive_versions and current_version <= max(archive_versions):
            errors.append(f"{client_id} current plan version is not newer than archive")

        log_path = base / "logs/daily.jsonl"
        record_ids: list[str] = []
        if log_path.exists():
            for line_number, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    errors.append(f"{client_id} invalid JSONL line {line_number}: {error}")
                    continue
                counts["log_records"] += 1
                record_ids.append(str(record.get("record_id")))
                if record.get("client_id") != client_id:
                    errors.append(f"{client_id} log client_id mismatch at line {line_number}")
                raw_ref = record.get("raw_ref")
                if raw_ref:
                    raw_path = base / raw_ref.get("path", "")
                    if not raw_path.is_file():
                        errors.append(f"{client_id} missing raw_ref: {raw_ref.get('path')}")
                    else:
                        payload = raw_path.read_bytes()
                        if raw_ref.get("bytes") != len(payload) or raw_ref.get("sha256") != hashlib.sha256(payload).hexdigest():
                            errors.append(f"{client_id} raw_ref hash mismatch: {raw_ref.get('path')}")
            for duplicate in sorted(duplicate_values(record_ids)):
                errors.append(f"{client_id} duplicate record_id: {duplicate}")

    actual_dirs = {
        f"clients/{path.name}"
        for path in paths["clients"].iterdir()
        if path.is_dir()
    } if paths["clients"].exists() else set()
    for directory in sorted(actual_dirs - indexed_dirs):
        warnings.append(f"unindexed client directory: {directory}")
    if not paths["rules"].exists():
        errors.append("missing adjustment rules")
    else:
        try:
            load_json(paths["rules"])
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"invalid adjustment rules: {error}")
    for schema_name in ("profile.schema.json", "plan.schema.json", "daily-log.schema.json"):
        if not (paths["schemas"] / schema_name).exists():
            warnings.append(f"missing schema: {schema_name}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    result = validate_workspace(args.workspace)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

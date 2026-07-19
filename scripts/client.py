from __future__ import annotations

import argparse
import copy
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import atomic_write_json, load_json, workspace_paths


CLIENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
REQUIRED_PROFILE_FIELDS = {"goal", "training", "constraints", "status"}
CLIENT_SUBDIRECTORIES = (
    "plans/archive",
    "logs",
    "reviews/weekly",
    "inbox",
    "inbox/raw",
    "inbox/rejected",
    "exports",
)


def init_workspace(root: Path) -> dict[str, str]:
    paths = workspace_paths(root)
    paths["clients"].mkdir(parents=True, exist_ok=True)
    paths["schemas"].mkdir(parents=True, exist_ok=True)
    paths["migrations"].mkdir(parents=True, exist_ok=True)
    if not paths["index"].exists():
        atomic_write_json(paths["index"], {"clients": []})
    return {key: str(value) for key, value in paths.items()}


def normalize_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _index(root: Path) -> dict[str, list[dict[str, Any]]]:
    init_workspace(root)
    value = load_json(workspace_paths(root)["index"])
    if not isinstance(value, dict) or not isinstance(value.get("clients"), list):
        raise ValueError("invalid client index")
    return value


def resolve_client(root: Path, query: str) -> dict[str, Any]:
    clients = _index(root)["clients"]
    for client in clients:
        if client["id"] == query:
            return client
    normalized = normalize_name(query)
    matches = []
    for client in clients:
        names = [client["display_name"], *client.get("aliases", [])]
        if normalized in {normalize_name(name) for name in names}:
            matches.append(client)
    if not matches:
        raise KeyError("client not found")
    if len(matches) != 1:
        ids = ", ".join(sorted(client["id"] for client in matches))
        raise ValueError(f"ambiguous client: {ids}")
    return matches[0]


def create_client(
    root: Path,
    client_id: str,
    display_name: str,
    aliases: list[str],
    profile: dict[str, Any],
) -> dict[str, Any]:
    if not CLIENT_ID_RE.fullmatch(client_id):
        raise ValueError("invalid client id")
    if not display_name.strip():
        raise ValueError("display_name is required")
    missing = REQUIRED_PROFILE_FIELDS - set(profile)
    if missing:
        raise ValueError(f"profile missing fields: {', '.join(sorted(missing))}")
    if profile["status"] not in {"draft", "active", "paused", "archived"}:
        raise ValueError("invalid profile status")
    index = _index(root)
    if any(item["id"] == client_id for item in index["clients"]):
        raise ValueError(f"client already exists: {client_id}")

    base = workspace_paths(root)["clients"] / client_id
    if base.exists():
        raise ValueError(f"client directory already exists: {client_id}")
    for child in CLIENT_SUBDIRECTORIES:
        (base / child).mkdir(parents=True, exist_ok=False if child == "plans/archive" else True)

    now = datetime.now(timezone.utc).isoformat()
    stored_profile = copy.deepcopy(profile)
    stored_profile.update(
        {
            "client_id": client_id,
            "display_name": display_name.strip(),
            "sources": copy.deepcopy(profile.get("sources", [])),
            "created_at": now,
            "updated_at": now,
        }
    )
    atomic_write_json(base / "profile.json", stored_profile)
    entry = {
        "id": client_id,
        "display_name": display_name.strip(),
        "aliases": [alias.strip() for alias in aliases if alias.strip()],
        "status": profile["status"],
        "directory": f"clients/{client_id}",
    }
    index["clients"].append(entry)
    index["clients"].sort(key=lambda item: item["id"])
    atomic_write_json(workspace_paths(root)["index"], index)
    return entry


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--workspace", required=True, type=Path)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--workspace", required=True, type=Path)
    create_parser.add_argument("--id", required=True)
    create_parser.add_argument("--name", required=True)
    create_parser.add_argument("--alias", action="append", default=[])
    create_parser.add_argument("--profile", required=True, type=Path)
    get_parser = subparsers.add_parser("get")
    get_parser.add_argument("--workspace", required=True, type=Path)
    get_parser.add_argument("--client", required=True)
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            result: Any = init_workspace(args.workspace)
        elif args.command == "create":
            result = create_client(
                args.workspace,
                args.id,
                args.name,
                args.alias,
                load_json(args.profile),
            )
        elif args.command == "get":
            result = resolve_client(args.workspace, args.client)
        else:
            result = _index(args.workspace)["clients"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    except ValueError as error:
        code = 3 if "ambiguous" in str(error) else 4
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return code


if __name__ == "__main__":
    raise SystemExit(main())

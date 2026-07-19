import json
import tempfile
import unittest
from pathlib import Path

from common import append_jsonl, atomic_write_json, load_json, workspace_paths
from client import init_workspace


class CommonStorageTests(unittest.TestCase):
    def test_atomic_json_and_jsonl_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "state.json"
            atomic_write_json(target, {"version": 1})
            self.assertEqual(load_json(target), {"version": 1})
            log = root / "daily.jsonl"
            append_jsonl(log, {"id": "r1", "value": 70.1})
            self.assertEqual(json.loads(log.read_text().strip())["id"], "r1")

    def test_init_workspace_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = init_workspace(root)
            second = init_workspace(root)
            self.assertEqual(first, second)
            self.assertEqual(load_json(root / "clients/index.json"), {"clients": []})

    def test_workspace_paths_are_absolute(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = workspace_paths(Path(tmp))
            self.assertTrue(all(path.is_absolute() for path in paths.values()))


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from client import create_client, init_workspace, resolve_client


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        init_workspace(self.root)
        self.profile = {
            "goal": {"primary": "general_fitness"},
            "training": {"experience": "beginner"},
            "constraints": {},
            "status": "draft",
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_resolve_refuses_ambiguous_alias(self):
        create_client(self.root, "client-a", "Client A", ["shared"], self.profile)
        create_client(self.root, "client-b", "Client B", ["shared"], self.profile)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            resolve_client(self.root, "shared")

    def test_create_client_builds_isolated_tree(self):
        result = create_client(self.root, "client-a", "Client A", [], self.profile)
        base = self.root / "clients/client-a"
        self.assertEqual(result["id"], "client-a")
        self.assertTrue((base / "profile.json").exists())
        for child in ("plans/archive", "logs", "reviews/weekly", "inbox", "exports"):
            self.assertTrue((base / child).is_dir())

    def test_exact_id_has_priority_over_alias(self):
        create_client(self.root, "alpha", "Alpha One", [], self.profile)
        create_client(self.root, "beta", "Beta", ["alpha"], self.profile)
        self.assertEqual(resolve_client(self.root, "alpha")["id"], "alpha")

    def test_duplicate_id_is_rejected(self):
        create_client(self.root, "alpha", "Alpha", [], self.profile)
        with self.assertRaisesRegex(ValueError, "already exists"):
            create_client(self.root, "alpha", "Another", [], self.profile)

    def test_unknown_client_is_not_created(self):
        with self.assertRaisesRegex(KeyError, "client not found"):
            resolve_client(self.root, "missing")


if __name__ == "__main__":
    unittest.main()

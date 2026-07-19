import copy
import json
import tempfile
import unittest
from pathlib import Path

from client import create_client, init_workspace
from common import atomic_write_json
from plan import activate_plan, diff_plans, validate_plan


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        init_workspace(self.root)
        profile = {"goal": {}, "training": {}, "constraints": {}, "status": "active"}
        create_client(self.root, "alpha", "Alpha", [], profile)
        self.client = self.root / "clients/alpha"
        self.current = {
            "client_id": "alpha",
            "version": 1,
            "effective_from": "2026-07-01",
            "effective_to": "2026-09-30",
            "phase": {"name": "base", "week": 1},
            "schedule": [{
                "day": "monday",
                "type": "strength",
                "workouts": [{"id": "squat", "sets": 3, "reps": [8, 10], "weight_kg": 20}],
            }],
            "cardio": {"weekly_minutes": 60},
            "progression": {"type": "double_progression"},
            "nutrition": {"calories": 1800, "protein_g": 120},
            "review_conditions": ["weekly"],
            "approval": {"status": "approved", "requested_reasons": []},
            "created_at": "2026-07-01T00:00:00+00:00",
            "change_summary": "initial",
        }
        atomic_write_json(self.client / "plans/current.json", self.current)
        self.candidate = copy.deepcopy(self.current)
        self.candidate["schedule"][0]["workouts"][0]["weight_kg"] = 22.5
        self.candidate["change_summary"] = "progressed squat"

    def tearDown(self):
        self.temp.cleanup()

    def test_activation_archives_current_and_increments_version(self):
        result = activate_plan(self.root, "alpha", self.candidate, expected_version=1, approved=True)
        self.assertEqual(result["version"], 2)
        self.assertTrue((self.client / "plans/archive/v001.json").exists())
        stored = json.loads((self.client / "plans/current.json").read_text())
        self.assertEqual(stored["schedule"][0]["workouts"][0]["weight_kg"], 22.5)

    def test_calorie_change_requires_approval(self):
        self.candidate["nutrition"]["calories"] -= 100
        with self.assertRaisesRegex(PermissionError, "calorie_change"):
            activate_plan(self.root, "alpha", self.candidate, expected_version=1, approved=False)

    def test_set_count_change_requires_approval_but_weight_change_does_not(self):
        low_risk = diff_plans(self.current, self.candidate, {})
        self.assertFalse(low_risk["approval_required"])
        self.candidate["schedule"][0]["workouts"][0]["sets"] = 4
        high_risk = diff_plans(self.current, self.candidate, {})
        self.assertIn("weekly_set_change", high_risk["review_reasons"])

    def test_version_conflict_creates_no_archive(self):
        with self.assertRaisesRegex(RuntimeError, "plan version conflict"):
            activate_plan(self.root, "alpha", self.candidate, expected_version=7, approved=True)
        self.assertEqual(list((self.client / "plans/archive").glob("*.json")), [])

    def test_initial_activation_accepts_only_expected_zero(self):
        (self.client / "plans/current.json").unlink()
        initial = copy.deepcopy(self.current)
        result = activate_plan(self.root, "alpha", initial, expected_version=0, approved=True)
        self.assertEqual(result["version"], 1)
        self.assertEqual(list((self.client / "plans/archive").glob("*.json")), [])

    def test_validate_plan_rejects_duplicate_workout_ids(self):
        invalid = copy.deepcopy(self.current)
        invalid["schedule"].append(copy.deepcopy(invalid["schedule"][0]))
        errors = validate_plan(invalid, "alpha")
        self.assertTrue(any("duplicate workout id" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

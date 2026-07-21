import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from client import create_client, init_workspace
from common import atomic_write_json
from render import render_daily, render_weekly
from validate import validate_workspace


class RenderValidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        init_workspace(self.root)
        rules = {
            "weight_trend": {"minimum_adherence": 0.85},
            "progression": {"required_confirmed_sessions": 2},
            "review_required": [],
        }
        atomic_write_json(self.root / "config/adjustment-rules.yaml", rules)
        profile = {"goal": {}, "training": {}, "constraints": {}, "status": "active"}
        create_client(self.root, "alpha", "Alpha", [], profile)
        create_client(self.root, "beta", "Beta", [], profile)
        self.plan = {
            "client_id": "alpha",
            "version": 1,
            "effective_from": "2026-07-01",
            "effective_to": "2026-09-30",
            "phase": {"name": "base", "week": 1},
            "schedule": [{
                "day": "sunday",
                "type": "strength",
                "title": "Lower Body",
                "workouts": [{"id": "sun-squat", "name": "Squat", "sets": 3, "reps": [8, 10], "rpe": 7, "rest_seconds": 90}],
            }],
            "cardio": {"weekly_minutes": 60},
            "progression": {"type": "double_progression"},
            "nutrition": {"calories": 1800, "protein_g": 120},
            "review_conditions": ["weekly"],
            "approval": {"status": "approved", "requested_reasons": []},
            "created_at": "2026-07-01T00:00:00+00:00",
            "change_summary": "initial",
        }
        atomic_write_json(self.root / "clients/alpha/plans/current.json", self.plan)
        beta = copy.deepcopy(self.plan)
        beta["client_id"] = "beta"
        beta["schedule"][0]["title"] = "Beta Secret Session"
        atomic_write_json(self.root / "clients/beta/plans/current.json", beta)

    def tearDown(self):
        self.temp.cleanup()

    def test_daily_export_contains_only_target_client(self):
        output = render_daily(self.root, "alpha", date(2026, 7, 19)).read_text()
        self.assertIn("Alpha", output)
        self.assertIn("Squat", output)
        self.assertNotIn("Beta", output)
        self.assertNotIn("Beta Secret Session", output)

    def test_weekly_export_marks_insufficient_data(self):
        output = render_weekly(self.root, "alpha", date(2026, 7, 19)).read_text()
        self.assertIn("数据不足", output)
        self.assertIn("insufficient_data", output)

    def test_daily_export_formats_numeric_ranges_with_dash(self):
        current = self.root / "clients/alpha/plans/current.json"
        plan = json.loads(current.read_text())
        plan["nutrition"]["calories"] = [1650, 1750]
        current.write_text(json.dumps(plan))
        output = render_daily(self.root, "alpha", date(2026, 7, 19)).read_text()
        self.assertIn("1650–1750 kcal", output)

    def test_daily_export_contains_week_specific_training_and_meals(self):
        current = self.root / "clients/alpha/plans/current.json"
        plan = json.loads(current.read_text())
        plan["effective_from"] = "2026-07-20"
        plan["schedule"] = [{
            "day": "monday",
            "type": "strength",
            "title": "下肢臀腿力量",
            "warmup": "史密斯深蹲前：约50%工作重量×10、70%×5，两组不计正式组。",
            "workouts": [
                {"id": "mon-smith-squat", "name": "史密斯深蹲", "sets": 3, "reps": [8, 12], "rest_seconds": 90},
                {"id": "mon-reverse-lunge", "name": "哑铃反向箭步蹲", "sets": 3, "reps_text": "每侧8–10次", "rest_seconds": 75},
            ],
            "finisher": {"name": "跑步机坡度走", "duration_minutes": 10},
        }]
        plan["progression"] = {
            "type": "double_progression",
            "weekly_rpe": {"1": 6},
            "week_1_set_cap": 2,
            "deload_week": 7,
            "deload_set_subtract": 1,
        }
        plan["nutrition"] = {
            "calories": [1650, 1750],
            "protein_g": [110, 125],
            "meal_cycle": [{
                "breakfast": "早餐A",
                "lunch": "午餐A",
                "snack": "加餐A",
                "dinner": "晚餐A",
            }],
        }
        plan["daily_targets"] = {"steps": {"1-2": "≥8,000步"}, "water": "2–2.5 L", "sleep": "7.5–9小时"}
        current.write_text(json.dumps(plan))

        output = render_daily(self.root, "alpha", date(2026, 7, 20)).read_text()

        self.assertIn("第1周", output)
        self.assertIn("史密斯深蹲前", output)
        self.assertIn("史密斯深蹲：2组×8–12次，RPE 6，休90秒", output)
        self.assertIn("哑铃反向箭步蹲：2组×每侧8–10次，RPE 6，休75秒", output)
        self.assertIn("跑步机坡度走：10分钟", output)
        self.assertIn("早餐：早餐A", output)
        self.assertIn("午餐：午餐A", output)
        self.assertIn("加餐：加餐A", output)
        self.assertIn("晚餐：晚餐A", output)
        self.assertIn("≥8,000步", output)

    def test_validator_detects_plan_client_mismatch(self):
        current = self.root / "clients/alpha/plans/current.json"
        plan = json.loads(current.read_text())
        plan["client_id"] = "beta"
        current.write_text(json.dumps(plan))
        result = validate_workspace(self.root)
        self.assertFalse(result["ok"])
        self.assertIn("client_id mismatch", " ".join(result["errors"]))

    def test_validator_detects_duplicate_log_ids_and_missing_raw_ref(self):
        log = self.root / "clients/alpha/logs/daily.jsonl"
        record = {
            "record_id": "same",
            "client_id": "alpha",
            "date": "2026-07-19",
            "recorded_at": "2026-07-19T08:00:00+00:00",
            "source": {"type": "test"},
            "confidence": "confirmed",
            "metrics": {},
            "raw_ref": {"path": "inbox/raw/missing.txt", "sha256": "0" * 64, "bytes": 1},
        }
        log.write_text(json.dumps(record) + "\n" + json.dumps(record) + "\n")
        result = validate_workspace(self.root)
        joined = " ".join(result["errors"])
        self.assertIn("duplicate record_id", joined)
        self.assertIn("missing raw_ref", joined)


if __name__ == "__main__":
    unittest.main()

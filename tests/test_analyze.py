import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from analyze import analyze_records, analyze_week, merge_daily_records
from client import create_client, init_workspace
from ingest import ingest_record


RULES = {
    "weight_trend": {
        "baseline_days": 14,
        "maintain_loss_kg_per_week": [0.4, 0.8],
        "low_loss_kg_per_week": 0.3,
        "high_loss_bodyweight_fraction": 0.01,
        "minimum_adherence": 0.85,
    },
    "progression": {
        "required_confirmed_sessions": 2,
        "compound_max_rpe": 8,
        "isolation_max_rpe": 9,
    },
}


def record(record_id, day, metrics, confidence="confirmed", hour=8):
    return {
        "record_id": record_id,
        "client_id": "alpha",
        "date": day.isoformat(),
        "recorded_at": datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc).isoformat(),
        "source": {"type": "test"},
        "confidence": confidence,
        "metrics": metrics,
    }


class AnalyzeTests(unittest.TestCase):
    def test_merge_prefers_confirmed_then_latest(self):
        day = date(2026, 7, 19)
        records = [
            record("inferred", day, {"weight_kg": 70.0}, "inferred", 12),
            record("confirmed-old", day, {"weight_kg": 69.9}, "confirmed", 8),
            record("confirmed-new", day, {"weight_kg": 69.8}, "confirmed", 10),
        ]
        merged = merge_daily_records(records)
        self.assertEqual(merged[0]["metrics"]["weight_kg"], 69.8)
        self.assertEqual(merged[0]["provenance"]["weight_kg"], "confirmed-new")

    def test_weekly_weight_uses_daily_latest_confirmed_value(self):
        end = date(2026, 7, 19)
        records = [
            record(f"r{i}", end - timedelta(days=6 - i), {"weight_kg": 70.0 - i * 0.1})
            for i in range(7)
        ]
        records.append(record("override", end, {"weight_kg": 68.9}, "confirmed", 23))
        result = analyze_records(records, end_date=end, rules=RULES)
        self.assertEqual(result["weight"]["days_present"], 7)
        self.assertAlmostEqual(result["weight"]["average_kg"], 69.6286, places=4)

    def test_missing_log_is_not_failed_adherence(self):
        result = analyze_records([], end_date=date(2026, 7, 19), rules=RULES)
        self.assertIsNone(result["adherence"]["training_rate"])
        self.assertIn("insufficient_data", result["flags"])

    def test_pain_four_forces_safety_review(self):
        day = date(2026, 7, 19)
        result = analyze_records(
            [record("pain", day, {"pain_0_10": 4, "nutrition_adherence": 1.0})],
            end_date=day,
            rules=RULES,
        )
        self.assertIn("pain_review", result["flags"])
        self.assertEqual(result["recommendation"], "safety_review")

    def test_missing_completion_is_coverage_gap_not_failure(self):
        day = date(2026, 7, 19)
        records = [
            record("scheduled", day, {"training_scheduled": True}),
            record("other", day - timedelta(days=1), {"training_scheduled": True, "training_completed": True}),
        ]
        result = analyze_records(records, end_date=day, rules=RULES)
        self.assertEqual(result["adherence"]["training_rate"], 1.0)
        self.assertEqual(result["adherence"]["training_coverage"], 0.5)

    def test_training_volume_counts_only_qualified_sets(self):
        day = date(2026, 7, 19)
        exercises = [{
            "exercise_id": "squat",
            "category": "compound",
            "rep_range": [8, 10],
            "sets": [
                {"weight_kg": 20, "reps": 10, "rpe": 8, "qualified": True},
                {"weight_kg": 20, "reps": 8, "rpe": 9, "qualified": False},
            ],
        }]
        result = analyze_records([record("workout", day, {"exercises": exercises})], day, RULES)
        self.assertEqual(result["training"]["volume_by_exercise"]["squat"], 200.0)


class AnalyzeWorkspaceTests(unittest.TestCase):
    def test_analyze_week_reads_only_resolved_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_workspace(root)
            profile = {"goal": {}, "training": {}, "constraints": {}, "status": "active"}
            create_client(root, "alpha", "Alpha", [], profile)
            day = date(2026, 7, 19)
            ingest_record(root, "alpha", record("r1", day, {"weight_kg": 70.0}), None, None)
            rules_path = root / "config/adjustment-rules.yaml"
            rules_path.write_text(__import__("json").dumps(RULES))
            result = analyze_week(root, "alpha", day)
            self.assertEqual(result["client_id"], "alpha")
            self.assertEqual(result["weight"]["days_present"], 1)


if __name__ == "__main__":
    unittest.main()

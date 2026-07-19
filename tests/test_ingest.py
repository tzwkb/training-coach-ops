import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from client import create_client, init_workspace
from ingest import ingest_record


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        init_workspace(self.root)
        profile = {
            "goal": {"primary": "strength"},
            "training": {"experience": "beginner"},
            "constraints": {},
            "status": "active",
        }
        create_client(self.root, "alpha", "Alpha", [], profile)
        create_client(self.root, "beta", "Beta", [], profile)

    def tearDown(self):
        self.temp.cleanup()

    def record(self, record_id):
        return {
            "record_id": record_id,
            "client_id": "alpha",
            "date": "2026-07-19",
            "recorded_at": "2026-07-19T08:00:00+08:00",
            "source": {"type": "chat", "label": "coach"},
            "confidence": "confirmed",
            "metrics": {"weight_kg": 70.1},
        }

    def test_ingest_keeps_two_same_day_records(self):
        ingest_record(self.root, "alpha", self.record("r1"), "晨重 70.1", None)
        ingest_record(self.root, "alpha", self.record("r2"), "训练完成", None)
        lines = (self.root / "clients/alpha/logs/daily.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 2)

    def test_ingest_rejects_cross_client_record(self):
        record = self.record("r1")
        record["client_id"] = "beta"
        with self.assertRaisesRegex(ValueError, "client_id mismatch"):
            ingest_record(self.root, "alpha", record, None, None)

    def test_duplicate_record_id_is_rejected(self):
        ingest_record(self.root, "alpha", self.record("r1"), None, None)
        with self.assertRaisesRegex(ValueError, "duplicate record_id"):
            ingest_record(self.root, "alpha", self.record("r1"), None, None)

    def test_raw_text_is_saved_with_hash(self):
        result = ingest_record(self.root, "alpha", self.record("r1"), "晨重 70.1", None)
        raw = self.root / "clients/alpha" / result["raw_ref"]["path"]
        self.assertEqual(raw.read_text(), "晨重 70.1")
        self.assertEqual(result["raw_ref"]["sha256"], hashlib.sha256(raw.read_bytes()).hexdigest())

    def test_invalid_date_is_rejected_without_changing_fact_log(self):
        ingest_record(self.root, "alpha", self.record("r1"), None, None)
        log = self.root / "clients/alpha/logs/daily.jsonl"
        before = hashlib.sha256(log.read_bytes()).hexdigest()
        invalid = self.record("bad-date")
        invalid["date"] = "2026-02-30"
        with self.assertRaisesRegex(ValueError, "invalid date"):
            ingest_record(self.root, "alpha", invalid, None, None)
        self.assertEqual(before, hashlib.sha256(log.read_bytes()).hexdigest())
        rejected = list((self.root / "clients/alpha/inbox/rejected").glob("*.json"))
        self.assertEqual(len(rejected), 1)
        self.assertEqual(json.loads(rejected[0].read_text())["record"]["record_id"], "bad-date")


if __name__ == "__main__":
    unittest.main()

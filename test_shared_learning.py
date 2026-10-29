"""Shared learning provenance and append-only import; no desktop calls."""
import copy
import tempfile
import unittest
from pathlib import Path

from game_learning import LearningStore


class SharedLearningTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(LearningStore, "export_records", None)), "Shared learning is not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a = LearningStore(Path(self.temp.name) / "a.db", computer_id="primary")
        self.b = LearningStore(Path(self.temp.name) / "b.db", computer_id="agenttwo")

    def record(self, **changes):
        data = dict(title="Move left", category="control", status="verified", source="bridge_action",
                    attempted="A for 300ms", expected="Move left", before="In bed", observed="Left of bed",
                    evidence=["notes.md#move"], context={"bindings": "default"})
        data.update(changes)
        return self.a.record("Pointer Mode", **data)

    def test_empty_shared_read_creates_nothing(self):
        self.assertEqual(self.b.recall_shared("Pointer Mode")["lessons"], [])
        self.assertFalse(self.b.path.exists())

    def test_shared_recall_keeps_origin_verification_separate(self):
        row = self.record()
        bundle = self.a.export_records("AgentOne")
        self.assertEqual(self.b.import_records(bundle), 1)
        remote = self.b.recall_shared("Pointer Mode")["lessons"][0]
        self.assertEqual(remote["id"], row["id"])
        self.assertEqual(remote["computer_id"], "primary")
        self.assertEqual(remote["helper"], "AgentOne")
        self.assertEqual(remote["status"], "verified")
        self.assertFalse(remote["tested_on_this_pc"])
        self.assertTrue(remote["requires_local_check"])
        self.assertEqual(self.b.recall("Pointer Mode")["total_lessons"], 0)
        self.assertEqual(self.b.export_records("AgentTwo"), [])
        with self.assertRaises(ValueError):
            self.b.correct(row["id"], status="failed", source="bridge_action", observed="No movement",
                           evidence=["retest"], reason="Foreign lesson cannot be corrected locally")

    def test_duplicate_import_and_corrections_preserve_failure_history(self):
        row = self.record(status="failed", observed="No movement")
        self.b.import_records(self.a.export_records("AgentOne"))
        self.a.correct(row["id"], status="verified", source="bridge_action", observed="Moved",
                       evidence=["retest"], reason="Recovery")
        records = self.a.export_records("AgentOne")
        self.assertEqual(self.b.import_records(list(reversed(records))), 1)
        self.assertEqual(self.b.import_records(records), 0)
        result = self.b.recall_shared("Pointer Mode")
        self.assertEqual(result["total_lessons"], 1)
        self.assertEqual(result["recorded_failures"], 1)
        self.assertTrue(result["lessons"][0]["had_failure"])
        history = self.b.shared_history(row["lesson_id"], "primary")["records"]
        self.assertEqual([r["status"] for r in history], ["failed", "verified"])
        self.assertEqual(self.b.shared_history(row["lesson_id"], "different-pc")["records"], [])

    def test_conflicting_or_invalid_import_is_atomic(self):
        self.record()
        original = self.a.export_records("AgentOne")
        self.b.import_records(original)
        self.record(title="New lesson")
        batch = self.a.export_records("AgentOne")
        batch[0]["record"]["observed"] = "Changed immutable record"
        with self.assertRaises(ValueError):
            self.b.import_records(list(reversed(batch)))
        self.assertEqual(self.b.recall_shared("Pointer Mode")["total_lessons"], 1)
        for change in (lambda x: x[0].update(schema_version=999),
                       lambda x: x[0]["record"].update(status="verified", source="demonstration"),
                       lambda x: x[0]["record"].update(created_at="not a timestamp"),
                       lambda x: x[0]["record"].update(extra="execute me")):
            broken = copy.deepcopy(original)
            change(broken)
            with self.assertRaises(ValueError):
                self.b.import_records(broken)

    def test_missing_ancestor_is_rejected_and_own_records_are_not_imported(self):
        row = self.record()
        self.a.correct(row["id"], status="uncertain", source="user_explanation", observed="Need new check",
                       evidence=[], reason="Different settings")
        bundle = self.a.export_records("AgentOne")
        with self.assertRaises(ValueError):
            self.b.import_records(bundle[1:])
        self.assertEqual(self.a.import_records(bundle), 0)
        self.assertEqual(self.a.recall_shared("Pointer Mode")["total_lessons"], 0)


if __name__ == "__main__":
    unittest.main()

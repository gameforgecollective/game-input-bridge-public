"""Learning journal tests use temporary files and never import input backends."""

import concurrent.futures
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

if importlib.util.find_spec("game_learning"):
    from game_learning import LearningStore
else:
    LearningStore = None


class LearningStoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(LearningStore, "Learning System journal is not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "learning" / "journal.sqlite3"
        self.store = LearningStore(self.path, computer_id="primary-pc")

    def record(self, store=None, game="Pointer Mode", **changes):
        data = dict(title="Walk out of bed", category="control", status="verified",
                    source="bridge_action", attempted="Hold A for 300 ms",
                    expected="Move left", before="AgentOne is in bed",
                    observed="AgentOne is standing left of the bed",
                    evidence=["playtests/before.jpg", "playtests/after.jpg"],
                    context={"resolution": "1280x703", "bindings": "default"})
        data.update(changes)
        return (store or self.store).record(game, **data)

    def test_read_only_empty_recall_and_history_do_not_create_database(self):
        result = self.store.recall("Pointer Mode")
        self.assertEqual(result["lessons"], [])
        self.assertEqual(result["total_lessons"], 0)
        self.assertEqual(self.store.history("00000000-0000-0000-0000-000000000000")["records"], [])
        self.assertFalse(self.path.parent.exists())

    def test_persists_across_reconnect_and_normalizes_game_title(self):
        record = self.record()
        reopened = LearningStore(self.path, computer_id="primary-pc")
        result = reopened.recall("pointer_mode")
        self.assertEqual(result["lessons"][0]["id"], record["id"])
        self.assertEqual(record["game_id"], "pointer_mode")
        self.assertEqual(record["computer_id"], "primary-pc")
        self.assertTrue(record["created_at"].endswith("+00:00"))
        self.assertFalse(result["controls_authorized"])
        self.assertEqual(result["evidence_verification"], "caller_reported")

    def test_keeps_games_and_computers_separate(self):
        self.record()
        self.record(game="Camera Mode")
        other = LearningStore(self.path, computer_id="agentthree-pc")
        self.assertEqual(other.recall("Pointer Mode")["lessons"], [])
        self.record(store=other)
        self.assertEqual(self.store.recall("Pointer Mode")["total_lessons"], 1)
        self.assertEqual(self.store.recall("Camera Mode")["total_lessons"], 1)
        self.assertEqual(other.history(self.store.recall("Pointer Mode")["lessons"][0]["lesson_id"])["records"], [])

    def test_correction_preserves_failure_and_rejects_stale_revision(self):
        failed = self.record(status="failed", observed="No visible movement")
        corrected = self.store.correct(failed["id"], status="verified", source="bridge_action",
            observed="AgentOne moved left after switching backend",
            evidence=["playtests/retest.jpg"], reason="Successful physical-key retest")
        result = self.store.recall("Pointer Mode")
        self.assertEqual(result["total_lessons"], 1)
        self.assertEqual(result["recorded_failures"], 1)
        self.assertEqual(result["current_counts"]["verified"], 1)
        self.assertTrue(result["lessons"][0]["had_failure"])
        self.assertEqual(corrected["supersedes_id"], failed["id"])
        history = self.store.history(failed["lesson_id"])["records"]
        self.assertEqual([row["status"] for row in history], ["failed", "verified"])
        with self.assertRaisesRegex(ValueError, "latest"):
            self.store.correct(failed["id"], status="uncertain", source="user_explanation",
                observed="Old update", evidence=[], reason="stale")
        self.assertEqual(len(self.store.history(failed["lesson_id"])["records"]), 2)

    def test_cannot_correct_another_computers_record(self):
        row = self.record()
        other = LearningStore(self.path, computer_id="agenttwo-pc")
        with self.assertRaises(ValueError):
            other.correct(row["id"], status="failed", source="bridge_action",
                observed="Unrelated PC", evidence=["image"], reason="Wrong scope")

    def test_demonstrations_and_explanations_cannot_claim_verified_play(self):
        for source in ("demonstration", "user_explanation"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.record(source=source)
        watched = self.record(status="observed", source="demonstration")
        self.assertEqual(watched["status"], "observed")
        with self.assertRaises(ValueError):
            self.record(status="observed", source="bridge_action")

    def test_verified_or_observed_require_evidence_and_verified_requires_comparison(self):
        for change in ({"evidence": []}, {"before": ""}, {"expected": ""}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.record(**change)
        with self.assertRaises(ValueError):
            self.record(status="observed", source="demonstration", evidence=[])
        self.record(status="uncertain", source="user_explanation", evidence=[], before="")

    def test_rejects_malformed_and_oversized_records_before_storage(self):
        invalid = [dict(title=""), dict(status="done"), dict(source="auto"),
                   dict(category="script"), dict(observed="x" * 4001),
                   dict(evidence="photo"), dict(evidence=[""]),
                   dict(context={"execute": {"code": "bad"}}), dict(context={"max_hold_ms": 9000})]
        for change in invalid:
            with self.subTest(change=str(change)[:70]), self.assertRaises(ValueError):
                self.record(**change)
        for game in ("../escape", "C:\\game", "", "a" * 81, 12):
            with self.subTest(game=game), self.assertRaises(ValueError):
                self.record(game=game)
        self.assertFalse(self.path.exists())

    def test_unknown_game_can_store_data_without_creating_executable_profile(self):
        row = self.record(game="A New Game", status="uncertain", source="user_explanation",
                          observed="User says Q interacts", evidence=[])
        self.assertEqual(row["game_id"], "a_new_game")
        from game_input_controls import game_profile_for_window
        self.assertEqual(game_profile_for_window("A New Game")[0], "unverified")

    def test_game_names_support_punctuation_and_unicode_without_accepting_paths(self):
        row = self.record(game="Sample Adventure: Chapter One")
        self.assertEqual(row["game_id"], "sample_adventure_chapter_one")
        self.record(game="Démo: Let's Go!")
        self.assertEqual(self.store.recall("Démo: Let's Go!")["total_lessons"], 1)
        with self.assertRaises(ValueError):
            self.record(game="C:game")

    def test_pagination_and_invalid_limits(self):
        first = self.record(title="First")
        second = self.record(title="Second")
        page = self.store.recall("Pointer Mode", limit=1)
        self.assertEqual(page["lessons"][0]["id"], second["id"])
        self.assertTrue(page["has_more"])
        self.assertEqual(self.store.recall("Pointer Mode", limit=1, offset=1)["lessons"][0]["id"], first["id"])
        for args in ({"limit": 0}, {"limit": 51}, {"limit": True}, {"offset": -1}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.store.recall("Pointer Mode", **args)

    def test_concurrent_writers_do_not_lose_lessons(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            rows = list(pool.map(lambda n: self.record(title=f"Lesson {n}"), range(18)))
        self.assertEqual(len({r["id"] for r in rows}), 18)
        self.assertEqual(self.store.recall("Pointer Mode")["total_lessons"], 18)

    def test_corrupt_store_is_reported_without_replacing_it(self):
        self.path.parent.mkdir()
        self.path.write_bytes(b"not a database")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.recall("Pointer Mode")
        self.assertEqual(self.path.read_bytes(), b"not a database")


if __name__ == "__main__":
    unittest.main()

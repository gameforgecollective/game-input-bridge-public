"""Real Git exchange tests with temporary bare repositories, never the network."""
import concurrent.futures
import ctypes
import importlib.util
import json
import os
import subprocess
import shlex
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from game_learning import LearningStore
if importlib.util.find_spec("game_learning_sync"):
    from game_learning_sync import GitLearningExchange, configured_exchange
else:
    GitLearningExchange = configured_exchange = None


def git(*args, cwd=None):
    return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@localhost", *args],
                          cwd=cwd, capture_output=True, text=True, check=True).stdout


class LearningSyncTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(GitLearningExchange, "Shared Git exchange is not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        git("init", "--bare", str(self.remote))
        seed = self.root / "seed"
        git("init", "-b", "learning-exchange", str(seed))
        (seed / ".game-learning-exchange.json").write_text(json.dumps({"schema_version": 1, "kind": "game-learning-exchange"}))
        git("add", ".", cwd=seed)
        git("commit", "-m", "Initialize test exchange", cwd=seed)
        git("push", str(self.remote), "HEAD:refs/heads/learning-exchange", cwd=seed)
        self.stores = [LearningStore(self.root / f"pc{i}.db", computer_id=f"pc{i}") for i in range(3)]

    def record(self, store, title):
        return store.record("Sharing Smoke Test", title=title, category="question", status="uncertain",
            source="user_explanation", attempted="Synthetic exchange fixture; no game input",
            expected="Other PCs can recall this fixture", before="", observed="Synthetic local record",
            evidence=[], context={"fixture": "true"})

    def test_three_peers_exchange_without_duplicates_and_keep_corrections(self):
        exchanges = [GitLearningExchange(s, str(self.remote), name) for s, name in zip(self.stores, ["AgentOne", "AgentTwo", "AgentThree"])]
        first = self.record(self.stores[0], "AgentOne fixture")
        for n in range(1, 3):
            self.record(self.stores[n], f"Peer {n} fixture")
        for ex in exchanges:
            self.assertTrue(ex.sync()["ok"])
        for ex in exchanges:
            self.assertTrue(ex.sync()["ok"])
        for store in self.stores:
            self.assertEqual(store.recall_shared("Sharing Smoke Test")["total_lessons"], 2)
            self.assertEqual(store.recall("Sharing Smoke Test")["total_lessons"], 1)
        self.stores[0].correct(first["id"], status="failed", source="user_explanation",
            observed="Synthetic failure report", evidence=[], reason="Test retained history")
        self.assertTrue(exchanges[0].sync()["ok"])
        self.assertTrue(exchanges[1].sync()["ok"])
        self.assertEqual(self.stores[1].recall_shared("Sharing Smoke Test")["recorded_failures"], 1)

    def test_concurrent_publish_does_not_lose_records(self):
        exchanges = [GitLearningExchange(s, str(self.remote), f"Helper{n}", timeout=25) for n, s in enumerate(self.stores)]
        for n, s in enumerate(self.stores):
            self.record(s, f"Concurrent {n}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda e: e.sync(), exchanges))
        self.assertTrue(all(r["ok"] for r in results), results)
        for ex in exchanges:
            self.assertTrue(ex.sync()["ok"])
            self.assertEqual(ex.store.recall_shared("Sharing Smoke Test")["total_lessons"], 2)

    def test_offline_failure_keeps_local_lesson(self):
        row = self.record(self.stores[0], "Offline fixture")
        result = GitLearningExchange(self.stores[0], str(self.root / "missing.git"), "AgentOne").sync()
        self.assertFalse(result["ok"])
        self.assertTrue(result["pending_sync"])
        self.assertEqual(self.stores[0].recall("Sharing Smoke Test")["lessons"][0]["id"], row["id"])

    def test_missing_configuration_does_not_enable_sharing(self):
        self.assertIsNone(configured_exchange(self.stores[0], self.root / "absent.json"))
        config = self.root / "sharing.json"
        config.write_text(json.dumps({"enabled": True, "helper": "AgentOne", "remote": str(self.remote), "branch": "main"}))
        with self.assertRaises(ValueError):
            configured_exchange(self.stores[0], config)

    def test_non_exchange_branch_marker_is_rejected(self):
        seed = self.root / "seed"
        (seed / ".game-learning-exchange.json").write_text('{}')
        git("add", ".", cwd=seed)
        git("commit", "-m", "Invalid marker fixture", cwd=seed)
        git("push", str(self.remote), "HEAD:refs/heads/learning-exchange", cwd=seed)
        result = GitLearningExchange(self.stores[0], str(self.remote), "AgentOne").sync()
        self.assertFalse(result["ok"])
        self.assertFalse(self.stores[0].path.exists())

    def test_combined_export_limits_reject_push_without_wedging_remote(self):
        a = GitLearningExchange(self.stores[0], str(self.remote), "AgentOne")
        b = GitLearningExchange(self.stores[1], str(self.remote), "AgentTwo")
        self.record(self.stores[0], "First fixture")
        self.record(self.stores[1], "Second fixture")
        self.assertTrue(a.sync()["ok"])
        before = git("--git-dir=" + str(self.remote), "rev-parse", "learning-exchange")
        sizes = [len((json.dumps(store.export_records(helper)[0], ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
                 for store, helper in zip(self.stores, ["AgentOne", "AgentTwo"])]
        for setting, bound in (("MAX_RECORDS", 1), ("MAX_EXCHANGE_BYTES", max(sizes) + 10)):
            with self.subTest(setting=setting), patch("game_learning_sync." + setting, bound):
                result = b.sync()
                self.assertFalse(result["ok"], result)
                self.assertTrue(result["pending_sync"])
            self.assertEqual(git("--git-dir=" + str(self.remote), "rev-parse", "learning-exchange"), before)
        self.assertEqual(self.stores[1].recall("Sharing Smoke Test")["total_lessons"], 1)
        self.assertTrue(b.sync()["ok"])

    def test_git_timeout_also_releases_descendant_pipe_handles(self):
        exchange = GitLearningExchange(self.stores[0], str(self.remote), "AgentOne")
        python = shlex.quote(sys.executable.replace("\\", "/"))
        alias = "!" + python + " -c " + shlex.quote("import time; time.sleep(4)")
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            exchange._git(["-c", "alias.waitfixture=" + alias, "waitfixture"],
                          started + 0.2, cwd=self.root / "seed")
        self.assertLess(time.monotonic() - started, 3, "Git descendants retained the pipe past the timeout")

    @unittest.skipUnless(os.name == "nt", "Windows owned-job lifecycle regression")
    def test_timeout_terminates_orphan_after_git_root_has_exited(self):
        pidfile = self.root / "owned-child.pid"
        launcher = self.root / "orphan_fixture.py"
        child = "import os,pathlib,time; pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(os.getpid())); time.sleep(8)"
        launcher.write_text("import subprocess,sys\nsubprocess.Popen([sys.executable,'-c'," + repr(child) + "])\n", encoding="utf-8")
        python = shlex.quote(sys.executable.replace("\\", "/"))
        alias = "!" + python + " " + shlex.quote(str(launcher).replace("\\", "/"))
        exchange = GitLearningExchange(self.stores[0], str(self.remote), "AgentOne")
        with self.assertRaises(subprocess.TimeoutExpired):
            exchange._git(["-c", "alias.orphanfixture=" + alias, "orphanfixture"],
                          time.monotonic() + 1, cwd=self.root / "seed")
        self.assertTrue(pidfile.exists(), "Fixture must actually spawn its child")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x100001, False, int(pidfile.read_text()))
        if handle:
            try:
                state = kernel.WaitForSingleObject(handle, 1000)
                if state != 0:
                    kernel.TerminateProcess(handle, 1)  # Only this fixture's recorded child.
                self.assertEqual(state, 0, "Owned descendant survived after Git root exited")
            finally:
                kernel.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()

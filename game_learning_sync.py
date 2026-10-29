"""Opt-in private Git exchange for lesson data; no game or desktop APIs."""

import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from game_learning import _text
from game_learning_process import WindowsGitJob

BRANCH = "learning-exchange"
MARKER = {"schema_version": 1, "kind": "game-learning-exchange"}
MAX_RECORDS = 2000
MAX_FILE_BYTES = 65536
MAX_EXCHANGE_BYTES = 8 * 1024 * 1024


def record_path(envelope):
    row = envelope["record"]
    origin = hashlib.sha256(row["computer_id"].encode("utf-8")).hexdigest()[:24]
    return Path("records") / origin / (row["id"] + ".json")


class GitLearningExchange:
    def __init__(self, store, remote, helper, branch=BRANCH, timeout=20):
        self.store = store
        self.helper = _text(helper, "helper", 50)
        self.remote = _text(remote, "remote", 1000)
        parsed = urlsplit(self.remote)
        https = parsed.scheme == "https" and parsed.hostname == "github.com" and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
        local = Path(self.remote).is_absolute() and not self.remote.startswith(("\\\\", "//"))
        if not (https or local):
            raise ValueError("Sharing needs a GitHub HTTPS URL without credentials, or an absolute local test repository.")
        if branch != BRANCH:
            raise ValueError("Learning exchange must use its separate learning-exchange branch.")
        if type(timeout) not in (int, float) or not 1 <= timeout <= 30:
            raise ValueError("Sync timeout must be from 1 to 30 seconds.")
        self.timeout = timeout

    def _git(self, args, deadline, *, cwd=None, check=True):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Learning sync time budget expired; local records retained.")
        command = ["git", "-c", "credential.interactive=never", *args]
        job = WindowsGitJob() if os.name == "nt" else None
        process = None
        try:
            process = subprocess.Popen(command, cwd=cwd,
                env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never"),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                start_new_session=os.name != "nt",
                creationflags=(subprocess.CREATE_NO_WINDOW | 0x4) if job else 0)  # CREATE_SUSPENDED
            if job:
                job.assign_and_resume(process)
            try:
                stdout, stderr = process.communicate(timeout=min(remaining, 10))
            except subprocess.TimeoutExpired:
                if job:
                    job.close()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if process.poll() is None:
                    process.kill()
                try:
                    process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
                raise
        finally:
            if job:
                job.close()
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=1)
        result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        if check and result.returncode:
            # Do not expose credential-helper diagnostics or URLs containing secrets.
            raise RuntimeError(f"Git {args[0]} failed (exit {result.returncode}); local learning retained.")
        return result

    def _read_exchange(self, repository):
        marker = repository / ".game-learning-exchange.json"
        if marker.is_symlink() or marker.stat().st_size > 1024 or json.loads(marker.read_text(encoding="utf-8-sig")) != MARKER:
            raise ValueError("Remote branch is not a supported learning exchange.")
        directory = repository / "records"
        if directory.is_symlink():
            raise ValueError("Exchange records directory must not be a symbolic link.")
        if directory.exists() and any(p.is_symlink() for p in directory.rglob("*")):
            raise ValueError("Exchange records must not contain symbolic links.")
        files = sorted(directory.rglob("*.json")) if directory.exists() else []
        if len(files) > MAX_RECORDS:
            raise ValueError("Exchange exceeds its 2000-record limit; local learning retained.")
        envelopes, total = [], 0
        for path in files:
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError("Exchange record path escapes the records directory.")
            size = path.stat().st_size
            total += size
            if size > MAX_FILE_BYTES or total > MAX_EXCHANGE_BYTES:
                raise ValueError("Exchange exceeds its bounded data size.")
            item = json.loads(path.read_text(encoding="utf-8"))
            if path.relative_to(repository) != record_path(item):
                raise ValueError("Exchange record path does not match its origin and ID.")
            envelopes.append(item)
        return envelopes

    def sync(self):
        """Bounded best-effort exchange. Local records are authoritative and durable."""
        result = dict(configured=True, ok=False, pending_sync=True, helper=self.helper,
                      computer_id=self.store.computer_id, imported_records=0, published_records=0)
        deadline = time.monotonic() + self.timeout
        try:
            own = self.store.export_records(self.helper)
            if len(own) > MAX_RECORDS:
                raise ValueError("Local export exceeds the exchange record limit.")
            for attempt in range(3):
                # Only this temporary checkout is mutated or cleaned up, never a user's repo.
                with tempfile.TemporaryDirectory(prefix="game-learning-sync-") as temporary:
                    repository = Path(temporary) / "exchange"
                    self._git(["clone", "--no-local", "--depth", "1", "--branch", BRANCH, "--", self.remote, str(repository)], deadline)
                    incoming = self._read_exchange(repository)
                    pending = []
                    total_bytes = sum(p.stat().st_size for p in (repository / "records").rglob("*.json"))
                    for item in own:
                        target = repository / record_path(item)
                        if not target.resolve().is_relative_to((repository / "records").resolve()):
                            raise ValueError("Published record target escapes the records directory.")
                        for ancestor in (target, *target.parents):
                            if ancestor == repository:
                                break
                            if ancestor.is_symlink():
                                raise ValueError("Published record target must not follow symbolic links.")
                        encoded = json.dumps(item, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
                        if len(encoded.encode("utf-8")) > MAX_FILE_BYTES:
                            raise ValueError("Local record exceeds the exchange file size limit.")
                        if target.exists():
                            if json.loads(target.read_text(encoding="utf-8")) != item:
                                raise ValueError("Immutable published record differs; no overwrite performed.")
                        else:
                            pending.append((target, encoded))
                            total_bytes += len(encoded.encode("utf-8"))
                    if len(incoming) + len(pending) > MAX_RECORDS or total_bytes > MAX_EXCHANGE_BYTES:
                        raise ValueError("Combined exchange would exceed its record/byte limit; no push performed and local learning retained.")
                    result["imported_records"] += self.store.import_records(incoming)
                    for target, encoded in pending:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(encoded, encoding="utf-8", newline="\n")
                    if pending:
                        self._git(["add", "--", "records"], deadline, cwd=repository)
                        self._git(["-c", "user.name=Game Learning", "-c", "user.email=learning@localhost",
                                   "commit", "-m", "Share immutable game learning records"], deadline, cwd=repository)
                        pushed = self._git(["push", "origin", "HEAD:refs/heads/" + BRANCH], deadline, cwd=repository, check=False)
                        if pushed.returncode:
                            if attempt < 2:
                                continue
                            raise RuntimeError("Git push could not complete after concurrent-update retries; local learning retained.")
                    result.update(ok=True, pending_sync=False, published_records=len(own),
                                  synced_at=datetime.now(timezone.utc).isoformat())
                    return result
            raise RuntimeError("Learning sync retry budget expired.")
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError) as error:
            result["error"] = str(error) if not isinstance(error, subprocess.TimeoutExpired) else "Git sync timed out; local learning retained."
            return result


def configured_exchange(store, path):
    """Only explicit local configuration enables network sharing."""
    path = Path(path)
    if not path.exists():
        return None
    if path.stat().st_size > 4096:
        raise ValueError("Sharing configuration is too large.")
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict) or set(config) - {"enabled", "helper", "remote", "branch", "timeout"}:
        raise ValueError("Invalid sharing configuration fields.")
    if config.get("enabled") is False:
        return None
    if config.get("enabled") is not True:
        raise ValueError("Sharing must be explicitly enabled.")
    return GitLearningExchange(store, config.get("remote"), config.get("helper"),
                               branch=config.get("branch", BRANCH), timeout=config.get("timeout", 20))

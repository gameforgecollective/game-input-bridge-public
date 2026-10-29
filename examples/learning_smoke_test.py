"""Exercise real MCP learning tools in temporary storage. Never call input tools."""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LEARNING_TOOLS = {"get_game_learning", "record_game_lesson",
                  "correct_game_lesson", "get_game_lesson_history"}


@asynccontextmanager
async def session_for(server, database):
    parameters = StdioServerParameters(command=sys.executable, args=[str(server)],
        env=dict(os.environ, GAME_INPUT_LEARNING_DB=str(database),
                 GAME_INPUT_LEARNING_SHARE_CONFIG=str(database.parent / "sharing-disabled-for-smoke.json")))
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            assert "Learning System" in initialized.instructions
            yield session


async def call(session, name, arguments, *, expect_error=False):
    assert name in LEARNING_TOOLS, "Smoke test must never send input or inspect the desktop"
    result = await session.call_tool(name, arguments)
    assert bool(result.isError) == expect_error, str(result.content)
    return result.structuredContent


async def smoke(server):
    with tempfile.TemporaryDirectory(prefix="bridge-learning-smoke-") as directory:
        database = Path(directory) / "learning.sqlite3"
        async with session_for(server, database) as session:
            discovered = await session.list_tools()
            assert LEARNING_TOOLS <= {tool.name for tool in discovered.tools}
            empty = await call(session, "get_game_learning", {"game": "Learning Smoke Fixture"})
            assert empty["total_lessons"] == 0 and not database.exists()
            lesson = dict(game="Learning Smoke Fixture", title="Synthetic smoke fixture",
                category="question", status="uncertain", source="user_explanation",
                attempted="Synthetic request, no real game input", expected="Synthetic outcome",
                before="Synthetic initial state", observed="No gameplay performed", evidence=[], context={})
            saved = await call(session, "record_game_lesson", lesson)
            record = saved["record"]
            await call(session, "record_game_lesson", dict(lesson, status="verified"), expect_error=True)
        # Fresh server process, same temporary journal: prove persistence.
        async with session_for(server, database) as session:
            recalled = await call(session, "get_game_learning", {"game": "Learning Smoke Fixture"})
            assert recalled["lessons"][0]["id"] == record["id"]
            failed = await call(session, "correct_game_lesson", dict(record_id=record["id"],
                status="failed", source="bridge_action", observed="Synthetic failed outcome",
                evidence=["synthetic fixture; not live gameplay"], reason="Exercise failure history"))
            corrected = await call(session, "correct_game_lesson", dict(record_id=failed["record"]["id"],
                status="uncertain", source="user_explanation", observed="Synthetic follow-up",
                evidence=[], reason="Exercise retained failure count"))
            await call(session, "correct_game_lesson", dict(record_id=record["id"],
                status="uncertain", source="user_explanation", observed="Stale update",
                evidence=[], reason="Must reject stale correction"), expect_error=True)
            history = await call(session, "get_game_lesson_history", {"lesson_id": record["lesson_id"]})
            assert [row["status"] for row in history["records"]] == ["uncertain", "failed", "uncertain"]
            latest = await call(session, "get_game_learning", {"game": "Learning Smoke Fixture"})
            assert latest["recorded_failures"] == 1
            assert latest["lessons"][0]["id"] == corrected["record"]["id"]
            assert latest["controls_authorized"] is False
            assert not (await call(session, "get_game_learning", {"game": "Other Smoke Game"}))["lessons"]
        print(json.dumps(dict(result="PASS", tools=sorted(LEARNING_TOOLS),
            persistence_across_server_reconnect=True, retained_revisions=3,
            failures_preserved=True, rejected_false_verification=True,
            rejected_stale_correction=True, game_input_calls=0,
            storage="temporary synthetic fixture only"), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, default=Path(__file__).resolve().parents[1] / "game_input_mcp.py")
    asyncio.run(smoke(parser.parse_args().server.resolve()))

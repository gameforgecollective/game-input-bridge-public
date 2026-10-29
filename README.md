# Game Input Bridge

**Bounded controls. Useful feedback. Learning that stays yours.**

Game Input Bridge is a local Windows MCP server for assistants and developers
testing keyboard-and-mouse interaction. Send a short action, inspect the returned
view, and keep a record of what actually worked.

This is a **public testing preview**. It ships with an empty learning journal,
neutral examples and optional sharing turned off.

## What you can try

- **Short, controlled actions:** key taps, movement chords, relative camera input
  and mouse interaction, with holds limited to two seconds.
- **Action-and-view calls:** perform one action or up to three planned steps and
  receive a fresh image for inspection.
- **Local learning:** save controls, routines, failures and open questions with
  evidence references. Corrections retain the original history.
- **Optional private sharing:** exchange lessons between your own installations
  using a separate private Git repository you configure.
- **A portable client:** keep a stdio connection open from JavaScript without
  hard-coded installation paths.

The bridge supplies tools and a journal. Your assistant interprets the view and
records the lesson; the bridge does not independently learn from video or plan
routes. Input delivery alone does not prove that the intended action happened.

## Quick start

You need Windows with an interactive desktop and Python **3.12 recommended**
(3.10 or newer supported by the source). Git is needed to clone this repository
and run the exchange tests. Node.js is optional for the JavaScript client.

Open PowerShell in a new working folder:

```powershell
git clone https://github.com/gameforgecollective/game-input-bridge-public.git
Set-Location game-input-bridge-public
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-mcp.txt
```

Add the server to your MCP client using the structure in
[examples/codex-mcp.example.toml](examples/codex-mcp.example.toml). Replace its
example paths with your checkout's absolute paths and keep your other settings.
The server needs no API key and communicates through local stdio.

Reconnect your MCP client after updating the server.

## Your window, your controls

Start with `inspect_active_window`. Pass the actual foreground title as
`expected_window` for each input call. The bridge checks that title before
sending input; it does not activate another window for you.

Physical scan-code keyboard input is the default for an unrecognized title.
If you need to select a keyboard method or pointer-style interaction, copy
[examples/input-settings.example.json](examples/input-settings.example.json) to
`input-settings.local.json` beside the server and enter your own window title:

```json
{
  "window_title": "Your Foreground Window",
  "input_style": "pointer",
  "keyboard_backend": "sendinput_scancode"
}
```

`input_style` accepts `pointer` or `camera`. The alternative keyboard method is
`pyautogui_virtual_key`. Reconnect after changing this local file. Your bindings
still determine the result, so verify a short action before longer sequences.

### Optional JavaScript client

```javascript
const { connectGameBridge } = await import('./fast_game_client.mjs');
const bridge = await connectGameBridge();
console.log((await bridge.listTools()).tools.map(tool => tool.name));
console.log(await bridge.call('inspect_active_window'));
await bridge.close({ releaseInputs: false });
```

The client resolves the server and `.venv` relative to its own file. You can
override `python` and `serverPath` when calling `connectGameBridge`, or set
`GAME_INPUT_PYTHON`. Use `bridge.step(expectedWindow, args)` or
`bridge.sequence(expectedWindow, steps)` only for already-authorized input.

## Learn from results

Use `get_game_learning` before a session. After observing an outcome, save a
`record_game_lesson` entry with the attempted action, expected result, before
state, observed result and evidence references.

| Status | Meaning |
| --- | --- |
| `observed` | A demonstration was observed. |
| `verified` | The caller checked the result of an authorized bridge action. |
| `failed` | The attempted result failed. |
| `uncertain` | The outcome or explanation still needs checking. |

Use `correct_game_lesson` to append a correction and `get_game_lesson_history` to
read earlier revisions. Failures remain counted after recovery. Evidence
references are stored as text; the journal does not independently verify them.

Journals are saved under `learning_data/`, scoped by the computer's hostname and
excluded from Git. No journal or prelearned content is included in this preview.
You can choose another database with `GAME_INPUT_LEARNING_DB`.

### Optional sharing

Sharing is **disabled by default**. To use it, create your own private Git
repository and follow [the sharing setup guide](docs/private-sharing.md).
No existing private exchange or account is bundled with this project.

Shared entries retain their source computer and status. They appear separately
from local lessons and always require a local check. A result verified elsewhere
does not establish that it works on your computer.

## Testing

The automated suite uses synthetic records, mocked input and temporary local Git
repositories. It does not send controls to your desktop.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe examples\learning_smoke_test.py
node --test test_fast_game_client.mjs
```

The smoke test starts a real stdio server with a temporary journal and real
sharing disabled. It checks discovery, persistence across reconnects, correction
history and rejected invalid updates.

## Testing responsibly

Use the bridge only in a session you are authorized to control. Check the
foreground title and a fresh view before input. Keep the pointer emergency stop
available, reobserve after transitions or uncertain results, and respect the
rules of the software you are testing. The bridge does not bypass access rules,
detect every obstacle or guarantee compatibility with every application.

## Feedback

Found a reproducible issue or have a feature request?
[Open an issue](https://github.com/gameforgecollective/game-input-bridge-public/issues).
Include the expected behavior, observed behavior, Python version and a minimal
example using a neutral window label. Keep credentials, personal journals,
private screenshots and account details out of public reports.

This preview is intended for evaluation and feedback. Updates are planned weekly;
follow the repository for published changes.

# Check controls before longer movement

Use this workflow in a session you are authorized to control. It does not start
testing, watch the desktop, select a backend automatically or grant permission.

## Inspect first

Call `inspect_active_window` and read `control_settings`. It reports the selected
profile, keyboard backend, binding hints and enforced input limits. An absent
foreground title returns null settings. An unknown title retains an unverified
profile; binding hints may be empty.

`runtime_verified:false` means this report is configuration, not a movement test.
It remains false even if a separate journal entry describes a verified outcome.
`controls_authorized:false` means authorization must come from the user. Neither
`input_ready:true` nor a matching title establishes that a world is loaded, a
chat/menu is closed, the desktop is unlocked, or the user has yielded controls.

Read `get_game_learning` for the actual game/window identity. Use
`sync_shared:false` when only cached, read-only review is wanted. Shared lessons
describe results on their origin computers and require a fresh local check.

## Measure one thing at a time

After a fresh user handoff, obtain a current game view. Record the edition or
version, backend, relevant bindings, display size and overlays. Choose a safe,
clear area. Stop immediately if the user takes controls or a dialog appears.

Start with a short move-only action, for example 200–400 milliseconds, without
sprinting or turning. Compare before/after coordinates when available, or clear
avatar/scenery displacement. Test jumping separately. Test camera look separately
against stable landmarks. Observe each result before the next decision; a key
acknowledgement or OS cursor movement alone proves neither walking nor aiming.

If the result is unchanged or obscured, record it as failed or uncertain. Stop
repeating the same attempt until a material condition changes. Do not increase
hold durations to compensate for an unverified control path.

## Compare keyboard methods deliberately

If a reproducible keyboard failure remains, compare the existing
`sendinput_scancode` and `pyautogui_virtual_key` methods under the same conditions.
Use your own ignored `input-settings.local.json` as described in the README;
change one field at a time and reconnect the server safely between trials.
Do not reconnect while any input is held or another assistant owns that PC.
Neither backend is guaranteed to work with every application.

Store the before state, expected result, observed result, evidence reference and
backend in the local learning journal. `verified` requires a caller-checked game
outcome after an authorized action. Append corrections without erasing earlier
failures. Only after separate controls work should you try combined movement,
longer sequences or following another player. The bridge does not provide
automatic obstacle detection or pathfinding.

## Keep fixes and private evidence separate

When maintaining a private installation, reproduce and fix issues there first.
Keep private records, screenshots, account details and development receipts in
that private workspace. Review each reusable change for public inclusion, rather
than copying a working directory or merging private history.

Use synthetic neutral fixtures for public regressions. Run the offline suite and
isolated stdio smoke, inspect staged content and reachable history, and publish
only reviewed generic code and documentation. Leave public journals empty and
sharing disabled. Preserve local settings, client portability, licensing choices
and unrelated user edits. Report code publication separately from any live-game
test result; offline checks do not establish gameplay compatibility.

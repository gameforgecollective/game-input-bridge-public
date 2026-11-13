# Changelog

## 0.1.3-preview

- If a mouse-button hold cannot release its button, `release_all_inputs` can
  retry the release. This also covers presses that report an error after
  partially completing.

## 0.1.2-preview

- Local input settings can select plain relative mouse events for captured cameras;
  existing event delivery remains the default and diagnostics show the selection.
- `control_character` can hold one interaction key while moving or looking, with
  the existing duration bounds, foreground checks and release-on-error behavior.
- Added offline coverage for mode selection, invalid settings and held-key cleanup.
- Compatibility still requires an authorized local test and observed results.

## 0.1.1-preview

- Read-only foreground diagnostics now report the selected keyboard method,
  binding hints and enforced limits before input.
- Diagnostics explicitly separate configuration from runtime verification and
  user authorization, including absent and unrecognized foreground windows.
- Added a measured movement-check workflow and private-first contribution guidance.
- Input defaults and safety limits are unchanged; live compatibility still needs
  local verification.

## 0.1.0-preview

- Bounded foreground-window keyboard and mouse tools.
- Action sequences with returned views for result checking.
- Local learning journals with evidence references and immutable correction history.
- Optional user-configured private sharing with source-PC verification labels.
- Portable JavaScript stdio client and local input settings.
- Synthetic offline tests and isolated reconnect smoke testing.

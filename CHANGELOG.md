# Changelog

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

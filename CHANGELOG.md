# Changelog

## 0.1.0 (not released yet)

First public version.

- Floating window that shows the context usage of Cowork conversations, per conversation and per model, read from Claude Desktop's local cache (read-only, no network code).
- Red mark at the auto-compaction threshold observed on your machine, and an alert (flashing border and a beep) at a chosen share of it.
- Quota gauges for the 5 hour session and the week.
- Table mode (`--once`) and diagnostics mode (`--debug`).
- English interface by default, French as an option (menu or `--lang`).
- Choose which conversations are shown: right-click a row (pin or hide) or use the *Choose conversations* menu. The choice is remembered.
- A `~` before the percentage flags numbers older than the conversation's last activity (the cache is only rewritten when Claude Desktop reloads the conversation).
- Conversations opened from a project (Claude.ai conversation list attached to a Cowork workspace session) are now listed too, and flagged as running.
- Conversations opened from a project have no token counter in the cache: their size is estimated from their text (about 3.5 characters per token, system prompt not counted) and shown with a `≈`. No alert is raised on an estimate.
- Options `--data-dir`, `--framed` and `--version`.
- Compaction threshold learned from Cowork itself and kept between sessions; for a model never seen, the threshold of a model with the same window, else 38 % of the window. Manual choice in the menu.
- Conversations opened from a project have no token counter in the cache: their size is estimated from the transcript since the last compaction divider, calibrated on the real compactions seen on your machine (about 35 % margin, shown as an approximation).
- A compaction divider appearing in a conversation is announced and re-arms the alerts.
- The HUD follows the conversation you are in (latest message, opening or run) and starts in auto mode.
- Two alerts before compaction (alert threshold, then 95 % of the compaction threshold); the percentage shown is the share of that threshold.
- One line per conversation (no duplicates).
- Windows: tested. macOS: experimental, not tested, see TESTS_MACOS.md.

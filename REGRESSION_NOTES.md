# Regression Notes

These are bugs that have already burned us once. Keep the tests with the
behavior, and do not reintroduce the old local fallback behavior.

## QuestLog-Connected Timing

- `Longest Life` is server-authoritative for QuestLog-connected runs.
- Do not merge it with local state using `max(existing, server)`.
- A stale local life cap can show as `12:00:00`; server status such as
  `longest_life_sec=2300` must replace that value and display `00:38:20`.
- Server status with exactly `longest_life_sec=43200` is the known stale
  12-hour cap sentinel from older builds. The app must not accept or resend it
  unless the current live streak is actually at that cap.
- Timer payloads must promote the current live streak into `longest_sec`
  before heartbeat/death posts. Pressing F9 after a long life must send the
  just-ended life as the new `Longest Life`, even though `streak_sec` is reset
  to `0` for the death event.
- Covered by `tests/test_questlog_sync_timing.py`.

## QuestLog-Connected Death Totals

- `Total Deaths`, `This Session`, `Boss Deaths`, `Everything Else`, and
  `Current Boss` must be assigned directly from authoritative API responses.
- `Deaths / HR (Session)` must be blank/`--` when `This Session` is `0`;
  stale rate values must be cleared when session deaths are reset to zero.
- Reopened QuestLog-connected runs must restore `This Session` from the
  server snapshot. Do not let the fresh local `Session()` default of `0`
  override a still-active server session.
- Do not locally record a death before the server death response returns.
- Do not calculate `Boss Deaths` by adding `session_deaths`; session deaths
  are already included in the server totals.

## QuestLog Run Identity

- Never auto-attach a login to the first active QuestLog run. Multiple active
  Reforged runs can exist, so game/mode matching is not enough.
- Login may only restore cloud sync when the currently open local run already
  has the exact same `questlog_token`.
- Startup may delay showing the logged-in UI until profile validation, but it
  must still create the internal API client immediately. Otherwise launching a
  cloud-linked run during validation skips `QuestLogSync`, which means no
  heartbeat, no current streak, no items, and a broken overlay.
- Creating a new QuestLog run must request a fresh server session and must
  refuse any response token that is already the current token, already linked
  to a local run, or already shown in the server active/history lists.

## QuestLog Pause State

- `pause()` and `resume()` must both update local state immediately, then let
  the server confirm or roll back.
- Resuming while the game is still running must restore `_life_start_ts` from
  the banked paused streak. Otherwise Current Streak, Longest Life, death
  payloads, and overlay timers can diverge from the site.

## Live Save Tracking

- The selected character save in Settings/Run Selector wins when launching a
  run; stale local run metadata is only a fallback.
- Live-save item reconciliation must include currently equipped armor and
  talismans, not only acquired inventory rows.

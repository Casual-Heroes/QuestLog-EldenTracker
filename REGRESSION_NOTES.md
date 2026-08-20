# Regression Notes

These are bugs that have already burned us once. Keep the tests with the
behavior, and do not reintroduce the old local fallback behavior.

## QuestLog-Connected Timing

- `Longest Life` is server-authoritative for QuestLog-connected runs.
- Do not merge it with local state using `max(existing, server)`.
- A stale local life cap can show as `12:00:00`; server status such as
  `longest_life_sec=2300` must replace that value and display `00:38:20`.
- Covered by `tests/test_questlog_sync_timing.py`.

## QuestLog-Connected Death Totals

- `Total Deaths`, `This Session`, `Boss Deaths`, `Everything Else`, and
  `Current Boss` must be assigned directly from authoritative API responses.
- Do not locally record a death before the server death response returns.
- Do not calculate `Boss Deaths` by adding `session_deaths`; session deaths
  are already included in the server totals.

## Live Save Tracking

- The selected character save in Settings/Run Selector wins when launching a
  run; stale local run metadata is only a fallback.
- Live-save item reconciliation must include currently equipped armor and
  talismans, not only acquired inventory rows.

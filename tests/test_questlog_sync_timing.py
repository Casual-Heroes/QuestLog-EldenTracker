from core.questlog_sync import QuestLogSync


def test_connected_status_replaces_stale_longest_life_cap():
    sync = QuestLogSync("token", api_key="key")
    sync._longest_life = 12 * 60 * 60

    sync._apply_death_count_status({
        "total_deaths": 10,
        "session_deaths": 1,
        "longest_life_sec": 38 * 60 + 20,
    })

    assert sync.longest_life_sec() == 38 * 60 + 20


def test_timer_payload_promotes_current_life_to_longest_before_death(monkeypatch):
    sync = QuestLogSync("token", api_key="key")
    sync._longest_life = 93
    sync._game_active = True
    sync._life_start_ts = 1_000.0

    monkeypatch.setattr("core.questlog_sync.time.time", lambda: 1_000.0 + (2 * 60 * 60))

    payload = sync._timer_payload(game_running=True, streak_override=0)

    assert payload["streak_sec"] == 0
    assert payload["longest_sec"] == 2 * 60 * 60
    assert sync.longest_life_sec() == 2 * 60 * 60


def test_session_deaths_zero_clears_session_deaths_per_hour():
    sync = QuestLogSync("token", api_key="key")
    sync._session_deaths_per_hour = 360.0

    sync._apply_death_count_status({
        "total_deaths": 4,
        "session_deaths": 0,
        "session_deaths_per_hour": 360.0,
    })

    session_dph, _run_dph = sync.get_deaths_per_hour()
    assert session_dph is None


def test_connected_session_deaths_restored_from_status_snapshot():
    sync = QuestLogSync("token", api_key="key")

    sync._apply_death_count_status({
        "total_deaths": 4,
        "session_deaths": 1,
        "boss_deaths_total": 3,
        "non_boss_deaths_total": 1,
    })

    assert sync.has_status_snapshot()
    assert sync.session_deaths() == 1

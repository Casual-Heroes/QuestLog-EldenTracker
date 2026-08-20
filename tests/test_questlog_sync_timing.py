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

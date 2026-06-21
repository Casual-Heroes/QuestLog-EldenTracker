import time
from collections import deque
from core.bosses import (
    TIER_ENEMY, TIER_GREAT_ENEMY, TIER_LEGEND, TIER_DEMIGOD, TIER_GOD
)

ROLLING_WINDOW_SECS = 1800  # 30 minutes
TIME_DECAY_DELAY    = 90    # seconds after last death before time decay kicks in
TIME_DECAY_RATE     = 25 / 60  # 25% per minute

TIER_DECAY = {
    TIER_ENEMY:       25,
    TIER_GREAT_ENEMY: 50,
    TIER_LEGEND:      100,
    TIER_DEMIGOD:     125,
    TIER_GOD:         999,
}

RAGE_STATES = [
    (0,   "Maiden's Grace", "#C9A84C"),
    (25,  "Staggered",      "#E07B00"),
    (50,  "Frenzied",       "#C0390F"),
    (75,  "Cursed",         "#8B0000"),
    (100, "HOLLOW",         "#FF0000"),
]


class DeathTracker:
    def __init__(self, session):
        self.session = session
        self._death_times    = deque()
        self._consecutive    = 0
        self._last_death_time = None
        self._rage_pct       = 0.0
        self._hollow_streak  = 0

    def record_death(self):
        now = time.time()
        self._death_times.append(now)
        self._last_death_time = now
        self.session.record_death()

        if self._rage_pct >= 100:
            self._hollow_streak += 1
        else:
            self._consecutive += 1
            self._rage_pct = min(100.0, self._consecutive * 25)
            if self._rage_pct >= 100:
                self._hollow_streak = 0

    def record_kill(self, tier=TIER_ENEMY):
        decay = TIER_DECAY.get(tier, 25)

        if tier == TIER_GOD:
            self._rage_pct      = 0.0
            self._consecutive   = 0
            self._hollow_streak = 0
            return

        if self._hollow_streak > 0:
            steps = max(1, decay // 25)
            self._hollow_streak = max(0, self._hollow_streak - steps)
            if self._hollow_streak == 0:
                self._rage_pct    = max(0.0, 75.0 - max(0, decay - 100))
                self._consecutive = int(self._rage_pct / 25)
        else:
            self._rage_pct    = max(0.0, self._rage_pct - decay)
            self._consecutive = int(self._rage_pct / 25)

    def reset(self):
        self._death_times.clear()
        self._consecutive     = 0
        self._last_death_time = None
        self._rage_pct        = 0.0
        self._hollow_streak   = 0

    def _prune_window(self):
        cutoff = time.time() - ROLLING_WINDOW_SECS
        while self._death_times and self._death_times[0] < cutoff:
            self._death_times.popleft()

    def deaths_per_hour(self):
        self._prune_window()
        count = len(self._death_times)
        if count == 0:
            return 0.0
        window_secs = min(self.session.elapsed_seconds(), ROLLING_WINDOW_SECS)
        if window_secs < 1:
            return 0.0
        return round(count / window_secs * 3600, 1)

    def update_rage_decay(self):
        if self._rage_pct <= 0 or self._hollow_streak > 0:
            return
        if not self._last_death_time:
            return
        if time.time() - self._last_death_time >= TIME_DECAY_DELAY:
            self._rage_pct    = max(0.0, self._rage_pct - TIME_DECAY_RATE)
            self._consecutive = int(self._rage_pct / 25)

    def rage_state(self):
        pct = int(self._rage_pct)
        for threshold, name, color in reversed(RAGE_STATES):
            if pct >= threshold:
                return pct, name, color
        return 0, "Maiden's Grace", "#C9A84C"

    def hollow_streak(self):
        return self._hollow_streak

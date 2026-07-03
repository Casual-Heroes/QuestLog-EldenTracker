import time
import json
import os
import psutil

STOP_GRACE_SECS = 10


class Session:
    def __init__(self, process_name, run_dir):
        self._process_name = process_name.lower().replace(".exe", "")
        self._state_file   = os.path.join(run_dir, "session.json")
        self.active        = False
        self.start_time    = time.time()   # always count from run launch, not game detection
        self.end_time      = None
        self.session_deaths = 0
        self.total_deaths  = self._load_total_deaths()
        self._missing_since = None

    def _load_total_deaths(self):
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file) as f:
                    return json.load(f).get("total_deaths", 0)
            except Exception:
                pass
        return 0

    def save(self):
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        with open(self._state_file, "w") as f:
            json.dump({"total_deaths": self.total_deaths}, f)

    def record_death(self):
        self.session_deaths += 1
        self.total_deaths   += 1
        self.save()

    def reset_total_deaths(self):
        self.total_deaths   = 0
        self.session_deaths = 0
        self.save()

    def reset_session_time(self):
        self.start_time = time.time()
        self.end_time   = None

    def stop(self):
        self.active         = False
        self.end_time       = time.time()
        self._missing_since = None
        self.save()

    def elapsed_seconds(self):
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time

    def elapsed_str(self):
        secs = int(self.elapsed_seconds())
        h, rem = divmod(secs, 3600)
        m, s   = divmod(rem, 60)
        return f"{h:02}:{m:02}:{s:02}"

    def is_game_running(self):
        for p in psutil.process_iter(["name"]):
            name = p.info["name"] or ""
            if name.lower().replace(".exe", "") == self._process_name:
                return True
        return False

    def poll(self):
        try:
            running = self.is_game_running()
        except Exception:
            return False

        if running:
            self._missing_since = None
            if not self.active:
                self.active         = True
                self.start_time     = time.time()
                self.session_deaths = 0
                self.save()
                return True
            return False
        else:
            if self.active:
                if self._missing_since is None:
                    self._missing_since = time.time()
                elif time.time() - self._missing_since >= STOP_GRACE_SECS:
                    self.stop()
                    return True
            return False

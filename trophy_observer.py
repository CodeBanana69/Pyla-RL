import os
import time
from datetime import datetime

import requests
from utils import load_toml_as_dict, save_dict_as_toml, api_base_url

TROPHY_LOG_DIR = "logs"
TROPHY_LOG_FILE = "trophies.log"
TROPHY_LOG_MAX_LINES = 1000
MILESTONE_STEP = 100
class TrophyObserver:

    def __init__(self, brawler_list):
        self.history_file = "./cfg/match_history.toml"
        self.current_trophies = None
        self.current_wins = None
        self.match_history = self.load_history(brawler_list)
        self.match_history['total'] = {"defeat": 0, "victory": 0, "draw": 0}
        self.sent_match_history = {brawler: {"defeat": self.match_history[brawler]["defeat"],
                                             "victory": self.match_history[brawler]["victory"],
                                             "draw": self.match_history[brawler]["draw"]}
                                   for brawler in brawler_list}
        self.win_streak = 0
        self.match_counter = 0  # New counter for the number of matches
        self.trophy_lose_ranges = [(49, 0), (299, 1), (599, 2), (799, 3), (999, 4), (1099, 5), (1199, 6), (1299, 7),
                                   (1499, 8), (1799, 9), (3999, 10), (float("inf"), 15)]
        self.trophy_win_ranges = [(1999, 10), (2499, 8), (2799, 6), (2999, 4), (3099, 2), (float("inf"), 1)]

        # Showdown trio: per-place trophy delta by trophy-range upper bound.
        # Columns: 1st, 2nd, 3rd, 4th
        # Source: official showdown trio trophy table.
        # Last row is a fallback for trophies above the documented range.
        self.showdown_trio_ranges = [
            (49,    (11, 5, 5, 5)),
            (99,    (11, 5, 4, -1)),
            (199,   (11, 5, 3, -1)),
            (299,   (11, 5, 2, -1)),
            (499,   (11, 5, 2, -2)),
            (599,   (11, 5, 1, -2)),
            (799,   (11, 5, 1, -3)),
            (999,   (11, 5, 1, -4)),
            (1099,  (11, 5, 0, -6)),
            (1199,  (11, 5, 0, -7)),
            (1299,  (11, 5, 0, -8)),
            (1499,  (11, 5, 0, -9)),
            (1799,  (11, 5, -5, -10)),
            (1999,  (11, 5, -5, -11)),
            (2199,  (9,  4, -5, -11)),
            (float("inf"), (9, 4, -5, -11)),
        ]
        self.crop_region = load_toml_as_dict("./cfg/lobby_config.toml")['lobby']['trophy_observer']
        self.trophies_multiplier = int(load_toml_as_dict("./cfg/general_config.toml")["trophies_multiplier"])

        # Per-brawler milestone tracking for the trophies log.
        #   _milestone_anchor_trophies[brawler] = trophies value that the
        #     current summary stretch is measured FROM. On first match of a
        #     session it's the brawler's actual starting trophies. After a
        #     milestone is crossed upward it becomes that milestone. After a
        #     downward move it becomes the lowest trophies seen in this
        #     stretch.
        #   _milestone_anchor_time[brawler] = monotonic timestamp matching
        #     when anchor_trophies was last observed. Resets together with
        #     anchor_trophies.
        self._milestone_anchor_trophies = {}
        self._milestone_anchor_time = {}
        os.makedirs(TROPHY_LOG_DIR, exist_ok=True)
        self._trophy_log_path = os.path.join(TROPHY_LOG_DIR, TROPHY_LOG_FILE)

    def win_streak_gain(self):
        return max(0, min(self.win_streak - 1, 10)) if self.current_trophies < 2000 else 0

    def apply_trophy_floor(self, old_trophies):
        """Once a brawler has reached 1000 trophies, they can't drop below it."""
        if old_trophies >= 1000 and self.current_trophies < 1000:
            self.current_trophies = 1000

    def calc_lost_decrement(self):
        for max_trophies, loss in self.trophy_lose_ranges:
            if float(self.current_trophies) <= float(max_trophies):
                return loss

    def calc_win_increment(self):
        for max_trophies, gain in self.trophy_win_ranges:
            if float(self.current_trophies) <= float(max_trophies):
                return gain*self.trophies_multiplier + self.win_streak_gain()

    def calc_showdown_delta(self, place_index):
        """Return trophy delta for showdown trio based on finishing place.

        place_index is 0-based: 0 = 1st, 1 = 2nd, 2 = 3rd, 3 = 4th.
        """
        for max_trophies, deltas in self.showdown_trio_ranges:
            if float(self.current_trophies) <= float(max_trophies):
                return deltas[place_index] * self.trophies_multiplier
        return 0

    def load_history(self, brawler_list):
        if os.path.exists(self.history_file):
            loaded_data = load_toml_as_dict(self.history_file)
        else:
            loaded_data = {}

        # Ensure each brawler has an entry
        for brawler in brawler_list:
            if brawler not in loaded_data:
                loaded_data[brawler] = {"defeat": 0, "victory": 0, "draw": 0}

        if "total" not in loaded_data:
            loaded_data["total"] = {"defeat": 0, "victory": 0, "draw": 0}

        return loaded_data

    def save_history(self):
        save_dict_as_toml(self.match_history, self.history_file)

    def _write_trophy_log(self, line):
        try:
            with open(self._trophy_log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._trim_trophy_log()
        except OSError as e:
            print(f"Failed to write trophy log: {e}")

    def _trim_trophy_log(self):
        try:
            with open(self._trophy_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) <= TROPHY_LOG_MAX_LINES:
                return
            with open(self._trophy_log_path, "w", encoding="utf-8") as f:
                f.writelines(lines[-TROPHY_LOG_MAX_LINES:])
        except OSError as e:
            print(f"Failed to trim trophy log: {e}")

    @staticmethod
    def _format_duration(seconds):
        seconds = int(seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m}m {s}s"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    def _log_match(self, brawler, game_result, old, new):
        delta = new - old
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._write_trophy_log(
            f"[{ts}] brawler={brawler} result={game_result} {old} -> {new} ({delta:+d})"
        )

    def _update_milestones(self, brawler, old, new):
        """Track every MILESTONE_STEP-trophy boundary the brawler crosses.

        Each milestone is summarized exactly once per session — the first
        time it's reached. After that the anchor is frozen at (milestone,
        crossing_time) and never rewinds on dips below it. The next summary
        (for the next milestone) is therefore measured from that original
        crossing, regardless of intermediate drops.
        """
        now = time.monotonic()
        step = MILESTONE_STEP

        if brawler not in self._milestone_anchor_time:
            self._milestone_anchor_trophies[brawler] = old
            self._milestone_anchor_time[brawler] = now

        anchor_trophies = self._milestone_anchor_trophies[brawler]

        # Upward: emit a summary for every milestone strictly above the anchor
        # that `new` has reached. The first one uses the actual anchor value
        # (e.g. 777 -> 800); subsequent ones use the previous milestone.
        next_milestone = ((anchor_trophies // step) + 1) * step
        while new >= next_milestone:
            elapsed = now - self._milestone_anchor_time[brawler]
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._write_trophy_log(
                f"[{ts}] SUMMARY brawler={brawler} {anchor_trophies} -> {next_milestone} "
                f"time={self._format_duration(elapsed)}"
            )
            anchor_trophies = next_milestone
            self._milestone_anchor_trophies[brawler] = anchor_trophies
            self._milestone_anchor_time[brawler] = now
            next_milestone += step

    # Map showdown places to match_history victory/defeat buckets so the
    # existing history/API reporting keeps working unchanged.
    _showdown_place_index = {"1st": 0, "2nd": 1, "3rd": 2, "4th": 3}
    _showdown_place_to_bucket = {"1st": "victory", "2nd": "victory", "3rd": "draw", "4th": "defeat"}

    def add_trophies(self, game_result, current_brawler):
        if current_brawler not in self.sent_match_history:
            self.sent_match_history[current_brawler] = {"defeat": 0, "victory": 0, "draw": 0}
        if current_brawler not in self.match_history:
            self.match_history[current_brawler] = {"defeat": 0, "victory": 0, "draw": 0}

        print(f"Found game result!: {game_result} win streak: {self.win_streak}")
        old = self.current_trophies
        bucket = None

        if game_result in self._showdown_place_index:
            # Showdown trio: place-based trophy delta.
            # Win streak rules for local trophy estimates:
            #   1st, 2nd → streak grows, streak bonus applied
            #   3rd keeps streak as tie, 4th resets it; neither gets streak bonus
            place_index = self._showdown_place_index[game_result]
            delta = self.calc_showdown_delta(place_index)

            # Update streak first so win_streak_gain() reflects this match.
            # 1st/2nd grow it; every other showdown placement resets it.
            if game_result in ("1st", "2nd"):
                self.win_streak += 1
            elif game_result == "4th":
                self.win_streak = 0

            streak_bonus = self.win_streak_gain() if game_result in ("1st", "2nd") else 0
            delta_with_bonus = delta + streak_bonus

            self.current_trophies += delta_with_bonus
            bucket = self._showdown_place_to_bucket[game_result]
            if streak_bonus:
                print(f"Showdown place: {game_result} -> delta {delta:+d} (+{streak_bonus} streak bonus)")
            else:
                print(f"Showdown place: {game_result} -> delta {delta:+d}")
        elif game_result == "victory":
            self.win_streak += 1
            self.current_trophies += self.calc_win_increment()
            bucket = "victory"
        elif game_result == "defeat":
            self.win_streak = 0
            self.current_trophies -= self.calc_lost_decrement()
            bucket = "defeat"
        elif game_result == "draw":
            print("Nothing changed. Draw detected")
            bucket = "draw"
        else:
            print("Catastrophic failure")
            return False

        self.apply_trophy_floor(old)
        print(f"Trophies : {old} -> {self.current_trophies}")
        print("Current wins:", self.current_wins)
        self._log_match(current_brawler, game_result, old, self.current_trophies)
        self._update_milestones(current_brawler, old, self.current_trophies)
        self.match_history[current_brawler][bucket] += 1
        self.match_history["total"][bucket] += 1

        self.match_counter += 1  # Increment the match counter
        if self.match_counter % 4 == 0:  # If every 4th match
            self.send_results_to_api()  # Send results to the API

        self.save_history()
        return True

    def add_win(self, game_result):
        # Treat victory (non-showdown) and 1st/2nd places (showdown) as wins
        if game_result == "victory" or game_result in ("1st", "2nd"):
            self.current_wins += 1



    def change_trophies(self, new):
        print(f"Trophies changed from {self.current_trophies} to {new}")
        self.current_trophies = new

    def send_results_to_api(self):
        # Prepare the data by calculating the difference between current and sent stats
        data = {}
        for brawler, stats in self.match_history.items():
            if brawler != "total":
                if brawler not in self.sent_match_history:
                    self.sent_match_history[brawler] = {"defeat": 0, "victory": 0, "draw": 0}
                new_stats = {
                    "wins": stats["victory"] - self.sent_match_history[brawler]["victory"],
                    "defeats": stats["defeat"] - self.sent_match_history[brawler]["defeat"],
                    "draws": stats["draw"] - self.sent_match_history[brawler]["draw"],
                }
                if any(new_stats.values()):  # Only include if there are new results
                    data[brawler] = new_stats

        if not data:  # No new data to send
            return

        if api_base_url != "localhost":
            # Send the POST request
            try:
                response = requests.post(f'https://{api_base_url}/api/brawlers', json=data)
                if response.status_code == 200:
                    print("Results successfully sent to API")
                    # Update sent_match_history with the latest totals
                    for brawler, stats in self.match_history.items():
                        if brawler != "total":
                            self.sent_match_history[brawler]["victory"] = stats["victory"]
                            self.sent_match_history[brawler]["defeat"] = stats["defeat"]
                            self.sent_match_history[brawler]["draw"] = stats["draw"]
                else:
                    print(f"Failed to send results to API. Status code: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Error sending results to API: {e}")

import os
import requests
from utils import load_toml_as_dict, api_base_url, hash_playstyle, PYLA_VERSION, resolve_project_path
import pandas as pd
from datetime import datetime

class TrophyObserver:

    def __init__(self):
        self.history_file = resolve_project_path("cfg/match_history.csv")
        self.current_trophies = None
        self.current_wins = None
        self.session_wins = 0
        self.session_losses = 0
        self.session_draws = 0
        self.match_history = self.load_history()
        self.last_sent_index = len(self.match_history)
        self.win_streak = 0
        self.match_counter = 0  # New counter for the number of matches
        self.last_match_record = None
        self.trophy_lose_ranges = [(49, 0), (299, 1), (599, 2), (799, 3), (999, 4), (1099, 5), (1199, 6), (1299, 7),
                                   (1499, 8), (1799, 9), (3999, 10), (float("inf"), 15)]
        self.trophy_win_ranges = [(1999, 10), (2499, 8), (2799, 6), (2999, 4), (3099, 2), (float("inf"), 1)]
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
        self.trophies_multiplier = int(load_toml_as_dict("cfg/general_config.toml")["trophies_multiplier"])

    def win_streak_gain(self):
        return min(self.win_streak - 1, 10) if self.current_trophies < 2000 else 0

    def calc_lost_decrement(self):
        for max_trophies, loss in self.trophy_lose_ranges:
            if float(self.current_trophies) <= float(max_trophies):
                return loss
        raise ValueError("Current trophies exceed all defined ranges")

    def calc_win_increment(self):
        for max_trophies, gain in self.trophy_win_ranges:
            if float(self.current_trophies) <= float(max_trophies):
                return gain*self.trophies_multiplier + self.win_streak_gain()
        raise ValueError("Current trophies exceed all defined ranges")

    def calc_showdown_delta(self, place):
        for max_trophies, deltas in self.showdown_trio_ranges:
            if float(self.current_trophies) <= float(max_trophies):
                return deltas[place] * self.trophies_multiplier + (self.win_streak_gain() if place < 2 else 0)
        raise ValueError("Current trophies exceed all defined ranges")

    def load_history(self):
        if os.path.exists(self.history_file):
            history = pd.read_csv(self.history_file)
        else:
            history = pd.DataFrame(
                columns=["date_time", "brawler_name", "result", "current_trophies", "trophy_delta", "new_winstreak",
                         "playstyle_hash", "playstyle_name", "playstyle_gamemodes", "playstyle_brawlers",
                         "pyla_version", "power_level"])
        return history

    def save_history(self):
        history_dir = os.path.dirname(self.history_file)
        if history_dir:
            os.makedirs(history_dir, exist_ok=True)
        self.match_history.to_csv(self.history_file, index=False)

    @staticmethod
    def _display_result(game_result):
        raw = str(game_result or "").strip().lower()
        if "showdown" in raw:
            try:
                place = int(raw.split("_")[-1])
            except (TypeError, ValueError):
                return raw
            return {0: "1st", 1: "2nd", 2: "3rd", 3: "4th"}.get(place, raw)
        return raw

    def add_trophies(self, game_result, current_brawler, playstyle_info, power_level=None):
        print(f"Found game result!: {game_result} win streak: {self.win_streak}")
        old = self.current_trophies
        display_result = self._display_result(game_result)
        if game_result == "victory":
            self.win_streak += 1
            trophy_delta = self.calc_win_increment()
        elif game_result == "defeat":
            self.win_streak = 0
            trophy_delta = -self.calc_lost_decrement()
        elif game_result == "draw":
            print("Nothing changed. Draw detected")
            trophy_delta = 0
        elif "showdown" in game_result:
            place = int(game_result.split("_")[-1])
            if place < 2:
                game_result = "victory"
                self.win_streak += 1
            elif place == 2:
                game_result = "draw"
            else:
                game_result = "defeat"
                self.win_streak = 0
            trophy_delta = self.calc_showdown_delta(place)
        else:
            print("Catastrophic failure")
            trophy_delta = 0
        self._record_session_result(game_result)
        self.current_trophies += trophy_delta
        self.last_match_record = {
            "brawler": current_brawler,
            "result": display_result,
            "started_trophies": old,
            "trophy_delta": trophy_delta,
            "trophies": self.current_trophies,
            "win_streak": self.win_streak,
        }

        print(f"Trophies : {old} -> {self.current_trophies}")
        print("Current wins:", self.current_wins)
        self.match_history.loc[len(self.match_history)] = [datetime.now().isoformat(), current_brawler, game_result, old, trophy_delta, self.win_streak, hash_playstyle(playstyle_info), playstyle_info["name"], "|".join(playstyle_info["gamemodes"]), "|".join(playstyle_info["brawlers"]), PYLA_VERSION, (power_level if power_level is not None else -1)]
        self.match_counter += 1
        self.send_results_to_api()


        self.save_history()

    def add_win(self, game_result):
        if game_result == "victory":
            self.current_wins += 1

    def _record_session_result(self, game_result: str) -> None:
        result = str(game_result or "").strip().lower()
        if result == "victory":
            self.session_wins += 1
        elif result == "defeat":
            self.session_losses += 1
        elif result == "draw":
            self.session_draws += 1

    def session_stats(self) -> dict[str, int]:
        return {
            "session_wins": int(self.session_wins or 0),
            "session_losses": int(self.session_losses or 0),
            "session_draws": int(self.session_draws or 0),
        }

    def change_trophies(self, new):
        print(f"Trophies changed from {self.current_trophies} to {new}")
        self.current_trophies = new

    def send_results_to_api(self):
        new_matches = self.match_history.iloc[self.last_sent_index:]
        if new_matches.empty:
            return
        payload = new_matches.to_dict(orient="records")
        if api_base_url != "localhost":
            try:
                response = requests.post(f'https://{api_base_url}/api/matches', json=payload)
                if response.status_code == 200:
                    print("Match history successfully sent to API")
                    self.last_sent_index = len(self.match_history)
                else:
                    print(f"Failed to send match history to API. Status code: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Error sending match history to API: {e}")

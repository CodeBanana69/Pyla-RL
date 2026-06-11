import unittest
from unittest.mock import MagicMock, patch

from utils import build_notification_details, notify_user


class NotifyUserTests(unittest.TestCase):
    def test_build_notification_details_returns_dict(self):
        manager = MagicMock()
        manager.brawlers_pick_data = [
            {"brawler": "angelo", "type": "trophies", "push_until": 1000},
            {"brawler": "shelly", "type": "trophies", "push_until": 500},
        ]
        manager.Trophy_observer = MagicMock(
            current_trophies=250,
            current_wins=0,
            win_streak=2,
        )

        details = build_notification_details("regular_matches_ping", manager)

        self.assertIsInstance(details, dict)
        self.assertEqual(details["brawler"], "angelo")
        self.assertEqual(details["trophies"], 250)
        self.assertIn("Pyla is still running", details["message"])

    @patch("utils.async_notify_user", new_callable=MagicMock)
    @patch("asyncio.run")
    def test_notify_user_forwards_details_dict(self, mock_run, mock_async):
        manager = MagicMock()
        manager.brawlers_pick_data = [{"brawler": "angelo", "type": "trophies", "push_until": 1000}]
        manager.Trophy_observer = MagicMock(current_trophies=100, current_wins=0, win_streak=0)

        notify_user("regular_matches_ping", None, manager)

        mock_async.assert_called_once_with(
            "regular_matches_ping",
            None,
            details={
                "message": "Pyla is still running.",
                "brawler": "angelo",
                "target": 1000,
                "brawlers_left": 1,
                "trophies": 100,
                "wins": 0,
                "win_streak": 0,
            },
        )
        mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()

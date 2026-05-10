import unittest

from main import normalize_detected_state, should_accept_lobby_after_match


class StateTransitionGuardTests(unittest.TestCase):
    def test_out_of_match_rewards_are_ignored_until_result_or_lobby_was_seen(self):
        for state in ("prestige_reward", "trophy_reward", "reward_unlock"):
            with self.subTest(state=state):
                self.assertEqual(
                    normalize_detected_state(
                        state,
                        previous_state="match",
                        lobby_seen_since_match=False,
                        match_result_seen=False,
                    ),
                    "match",
                )

    def test_reward_unlock_is_allowed_after_trophy_reward(self):
        self.assertEqual(
            normalize_detected_state(
                "reward_unlock",
                previous_state="trophy_reward",
            ),
            "reward_unlock",
        )
        self.assertEqual(
            normalize_detected_state(
                "reward_unlock",
                previous_state="reward_unlock",
            ),
            "reward_unlock",
        )

    def test_out_of_match_rewards_are_allowed_after_result_screen(self):
        for state in ("prestige_reward", "trophy_reward"):
            with self.subTest(state=state):
                self.assertEqual(
                    normalize_detected_state(
                        state,
                        previous_state="end_3rd",
                        lobby_seen_since_match=False,
                        match_result_seen=True,
                    ),
                    state,
                )

    def test_out_of_match_rewards_are_allowed_after_lobby_was_seen(self):
        for state in ("prestige_reward", "trophy_reward"):
            with self.subTest(state=state):
                self.assertEqual(
                    normalize_detected_state(
                        state,
                        previous_state="lobby",
                        lobby_seen_since_match=True,
                    ),
                    state,
                )

    def test_out_of_match_rewards_are_blocked_after_lobby_start_press_without_result(self):
        for state in ("prestige_reward", "trophy_reward"):
            with self.subTest(state=state):
                self.assertEqual(
                    normalize_detected_state(
                        state,
                        previous_state="lobby",
                        lobby_seen_since_match=True,
                        match_launch_pending=True,
                        match_result_seen=False,
                    ),
                    "match",
                )

    def test_out_of_match_rewards_are_allowed_after_result_even_if_launch_pending(self):
        for state in ("prestige_reward", "trophy_reward"):
            with self.subTest(state=state):
                self.assertEqual(
                    normalize_detected_state(
                        state,
                        previous_state="end_3rd",
                        lobby_seen_since_match=False,
                        match_launch_pending=True,
                        match_result_seen=True,
                    ),
                    state,
                )

    def test_other_states_pass_through(self):
        self.assertEqual(
            normalize_detected_state(
                "lobby",
                previous_state="match",
                lobby_seen_since_match=False,
            ),
            "lobby",
        )

    def test_star_drop_is_blocked_unless_previous_state_was_post_match_reward_chain(self):
        for previous_state in ("match", "match_making", "shop", "lobby", None):
            with self.subTest(previous_state=previous_state):
                self.assertNotEqual(
                    normalize_detected_state(
                        "star_drop",
                        previous_state=previous_state,
                    ),
                    "star_drop",
                )

    def test_star_drop_is_allowed_only_from_post_match_reward_chain(self):
        for previous_state in ("end_1st", "end_2nd", "end_3rd", "end_4th", "trophy_reward", "reward_unlock", "star_drop", "nova_star_drop"):
            with self.subTest(previous_state=previous_state):
                self.assertEqual(
                    normalize_detected_state(
                        "star_drop",
                        previous_state=previous_state,
                    ),
                    "star_drop",
                )

    def test_star_drop_is_blocked_after_lobby_start_pressed(self):
        self.assertEqual(
            normalize_detected_state(
                "star_drop",
                previous_state="end_1st",
                match_launch_pending=True,
            ),
            "end_1st",
        )

    def test_daily_star_drop_is_blocked_in_match_without_post_match_result(self):
        self.assertEqual(
            normalize_detected_state(
                "daily_star_drop",
                previous_state="match",
                match_result_seen=False,
            ),
            "match",
        )
        self.assertEqual(
            normalize_detected_state(
                "daily_star_drop",
                previous_state="match",
                match_launch_pending=True,
            ),
            "match",
        )

    def test_daily_star_drop_is_allowed_after_post_match_result(self):
        self.assertEqual(
            normalize_detected_state(
                "daily_star_drop",
                previous_state="end_1st",
                match_result_seen=True,
            ),
            "daily_star_drop",
        )

    def test_nova_star_drop_is_allowed_after_post_match_result(self):
        self.assertEqual(
            normalize_detected_state(
                "nova_star_drop",
                previous_state="end_1st",
                match_result_seen=True,
            ),
            "nova_star_drop",
        )
        self.assertEqual(
            normalize_detected_state(
                "nova_star_drop",
                previous_state="star_drop",
            ),
            "nova_star_drop",
        )
        self.assertEqual(
            normalize_detected_state(
                "daily_star_drop",
                previous_state="match",
                match_result_seen=True,
            ),
            "daily_star_drop",
        )

    def test_lobby_after_match_depends_on_stable_lobby_state_not_vision_quietness(self):
        self.assertFalse(should_accept_lobby_after_match(2.9, 3.0))
        self.assertTrue(should_accept_lobby_after_match(3.0, 3.0))
        self.assertTrue(should_accept_lobby_after_match(126.9, 3.0))


if __name__ == "__main__":
    unittest.main()

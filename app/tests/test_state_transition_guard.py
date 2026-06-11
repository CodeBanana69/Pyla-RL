import unittest

from main import (
    apply_in_match_overlay_guard,
    normalize_detected_state,
    should_accept_lobby_after_match,
)


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

    def test_out_of_match_rewards_are_blocked_from_match_even_inside_reward_window(self):
        for state in ("prestige_reward", "trophy_reward"):
            with self.subTest(state=state):
                self.assertEqual(
                    normalize_detected_state(
                        state,
                        previous_state="match",
                        match_result_seen=True,
                    ),
                    "match",
                )

    def test_out_of_match_rewards_are_allowed_from_match_after_recent_trophy_change(self):
        self.assertEqual(
            normalize_detected_state(
                "trophy_reward",
                previous_state="match",
                recent_trophy_change=True,
            ),
            "trophy_reward",
        )
        self.assertEqual(
            normalize_detected_state(
                "prestige_reward",
                previous_state="match",
                recent_trophy_change=True,
                prestige_reward_allowed=True,
            ),
            "prestige_reward",
        )
        self.assertEqual(
            normalize_detected_state(
                "prestige_reward",
                previous_state="match",
                recent_trophy_change=True,
                prestige_reward_allowed=False,
            ),
            "match",
        )

    def test_prestige_reward_does_not_rearm_after_falling_back_to_match(self):
        self.assertEqual(
            normalize_detected_state(
                "prestige_reward",
                previous_state="match",
                lobby_seen_since_match=False,
                match_result_seen=True,
            ),
            "match",
        )

    def test_prestige_reward_requires_recent_allowed_result_context(self):
        self.assertEqual(
            normalize_detected_state(
                "prestige_reward",
                previous_state="end_1st",
                match_result_seen=True,
                trophy_result_recorded=True,
                prestige_reward_allowed=False,
            ),
            "end_1st",
        )
        self.assertEqual(
            normalize_detected_state(
                "prestige_reward",
                previous_state="end_1st",
                match_result_seen=True,
                trophy_result_recorded=True,
                prestige_reward_allowed=True,
            ),
            "prestige_reward",
        )

    def test_rewards_are_allowed_from_match_after_trophies_were_recorded(self):
        for state in ("prestige_reward", "trophy_reward", "star_drop", "daily_star_drop", "nova_star_drop"):
            with self.subTest(state=state):
                self.assertEqual(
                    normalize_detected_state(
                        state,
                        previous_state="match",
                        match_result_seen=True,
                        trophy_result_recorded=True,
                    ),
                    state,
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

    def test_matchmaking_is_only_allowed_after_lobby_or_start_press(self):
        self.assertEqual(
            normalize_detected_state(
                "match_making",
                previous_state="match",
                match_launch_pending=False,
            ),
            "match",
        )
        self.assertEqual(
            normalize_detected_state(
                "match_making",
                previous_state=None,
                match_launch_pending=False,
            ),
            "match",
        )
        self.assertEqual(
            normalize_detected_state(
                "match_making",
                previous_state="lobby",
                match_launch_pending=False,
            ),
            "match_making",
        )
        self.assertEqual(
            normalize_detected_state(
                "match_making",
                previous_state="match",
                match_launch_pending=True,
            ),
            "match_making",
        )
        self.assertEqual(
            normalize_detected_state(
                "match_making",
                previous_state="match_making",
                match_launch_pending=True,
            ),
            "match_making",
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
            "match",
        )

    def test_exact_star_drop_can_appear_directly_after_match(self):
        for detected_state in ("star_drop", "daily_star_drop", "nova_star_drop"):
            with self.subTest(detected_state=detected_state):
                self.assertEqual(
                    normalize_detected_state(
                        detected_state,
                        previous_state="match",
                        exact_star_drop_after_match=True,
                    ),
                    detected_state,
                )

    def test_nova_star_drop_can_survive_transient_match_after_result(self):
        self.assertEqual(
            normalize_detected_state(
                "nova_star_drop",
                previous_state="match",
                match_result_seen=True,
            ),
            "nova_star_drop",
        )
        self.assertEqual(
            normalize_detected_state(
                "daily_star_drop",
                previous_state="match",
                match_result_seen=True,
            ),
            "match",
        )

    def test_lobby_after_match_depends_on_stable_lobby_state_not_vision_quietness(self):
        self.assertFalse(should_accept_lobby_after_match(2.9, 3.0))
        self.assertTrue(should_accept_lobby_after_match(3.0, 3.0))
        self.assertTrue(should_accept_lobby_after_match(126.9, 3.0))

    def test_shop_panel_escape_is_allowed_after_match_when_brawl_pass_detected(self):
        state = apply_in_match_overlay_guard(
            "shop",
            detected_state="shop",
            previous_state="match",
            allow_panel_escape=True,
        )
        self.assertEqual(state, "shop")

    def test_shop_stays_suppressed_during_match_without_panel_escape(self):
        state = apply_in_match_overlay_guard(
            "shop",
            detected_state="shop",
            previous_state="match",
            allow_panel_escape=False,
        )
        self.assertEqual(state, "match")


if __name__ == "__main__":
    unittest.main()

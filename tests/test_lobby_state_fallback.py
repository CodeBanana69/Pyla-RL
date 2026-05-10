import unittest

import cv2
import numpy as np

from state_finder import (
    get_in_game_state,
    get_matchmaking_exit_button_center,
    get_starr_nova_got_it_button_center,
    get_starr_nova_hub_back_button_center,
    is_in_match_making,
    is_lobby_currency_bar_visible,
    is_lobby_hud_visible,
    is_lobby_quests_button_visible,
    is_lobby_play_button_visible,
    is_starr_nova_hub_screen,
    is_starr_nova_info_screen,
)


class LobbyStateFallbackTests(unittest.TestCase):
    @staticmethod
    def draw_lobby_hud(image):
        yellow_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (28, 230, 245), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        green_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (65, 220, 220), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        cyan_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (96, 190, 220), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        orange_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (20, 220, 220), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[850:1020, 1300:1820] = yellow_bgr
        image[12:76, 1170:1280] = (245, 245, 245)
        image[14:74, 1390:1500] = yellow_bgr
        image[14:74, 1580:1690] = green_bgr
        image[870:1040, 280:520] = (35, 35, 45)
        image[880:965, 300:420] = cyan_bgr
        image[930:1015, 390:500] = orange_bgr
        image[970:1035, 300:500] = (245, 245, 245)
        image[18:78, 1790:1880] = (245, 245, 245)
        image[0:95, 1760:1910] = np.maximum(image[0:95, 1760:1910], 35)

    @staticmethod
    def draw_starr_nova_info_screen(image):
        cyan_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (90, 220, 240), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        green_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (60, 245, 225), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[:] = (118, 118, 118)
        for x in range(0, 1920, 240):
            cv2.line(image, (x, 0), (x + 380, 1080), (92, 92, 92), 9)
        image[50:145, 610:1310] = (245, 245, 245)
        image[135:175, 760:1160] = cyan_bgr
        image[465:525, 70:540] = cyan_bgr
        image[465:525, 690:1230] = cyan_bgr
        image[465:525, 1290:1840] = cyan_bgr
        image[850:1010, 745:1175] = green_bgr
        image[900:960, 855:1070] = (250, 250, 250)
        image[942:972, 855:1070] = (25, 25, 25)

    @staticmethod
    def draw_starr_nova_hub_screen(image):
        cyan_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (90, 220, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        pink_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (150, 210, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        yellow_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (28, 220, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[:] = (214, 214, 214)
        for x in range(0, 1920, 280):
            cv2.line(image, (x, 0), (x + 280, 1080), (165, 165, 165), 6)
        image[0:115, 0:150] = (48, 56, 74)
        cv2.polylines(
            image,
            [np.array([(82, 18), (34, 56), (82, 96)], dtype=np.int32)],
            False,
            (245, 245, 245),
            18,
        )
        image[12:105, 180:820] = (245, 245, 245)
        image[25:92, 210:790] = cyan_bgr
        image[0:95, 1120:1660] = (8, 8, 8)
        image[8:45, 1340:1580] = pink_bgr
        image[45:83, 1320:1525] = cyan_bgr
        image[92:250, 330:850] = (245, 245, 245)
        image[112:225, 360:820] = cyan_bgr
        image[125:175, 555:760] = pink_bgr
        image[900:1065, 1250:1720] = yellow_bgr
        image[900:1065, 350:620] = pink_bgr

    @staticmethod
    def draw_matchmaking_screen(image):
        blue_bg = cv2.cvtColor(
            np.full((1, 1, 3), (100, 150, 205), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        deep_blue = cv2.cvtColor(
            np.full((1, 1, 3), (118, 150, 110), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        yellow_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (28, 225, 245), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[:] = blue_bg
        image[0:760, :] = blue_bg
        cv2.circle(image, (960, 180), 360, (236, 248, 248), -1)
        image[240:760, :] = np.maximum(image[240:760, :], deep_blue)
        image[120:210, 720:1190] = (245, 245, 245)
        image[112:220, 710:1200] = np.minimum(image[112:220, 710:1200], 40)
        image[125:205, 725:1185] = (245, 245, 245)
        star_points = np.array(
            [
                (960, 250), (1030, 360), (1160, 360), (1060, 450),
                (1110, 590), (960, 520), (810, 590), (860, 450),
                (760, 360), (890, 360),
            ],
            dtype=np.int32,
        )
        cv2.fillPoly(image, [star_points], yellow_bgr.tolist())
        cv2.polylines(image, [star_points], True, (10, 10, 10), 24)
        cv2.circle(image, (960, 425), 120, (10, 10, 10), -1)
        cv2.circle(image, (960, 425), 95, yellow_bgr.tolist(), -1)
        image[780:895, 430:1490] = (245, 245, 245)
        image[770:905, 420:1500] = np.minimum(image[770:905, 420:1500], 40)
        image[785:890, 435:1485] = (245, 245, 245)
        exit_template = cv2.imread("images/states/exit_match_making.png")
        th, tw = exit_template.shape[:2]
        image[954:954 + th, 1636:1636 + tw] = exit_template

    def test_detects_lobby_by_large_yellow_play_button(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        yellow_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (28, 230, 245), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[850:1020, 1300:1820] = yellow_bgr

        self.assertTrue(is_lobby_play_button_visible(image))
        self.assertFalse(is_lobby_hud_visible(image))

    def test_rejects_small_yellow_noise(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        yellow_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (28, 230, 245), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[900:930, 1300:1360] = yellow_bgr

        self.assertFalse(is_lobby_play_button_visible(image))

    def test_detects_lobby_only_when_multiple_hud_anchors_are_visible(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_lobby_hud(image)

        self.assertTrue(is_lobby_play_button_visible(image))
        self.assertTrue(is_lobby_currency_bar_visible(image))
        self.assertTrue(is_lobby_quests_button_visible(image))
        self.assertTrue(is_lobby_hud_visible(image))
        self.assertEqual(get_in_game_state(image), "lobby")

    def test_rejects_match_like_noise_without_full_lobby_hud(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        yellow_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (28, 230, 245), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        cyan_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (96, 190, 220), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[850:1020, 1300:1820] = yellow_bgr
        image[300:500, 700:1000] = cyan_bgr
        image[620:730, 615:950] = (0, 0, 230)

        self.assertFalse(is_lobby_hud_visible(image))
        self.assertEqual(get_in_game_state(image), "match")

    def test_team_invite_popup_is_ignored_by_state_detection(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        blue_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (105, 220, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        red_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (2, 220, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        green_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (60, 220, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        self.draw_lobby_hud(image)
        image[220:860, 550:1370] = blue_bgr
        image[620:730, 615:950] = red_bgr
        image[620:730, 970:1305] = green_bgr

        self.assertNotEqual(get_in_game_state(image), "popup")

    def test_starr_nova_info_screen_detects_got_it_button(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_starr_nova_info_screen(image)

        center = get_starr_nova_got_it_button_center(image)

        self.assertIsNotNone(center)
        self.assertTrue(is_starr_nova_info_screen(image))
        self.assertTrue(850 <= center[0] <= 1070)
        self.assertTrue(900 <= center[1] <= 960)

    def test_starr_nova_info_screen_rejects_plain_green_button(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        green_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (60, 245, 225), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[850:1010, 745:1175] = green_bgr
        image[900:960, 855:1070] = (250, 250, 250)

        self.assertFalse(is_starr_nova_info_screen(image))

    def test_starr_nova_hub_screen_detects_back_button(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_starr_nova_hub_screen(image)

        center = get_starr_nova_hub_back_button_center(image)

        self.assertIsNotNone(center)
        self.assertTrue(is_starr_nova_hub_screen(image))
        self.assertTrue(45 <= center[0] <= 85)
        self.assertTrue(40 <= center[1] <= 75)

    def test_starr_nova_hub_screen_rejects_plain_back_button(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        image[0:115, 0:150] = (48, 56, 74)
        cv2.polylines(
            image,
            [np.array([(82, 18), (34, 56), (82, 96)], dtype=np.int32)],
            False,
            (245, 245, 245),
            18,
        )

        self.assertIsNotNone(get_starr_nova_hub_back_button_center(image))
        self.assertFalse(is_starr_nova_hub_screen(image))

    def test_matchmaking_screen_is_own_state(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_matchmaking_screen(image)

        center = get_matchmaking_exit_button_center(image)

        self.assertIsNotNone(center)
        self.assertTrue(is_in_match_making(image))
        self.assertEqual(get_in_game_state(image), "match_making")

    def test_matchmaking_rejects_plain_red_button(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        red_button = cv2.cvtColor(
            np.full((1, 1, 3), (2, 220, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[935:1045, 1625:1890] = red_button
        image[960:1018, 1710:1845] = (250, 250, 250)

        self.assertFalse(is_in_match_making(image))
        self.assertNotEqual(get_in_game_state(image), "match_making")

    def test_matchmaking_rejects_exit_button_without_unique_screen_anchors(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        exit_template = cv2.imread("images/states/exit_match_making.png")
        th, tw = exit_template.shape[:2]
        image[954:954 + th, 1636:1636 + tw] = exit_template
        image[120:210, 720:1190] = (245, 245, 245)

        self.assertFalse(is_in_match_making(image))
        self.assertNotEqual(get_in_game_state(image), "match_making")


if __name__ == "__main__":
    unittest.main()

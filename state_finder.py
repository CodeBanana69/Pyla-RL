import os
import sys
import cv2
import numpy as np
sys.path.append(os.path.abspath('/'))
from utils import load_toml_as_dict

orig_screen_width, orig_screen_height = 1920, 1080

states_path = r"./images/states/"

star_drops_path = r"./images/star_drop_types/"
images_with_star_drop = []
for file in os.listdir(star_drops_path):
    if "star_drop" in file:
        images_with_star_drop.append(file)
images_with_star_drop.sort(key=lambda name: 0 if name in ("angelic_star_drop.png", "demonic_star_drop.png") else 1)
STAR_DROP_TEMPLATE_THRESHOLD = 0.97

end_results_path = r"./images/end_results/"

region_data = load_toml_as_dict("./cfg/lobby_config.toml")['template_matching']
super_debug = load_toml_as_dict("./cfg/general_config.toml")['super_debug'] == "yes"
_last_printed_state = None
if super_debug:
    debug_folder = "./debug_frames/"
    if not os.path.exists(debug_folder):
        os.makedirs(debug_folder)

def is_template_in_region(image, template_path, region, threshold=0.7):
    current_height, current_width = image.shape[:2]
    orig_x, orig_y, orig_width, orig_height = region
    width_ratio, height_ratio = current_width / orig_screen_width, current_height / orig_screen_height

    new_x, new_y = int(orig_x * width_ratio), int(orig_y * height_ratio)
    new_width, new_height = int(orig_width * width_ratio), int(orig_height * height_ratio)
    cropped_image = image[new_y:new_y + new_height, new_x:new_x + new_width]
    current_height, current_width = image.shape[:2]
    loaded_template = load_template(template_path, current_width, current_height)
    result = cv2.matchTemplate(cropped_image, loaded_template,
                               cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    return max_val > threshold

cached_templates = {}

def load_template(image_path, width, height):
    if (image_path, width, height) in cached_templates:
        return cached_templates[(image_path, width, height)]
    current_width_ratio, current_height_ratio = width / orig_screen_width, height / orig_screen_height
    image = cv2.imread(image_path)
    orig_height, orig_width = image.shape[:2]
    resized_image = cv2.resize(image, (int(orig_width * current_width_ratio), int(orig_height * current_height_ratio)))
    cached_templates[(image_path, width, height)] = resized_image
    return resized_image

crop_region = load_toml_as_dict("./cfg/lobby_config.toml")['lobby']['trophy_observer']
_current_gamemode = load_toml_as_dict("./cfg/bot_config.toml").get("gamemode", "")

# Showdown has place-based results (1st-4th in trio) instead of victory/defeat.
# Each place may have multiple template variants (different backgrounds at
# different trophy ranges). Any matching variant counts as that place.
showdown_place_templates = {
    "1st": ["sd1st.png"],
    "2nd": ["sd2nd.png"],
    "4th": ["sd4th.png"],
    "3rd": ["sd3rd.png", "sd3rd_alt.png"],
}


SHOWDOWN_PLACE_THRESHOLD = 0.95


def refresh_runtime_config():
    global region_data, super_debug, crop_region, _current_gamemode
    lobby_config = load_toml_as_dict("./cfg/lobby_config.toml")
    general_config = load_toml_as_dict("./cfg/general_config.toml")
    bot_config = load_toml_as_dict("./cfg/bot_config.toml")
    region_data = lobby_config['template_matching']
    crop_region = lobby_config['lobby']['trophy_observer']
    super_debug = str(general_config.get("super_debug", "no")).lower() in ("yes", "true", "1")
    _current_gamemode = bot_config.get("gamemode", "")
    if super_debug and not os.path.exists("./debug_frames/"):
        os.makedirs("./debug_frames/")


def find_game_result(screenshot):
    if _current_gamemode == "showdown":
        for place, template_files in showdown_place_templates.items():
            for template_file in template_files:
                if is_template_in_region(
                    screenshot,
                    end_results_path + template_file,
                    crop_region,
                    threshold=SHOWDOWN_PLACE_THRESHOLD,
                ):
                    return place
        return False

    is_victory = is_template_in_region(screenshot, end_results_path + 'victory.png', crop_region)
    if is_victory:
        return "victory"

    is_defeat = is_template_in_region(screenshot, end_results_path + 'defeat.png', crop_region)
    if is_defeat:
        return "defeat"

    is_draw = is_template_in_region(screenshot, end_results_path + 'draw.png', crop_region)
    if is_draw:
        return "draw"
    return False



def get_in_game_state(image):
    game_result = is_in_end_of_a_match(image)
    if game_result: return f"end_{game_result}"
    if is_in_shop(image): return "shop"
    if is_in_offer_popup(image): return "popup"
    if is_in_match_making(image): return "match_making"
    if is_in_lobby(image): return "lobby"
    if is_in_brawler_selection(image):
        return "brawler_selection"

    if is_in_brawl_pass(image) or is_in_star_road(image):
        return "shop"

    if is_in_daily_wins_hold_drop(image) or is_in_daily_wins_drop(image):
        return "daily_star_drop"

    if is_in_star_drop(image):
        return "star_drop"

    if is_in_trophy_reward(image):
        return "trophy_reward"

    if is_in_reward_unlock(image):
        return "reward_unlock"

    if is_in_prestige_reward(image):
        return "prestige_reward"

    return "match"


def is_in_shop(image) -> bool:
    return is_template_in_region(image, states_path + 'powerpoint.png', region_data["powerpoint"])


def is_in_brawler_selection(image) -> bool:
    return is_template_in_region(image, states_path + 'brawler_menu_task.png', region_data["brawler_menu_task"])


def is_in_offer_popup(image) -> bool:
    return is_template_in_region(image, states_path + 'close_popup.png', region_data["close_popup"])


def get_matchmaking_exit_button_center(image):
    region = region_data.get("exit_match_making", [1600, 925, 295, 135])
    template_path = states_path + "exit_match_making.png"
    if os.path.exists(template_path) and not is_template_in_region(
            image,
            template_path,
            region,
            threshold=0.82,
    ):
        return None

    current_height, current_width = image.shape[:2]
    width_ratio = current_width / orig_screen_width
    height_ratio = current_height / orig_screen_height

    # Matchmaking has a large red Exit button fixed in the lower-right corner.
    # Require the exact Exit template first, then use the color/shape pass only
    # to return a scaled click center. In-match red UI can otherwise resemble a
    # cancel button closely enough to cause false match_making states.
    x = int(region[0] * width_ratio)
    y = int(region[1] * height_ratio)
    w = int(region[2] * width_ratio)
    h = int(region[3] * height_ratio)
    crop = image[y:y + h, x:x + w]
    if crop.size == 0:
        return None

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    red_low = cv2.inRange(
        hsv,
        np.array((0, 90, 90), dtype=np.uint8),
        np.array((10, 255, 255), dtype=np.uint8),
    )
    red_high = cv2.inRange(
        hsv,
        np.array((170, 90, 90), dtype=np.uint8),
        np.array((179, 255, 255), dtype=np.uint8),
    )
    red_mask = cv2.bitwise_or(red_low, red_high)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, np.ones((7, 7), dtype=np.uint8))
    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    min_area = max(600, crop.shape[0] * crop.shape[1] * 0.18)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        bx, by, bw, bh = cv2.boundingRect(contour)
        if area < min_area or bw < w * 0.45 or bh < h * 0.30:
            continue
        button_part = crop[by:by + bh, bx:bx + bw]
        if button_part.size == 0:
            continue
        white_ratio = mask_ratio(button_part, (0, 0, 165), (179, 95, 255))
        dark_ratio = mask_ratio(button_part, (0, 0, 0), (179, 255, 75))
        if white_ratio < 0.015 or dark_ratio < 0.025:
            continue
        candidates.append((area, bx, by, bw, bh))

    if not candidates:
        return None
    _, bx, by, bw, bh = max(candidates, key=lambda item: item[0])
    return int(x + bx + bw / 2), int(y + by + bh / 2)


def is_matchmaking_tip_visible(image):
    top = crop_scaled_region(image, [650, 95, 620, 140])
    if top.size == 0:
        return False
    white_ratio = mask_ratio(top, (0, 0, 170), (179, 90, 255))
    dark_ratio = mask_ratio(top, (0, 0, 0), (179, 255, 80))
    return white_ratio > 0.035 and dark_ratio > 0.025


def is_matchmaking_background_visible(image):
    center = crop_scaled_region(image, [0, 0, 1920, 840])
    if center.size == 0:
        return False
    red_ratio = mask_ratio(center, (0, 60, 65), (12, 255, 255)) + mask_ratio(center, (170, 60, 65), (179, 255, 255))
    dark_ratio = mask_ratio(center, (0, 0, 0), (179, 255, 90))
    return red_ratio > 0.12 and dark_ratio > 0.035


def is_in_match_making(image) -> bool:
    return (
        get_matchmaking_exit_button_center(image) is not None
        and is_matchmaking_tip_visible(image)
        and is_matchmaking_background_visible(image)
    )


def is_in_lobby(image) -> bool:
    return is_lobby_hud_visible(image)


def crop_scaled_region(image, region):
    current_height, current_width = image.shape[:2]
    orig_x, orig_y, orig_width, orig_height = region
    width_ratio, height_ratio = current_width / orig_screen_width, current_height / orig_screen_height
    x = int(orig_x * width_ratio)
    y = int(orig_y * height_ratio)
    width = int(orig_width * width_ratio)
    height = int(orig_height * height_ratio)
    return image[y:y + height, x:x + width]


def mask_ratio(crop, lower, upper):
    if crop.size == 0:
        return 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
    return cv2.countNonZero(mask) / max(1, crop.shape[0] * crop.shape[1])


def get_starr_nova_got_it_button_center(image):
    current_height, current_width = image.shape[:2]
    width_ratio = current_width / orig_screen_width
    height_ratio = current_height / orig_screen_height

    # Fixed event-info layout: large green "GOT IT!" button centered near the
    # bottom. Region is intentionally tight so lobby/match green UI cannot
    # trigger it.
    button_crop = crop_scaled_region(image, [690, 835, 560, 190])
    if button_crop.size == 0:
        return None

    hsv = cv2.cvtColor(button_crop, cv2.COLOR_BGR2HSV)
    green_mask = cv2.inRange(
        hsv,
        np.array((48, 120, 120), dtype=np.uint8),
        np.array((76, 255, 255), dtype=np.uint8),
    )
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, np.ones((7, 7), dtype=np.uint8))
    contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    x0 = int(690 * width_ratio)
    y0 = int(835 * height_ratio)
    min_area = max(800, button_crop.shape[0] * button_crop.shape[1] * 0.16)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        bx, by, bw, bh = cv2.boundingRect(contour)
        if area < min_area or bw < button_crop.shape[1] * 0.35 or bh < button_crop.shape[0] * 0.28:
            continue
        button_part = button_crop[by:by + bh, bx:bx + bw]
        if button_part.size == 0:
            continue
        white_ratio = mask_ratio(button_part, (0, 0, 150), (179, 120, 255))
        dark_ratio = mask_ratio(button_part, (0, 0, 0), (179, 255, 80))
        if white_ratio < 0.015 or dark_ratio < 0.03:
            continue
        candidates.append((area, bx, by, bw, bh))

    if not candidates:
        return None
    _, bx, by, bw, bh = max(candidates, key=lambda item: item[0])
    return int(x0 + bx + bw / 2), int(y0 + by + bh / 2)


def is_starr_nova_info_screen(image):
    button_center = get_starr_nova_got_it_button_center(image)
    if button_center is None:
        return False
    starr_nova_region = region_data.get("starr_nova_event")
    if starr_nova_region and os.path.exists(states_path + "starr_nova_event.png"):
        if is_template_in_region(
                image,
                states_path + "starr_nova_event.png",
                starr_nova_region,
                threshold=0.78,
        ):
            return True

    # The screen is mostly grayscale manga panels, with cyan headings and the
    # bright event logo. These anchors make the green button check specific to
    # this event screen instead of any random confirmation button.
    full_hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    low_sat_ratio = cv2.countNonZero(
        cv2.inRange(full_hsv[:, :, 1], np.array(0, dtype=np.uint8), np.array(55, dtype=np.uint8))
    ) / max(1, image.shape[0] * image.shape[1])
    if low_sat_ratio < 0.45:
        return False

    top_region = crop_scaled_region(image, [500, 35, 920, 190])
    mid_region = crop_scaled_region(image, [0, 430, 1920, 300])
    if top_region.size == 0 or mid_region.size == 0:
        return False
    top_white = mask_ratio(top_region, (0, 0, 170), (179, 90, 255))
    top_cyan = mask_ratio(top_region, (82, 80, 120), (100, 255, 255))
    mid_cyan = mask_ratio(mid_region, (82, 90, 110), (100, 255, 255))
    return top_white > 0.025 and top_cyan > 0.006 and mid_cyan > 0.012


def is_lobby_hud_visible(image, required_anchors=3) -> bool:
    anchors = [
        is_lobby_play_button_visible(image),
        is_lobby_currency_bar_visible(image),
        is_lobby_quests_button_visible(image),
        is_lobby_menu_button_visible(image),
    ]
    return sum(1 for value in anchors if value) >= required_anchors


def is_lobby_play_button_visible(image) -> bool:
    current_height, current_width = image.shape[:2]
    width_ratio = current_width / orig_screen_width
    height_ratio = current_height / orig_screen_height

    region = [1260, 820, 610, 225]
    x = int(region[0] * width_ratio)
    y = int(region[1] * height_ratio)
    w = int(region[2] * width_ratio)
    h = int(region[3] * height_ratio)
    crop = image[y:y + h, x:x + w]
    if crop.size == 0:
        return False

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    yellow_mask = cv2.inRange(
        hsv,
        np.array((15, 90, 120), dtype=np.uint8),
        np.array((42, 255, 255), dtype=np.uint8),
    )
    yellow_pixels = cv2.countNonZero(yellow_mask)
    yellow_ratio = yellow_pixels / max(1, crop.shape[0] * crop.shape[1])
    if yellow_ratio < 0.28:
        return False

    contours, _ = cv2.findContours(yellow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return False
    largest = max(contours, key=cv2.contourArea)
    bx, by, bw, bh = cv2.boundingRect(largest)
    return bw > w * 0.45 and bh > h * 0.35


def is_lobby_currency_bar_visible(image) -> bool:
    crop = crop_scaled_region(image, [1120, 0, 620, 95])
    if crop.size == 0:
        return False
    yellow_ratio = mask_ratio(crop, (16, 80, 120), (42, 255, 255))
    green_ratio = mask_ratio(crop, (45, 80, 110), (88, 255, 255))
    white_ratio = mask_ratio(crop, (0, 0, 170), (179, 95, 255))
    dark_ratio = mask_ratio(crop, (0, 0, 0), (179, 255, 80))
    return yellow_ratio > 0.018 and green_ratio > 0.010 and white_ratio > 0.035 and dark_ratio > 0.15


def is_lobby_quests_button_visible(image) -> bool:
    crop = crop_scaled_region(image, [240, 850, 340, 220])
    if crop.size == 0:
        return False
    cyan_ratio = mask_ratio(crop, (82, 50, 110), (112, 255, 255))
    white_ratio = mask_ratio(crop, (0, 0, 160), (179, 90, 255))
    orange_ratio = mask_ratio(crop, (8, 80, 100), (32, 255, 255))
    dark_ratio = mask_ratio(crop, (0, 0, 0), (179, 255, 90))
    return cyan_ratio > 0.025 and white_ratio > 0.055 and orange_ratio > 0.015 and dark_ratio > 0.20


def is_lobby_menu_button_visible(image) -> bool:
    if is_template_in_region(image, states_path + 'lobby_menu.png', region_data["lobby_menu"]):
        return True
    crop = crop_scaled_region(image, [1760, 0, 160, 100])
    if crop.size == 0:
        return False
    white_ratio = mask_ratio(crop, (0, 0, 175), (179, 80, 255))
    dark_ratio = mask_ratio(crop, (0, 0, 0), (179, 255, 90))
    return white_ratio > 0.05 and dark_ratio > 0.18


def is_in_end_of_a_match(image):
    return find_game_result(image)



def is_in_trophy_reward(image):
    return is_template_in_region(image, states_path + 'trophies_screen.png', region_data["trophies_screen"])


def is_in_reward_unlock(image):
    # Generic "YOU GOT / Unlocked" reward page shown after trophy-road rewards.
    # It is intentionally guarded by main.py so this broad color detector is
    # only actionable inside the post-trophy reward chain.
    if is_in_skin_reward_unlock(image):
        return True

    full = crop_scaled_region(image, [0, 0, 1920, 1080])
    if full.size == 0:
        return False

    hsv = cv2.cvtColor(full, cv2.COLOR_BGR2HSV)
    blue_ratio = mask_ratio(full, (92, 80, 85), (118, 255, 255))
    if blue_ratio < 0.45:
        return False

    top = crop_scaled_region(image, [720, 120, 520, 150])
    bottom = crop_scaled_region(image, [700, 610, 560, 150])
    card = crop_scaled_region(image, [720, 260, 520, 330])
    if top.size == 0 or bottom.size == 0 or card.size == 0:
        return False

    top_white = mask_ratio(top, (0, 0, 170), (179, 80, 255))
    top_black = mask_ratio(top, (0, 0, 0), (179, 255, 65))
    bottom_yellow = mask_ratio(bottom, (18, 85, 110), (42, 255, 255))
    bottom_black = mask_ratio(bottom, (0, 0, 0), (179, 255, 70))
    card_dark = mask_ratio(card, (0, 0, 0), (179, 255, 80))
    card_light = mask_ratio(card, (85, 25, 115), (110, 150, 255))
    return (
            top_white > 0.08
            and top_black > 0.04
            and bottom_yellow > 0.04
            and bottom_black > 0.03
            and card_dark > 0.10
            and card_light > 0.08
    )


def get_skin_reward_continue_button_center(image):
    button_region = [885, 850, 420, 150]
    crop = crop_scaled_region(image, button_region)
    if crop.size == 0:
        return None

    blue_ratio = mask_ratio(crop, (100, 90, 120), (125, 255, 255))
    white_ratio = mask_ratio(crop, (0, 0, 170), (179, 90, 255))
    dark_ratio = mask_ratio(crop, (0, 0, 0), (179, 255, 80))
    if blue_ratio < 0.28 or white_ratio < 0.025 or dark_ratio < 0.08:
        return None

    current_height, current_width = image.shape[:2]
    width_ratio = current_width / orig_screen_width
    height_ratio = current_height / orig_screen_height
    x, y, w, h = button_region
    return int((x + w / 2) * width_ratio), int((y + h / 2) * height_ratio)


def is_in_skin_reward_unlock(image):
    continue_center = get_skin_reward_continue_button_center(image)
    if continue_center is None:
        return False

    background = crop_scaled_region(image, [0, 0, 1920, 1080])
    header = crop_scaled_region(image, [900, 0, 850, 110])
    title = crop_scaled_region(image, [860, 150, 900, 360])
    if background.size == 0 or header.size == 0 or title.size == 0:
        return False

    pink_ratio = mask_ratio(background, (138, 55, 90), (176, 255, 255))
    green_ratio = mask_ratio(title, (45, 90, 110), (82, 255, 255))
    white_ratio = mask_ratio(title, (0, 0, 170), (179, 95, 255))
    header_white = mask_ratio(header, (0, 0, 175), (179, 90, 255))
    header_dark = mask_ratio(header, (0, 0, 0), (179, 255, 75))
    return (
            pink_ratio > 0.28
            and green_ratio > 0.06
            and white_ratio > 0.05
            and header_white > 0.045
            and header_dark > 0.03
    )


def count_hsv_in_region(image, region, lower, upper):
    current_height, current_width = image.shape[:2]
    orig_x, orig_y, orig_width, orig_height = region
    width_ratio, height_ratio = current_width / orig_screen_width, current_height / orig_screen_height
    x = int(orig_x * width_ratio)
    y = int(orig_y * height_ratio)
    width = int(orig_width * width_ratio)
    height = int(orig_height * height_ratio)
    crop = image[y:y + height, x:x + width]
    if crop.size == 0:
        return 0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
    return int(cv2.countNonZero(mask))


def get_prestige_next_button_center(image):
    current_height, current_width = image.shape[:2]
    width_ratio = current_width / orig_screen_width
    height_ratio = current_height / orig_screen_height

    button_region = [1040, 760, 620, 250]
    x = int(button_region[0] * width_ratio)
    y = int(button_region[1] * height_ratio)
    w = int(button_region[2] * width_ratio)
    h = int(button_region[3] * height_ratio)
    button_crop = image[y:y + h, x:x + w]
    if button_crop.size == 0:
        return None

    hsv = cv2.cvtColor(button_crop, cv2.COLOR_BGR2HSV)
    green_mask = cv2.inRange(
        hsv,
        np.array((45, 120, 110), dtype=np.uint8),
        np.array((72, 255, 255), dtype=np.uint8),
    )
    contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    min_area = max(400, button_crop.shape[0] * button_crop.shape[1] * 0.04)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        bx, by, bw, bh = cv2.boundingRect(contour)
        if area < min_area or bw < w * 0.20 or bh < h * 0.15:
            continue
        button_part = button_crop[by:by + bh, bx:bx + bw]
        if button_part.size == 0:
            continue
        text_hsv = cv2.cvtColor(button_part, cv2.COLOR_BGR2HSV)
        white_mask = cv2.inRange(
            text_hsv,
            np.array((0, 0, 160), dtype=np.uint8),
            np.array((179, 100, 255), dtype=np.uint8),
        )
        white_pixels = cv2.countNonZero(white_mask)
        if white_pixels < max(80, int(button_part.shape[0] * button_part.shape[1] * 0.02)):
            continue
        candidates.append((area, bx, by, bw, bh))

    if not candidates:
        return None

    _, bx, by, bw, bh = max(candidates, key=lambda item: item[0])
    return int(x + bx + bw / 2), int(y + by + bh / 2)


def has_prestige_badge_shape(image):
    current_height, current_width = image.shape[:2]
    width_ratio = current_width / orig_screen_width
    height_ratio = current_height / orig_screen_height
    badge_region = [1060, 120, 680, 560]
    x = int(badge_region[0] * width_ratio)
    y = int(badge_region[1] * height_ratio)
    w = int(badge_region[2] * width_ratio)
    h = int(badge_region[3] * height_ratio)
    crop = image[y:y + h, x:x + w]
    if crop.size == 0:
        return False

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(
        hsv,
        np.array((96, 90, 90), dtype=np.uint8),
        np.array((126, 255, 255), dtype=np.uint8),
    )
    blue_mask = cv2.morphologyEx(
        blue_mask,
        cv2.MORPH_CLOSE,
        np.ones((9, 9), dtype=np.uint8),
    )
    contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return False

    scale = max(0.05, width_ratio * height_ratio)
    min_area = int(22000 * scale)
    min_width = int(180 * width_ratio)
    min_height = int(160 * height_ratio)
    for contour in contours:
        area = cv2.contourArea(contour)
        bx, by, bw, bh = cv2.boundingRect(contour)
        if area >= min_area and bw >= min_width and bh >= min_height:
            return True
    return False


def is_in_prestige_reward(image):
    button_center = get_prestige_next_button_center(image)
    if button_center is None:
        return False
    if not has_prestige_badge_shape(image):
        return False

    prestige_purple = count_hsv_in_region(
        image,
        [980, 80, 760, 660],
        (124, 80, 90),
        (162, 255, 255),
    )
    prestige_blue = count_hsv_in_region(
        image,
        [1060, 120, 650, 540],
        (95, 80, 80),
        (125, 255, 255),
    )
    scale = max(0.05, (image.shape[1] / orig_screen_width) * (image.shape[0] / orig_screen_height))
    return prestige_purple > int(18000 * scale) and prestige_blue > int(12000 * scale)



def is_in_brawl_pass(image):
    return is_template_in_region(image, states_path + 'brawl_pass_house.PNG', region_data['brawl_pass_house'])


def is_in_star_road(image):
    return is_template_in_region(image, states_path + "go_back_arrow.png", region_data['go_back_arrow'])


def is_in_star_drop(image):
    return get_star_drop_type(image) is not None


def get_star_drop_type(image):
    if is_in_daily_wins_hold_drop(image):
        return "daily_hold"
    if is_in_daily_wins_drop(image):
        return "standard"
    for image_filename in images_with_star_drop:
        if is_template_in_region(
                image,
                star_drops_path + image_filename,
                region_data['star_drop'],
                threshold=STAR_DROP_TEMPLATE_THRESHOLD,
        ):
            if image_filename == "angelic_star_drop.png":
                return "angelic"
            if image_filename == "demonic_star_drop.png":
                return "demonic"
            if image_filename == "starr_nova_star_drop.png":
                return "daily_hold"
            if not has_standard_star_drop_screen_context(image):
                return None
            return "standard"
    return None


def has_standard_star_drop_screen_context(image):
    background = crop_scaled_region(image, [340, 75, 1240, 830])
    if background.size == 0:
        return False

    hsv = cv2.cvtColor(background, cv2.COLOR_BGR2HSV)
    green_mask = cv2.inRange(
        hsv,
        np.array((38, 55, 55), dtype=np.uint8),
        np.array((92, 255, 255), dtype=np.uint8),
    )
    green_ratio = cv2.countNonZero(green_mask) / max(1, background.shape[0] * background.shape[1])
    if green_ratio < 0.16:
        return False

    top_title = crop_scaled_region(image, [690, 20, 540, 155])
    if top_title.size == 0:
        return False
    title_hsv = cv2.cvtColor(top_title, cv2.COLOR_BGR2HSV)
    bright_text = cv2.inRange(
        title_hsv,
        np.array((35, 0, 120), dtype=np.uint8),
        np.array((95, 255, 255), dtype=np.uint8),
    )
    return cv2.countNonZero(bright_text) > int(2200 * (image.shape[1] / orig_screen_width) * (image.shape[0] / orig_screen_height))


def is_in_daily_wins_drop(image):
    current_height, current_width = image.shape[:2]
    width_ratio, height_ratio = current_width / orig_screen_width, current_height / orig_screen_height

    def scaled_region(region):
        x, y, w, h = region
        return (
            int(x * width_ratio),
            int(y * height_ratio),
            int(w * width_ratio),
            int(h * height_ratio),
        )

    cx, cy, cw, ch = scaled_region([430, 90, 900, 760])
    center = image[cy:cy + ch, cx:cx + cw]
    if center.size == 0:
        return False

    hsv = cv2.cvtColor(center, cv2.COLOR_BGR2HSV)
    bright_green_mask = cv2.inRange(
        hsv,
        np.array((42, 100, 120), dtype=np.uint8),
        np.array((78, 255, 255), dtype=np.uint8),
    )
    bright_green_pixels = cv2.countNonZero(bright_green_mask)
    green_ratio = bright_green_pixels / max(1, center.shape[0] * center.shape[1])
    if green_ratio < 0.10:
        return False

    tx, ty, tw, th = scaled_region([0, 0, 520, 170])
    title = image[ty:ty + th, tx:tx + tw]
    if title.size == 0:
        return False

    title_hsv = cv2.cvtColor(title, cv2.COLOR_BGR2HSV)
    white_mask = cv2.inRange(
        title_hsv,
        np.array((0, 0, 160), dtype=np.uint8),
        np.array((179, 80, 255), dtype=np.uint8),
    )
    white_pixels = cv2.countNonZero(white_mask)
    dark_title_ratio = mask_ratio(title, (0, 0, 0), (179, 255, 85))
    if white_pixels <= int(1800 * width_ratio * height_ratio) or dark_title_ratio < 0.08:
        return False

    rx, ry, rw, rh = scaled_region([690, 20, 540, 170])
    rarity = image[ry:ry + rh, rx:rx + rw]
    if rarity.size == 0:
        return False
    rarity_green = mask_ratio(rarity, (42, 90, 100), (95, 255, 255))
    rarity_dark = mask_ratio(rarity, (0, 0, 0), (179, 255, 85))
    if rarity_green <= 0.055 or rarity_dark <= 0.035:
        return False

    sx, sy, sw, sh = scaled_region([620, 170, 680, 720])
    star = image[sy:sy + sh, sx:sx + sw]
    if star.size == 0:
        return False
    star_yellow = mask_ratio(star, (16, 70, 120), (42, 255, 255))
    star_dark = mask_ratio(star, (0, 0, 0), (179, 255, 85))
    star_white = mask_ratio(star, (0, 0, 180), (179, 70, 255))
    return star_yellow > 0.075 and star_dark > 0.025 and star_white > 0.010


def is_in_daily_wins_hold_drop(image):
    current_height, current_width = image.shape[:2]
    width_ratio, height_ratio = current_width / orig_screen_width, current_height / orig_screen_height

    def scaled_region(region):
        x, y, w, h = region
        return (
            int(x * width_ratio),
            int(y * height_ratio),
            int(w * width_ratio),
            int(h * height_ratio),
        )

    background = crop_scaled_region(image, [0, 0, 1920, 1080])
    if background.size == 0:
        return False
    purple_ratio = (
        mask_ratio(background, (124, 65, 90), (168, 255, 255))
        + mask_ratio(background, (0, 65, 90), (8, 255, 255))
    )
    if purple_ratio < 0.34:
        return False

    tx, ty, tw, th = scaled_region([0, 0, 540, 170])
    title = image[ty:ty + th, tx:tx + tw]
    if title.size == 0:
        return False
    title_white = mask_ratio(title, (0, 0, 160), (179, 90, 255))
    title_dark = mask_ratio(title, (0, 0, 0), (179, 255, 85))
    if title_white < 0.11 or title_dark < 0.08:
        return False

    sx, sy, sw, sh = scaled_region([520, 160, 720, 520])
    star = image[sy:sy + sh, sx:sx + sw]
    if star.size == 0:
        return False
    star_cyan = mask_ratio(star, (82, 45, 130), (108, 255, 255))
    star_pink = mask_ratio(star, (138, 45, 130), (174, 255, 255))
    star_white = mask_ratio(star, (0, 0, 178), (179, 85, 255))
    star_dark = mask_ratio(star, (0, 0, 0), (179, 255, 85))
    if star_cyan < 0.055 or star_pink < 0.035 or star_white < 0.065 or star_dark < 0.035:
        return False

    bx, by, bw, bh = scaled_region([680, 760, 560, 130])
    bottom = image[by:by + bh, bx:bx + bw]
    if bottom.size == 0:
        return False
    bottom_white = mask_ratio(bottom, (0, 0, 170), (179, 85, 255))
    bottom_dark = mask_ratio(bottom, (0, 0, 0), (179, 255, 85))
    return bottom_white > 0.075 and bottom_dark > 0.05

def get_state(screenshot):
    global _last_printed_state
    refresh_runtime_config()
    screenshot_bgr = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
    if super_debug: cv2.imwrite(f"./debug_frames/state_screenshot_{len(os.listdir('./debug_frames'))}.png", screenshot_bgr)
    state = get_in_game_state(screenshot_bgr)
    if super_debug or state != _last_printed_state:
        print(f"State: {state}")
        _last_printed_state = state
    return state

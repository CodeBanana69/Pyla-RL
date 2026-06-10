import os
import sys

import cv2
import numpy as np

sys.path.append(os.path.abspath('/'))
from utils import load_toml_as_dict, config_bool

orig_screen_width, orig_screen_height = 1920, 1080

states_path = r"./images/states/"

star_drops_path = r"./images/star_drop_types/"
images_with_star_drop = []
for file in os.listdir(star_drops_path):
    if "star_drop" in file:
        images_with_star_drop.append(file)

end_results_path = r"./images/end_results/"

match_result_crop_region = load_toml_as_dict("./cfg/lobby_config.toml")['lobby']['match_result']
region_data = load_toml_as_dict("./cfg/lobby_config.toml")['template_matching']


def is_template_in_region(image, template_path, region, threshold=0.7):
    if not os.path.exists(template_path):
        return False
    current_height, current_width = image.shape[:2]
    orig_x, orig_y, orig_width, orig_height = region
    width_ratio, height_ratio = current_width / orig_screen_width, current_height / orig_screen_height

    new_x, new_y = int(orig_x * width_ratio), int(orig_y * height_ratio)
    new_width, new_height = int(orig_width * width_ratio), int(orig_height * height_ratio)
    cropped_image = image[new_y:new_y + new_height, new_x:new_x + new_width]
    current_height, current_width = image.shape[:2]
    loaded_template = load_template(template_path, current_width, current_height)
    if loaded_template is None:
        return False
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
    if image is None:
        return None
    orig_height, orig_width = image.shape[:2]
    resized_image = cv2.resize(image, (int(orig_width * current_width_ratio), int(orig_height * current_height_ratio)))
    resized_colored_image = cv2.cvtColor(resized_image, cv2.COLOR_BGR2RGB)
    cached_templates[(image_path, width, height)] = resized_colored_image
    return resized_colored_image

SHOWDOWN_PLACE_THRESHOLD = 0.9
showdown_place_templates = {
    0: ["sd1st.png", "1st.png"],
    1: ["sd2nd.png", "2nd.png"],
    2: ["sd3rd.png", "sd3rd_alt.png", "3rd.png"],
    3: ["sd4th.png", "4th.png"],
}

def find_game_result(screenshot):
    for place, template_files in showdown_place_templates.items():
        for template_file in template_files:
            if is_template_in_region(
                    screenshot,
                    end_results_path + template_file,
                    match_result_crop_region,
                    threshold=SHOWDOWN_PLACE_THRESHOLD
            ):
                return f"trio_showdown_{place}"
    is_victory = is_template_in_region(screenshot, end_results_path + 'victory.png', match_result_crop_region)
    if is_victory:
        return "victory"

    is_defeat = is_template_in_region(screenshot, end_results_path + 'defeat.png', match_result_crop_region)
    if is_defeat:
        return "defeat"

    is_draw = is_template_in_region(screenshot, end_results_path + 'draw.png', match_result_crop_region)
    if is_draw:
        return "draw"
    return False


def get_in_game_state(image):
    game_result = is_in_end_of_a_match(image)
    if game_result: return f"end_{game_result}"
    if is_in_lobby(image): return "lobby"
    if is_in_match_making(image): return "match_making"
    if is_in_brawler_selection(image): return "brawler_selection"
    if is_in_shop(image): return "shop"
    if is_in_offer_popup(image): return "popup"
    if is_in_brawl_pass(image) or is_in_star_road(image): return "shop"

    star_drop_type = is_in_star_drop(image)
    if star_drop_type:
        return f"star_drop_{star_drop_type}"

    if is_in_trophy_reward(image):
        return "trophy_reward"

    return "match"


def is_in_shop(image) -> bool:
    return is_template_in_region(image, states_path + 'powerpoint.png', region_data["powerpoint"])


def is_in_brawler_selection(image) -> bool:
    return is_template_in_region(image, states_path + 'brawler_menu_task.png', region_data["brawler_menu_task"])


def is_in_offer_popup(image) -> bool:
    return is_template_in_region(image, states_path + 'close_popup.png', region_data["close_popup"])


def is_in_lobby(image) -> bool:
    return is_template_in_region(image, states_path + 'lobby_menu.png', region_data["lobby_menu"])


def is_in_end_of_a_match(image):
    return find_game_result(image)


def is_in_trophy_reward(image):
    return is_template_in_region(image, states_path + 'trophies_screen.png', region_data["trophies_screen"])


def is_in_brawl_pass(image):
    return is_template_in_region(image, states_path + 'brawl_pass_house.PNG', region_data['brawl_pass_house'])


def is_in_star_road(image):
    return is_template_in_region(image, states_path + "go_back_arrow.png", region_data['go_back_arrow'])


def is_in_match_making(image):
    return is_template_in_region(image, states_path + "exit_match_making.png", region_data['exit_match_making'])


def is_in_starr_nova_event(image):
    return is_template_in_region(image, states_path + "starr_nova_event.png", region_data['starr_nova_event'])


def is_in_star_drop(image):
    for image_filename in images_with_star_drop:
        if is_template_in_region(image, star_drops_path + image_filename, region_data['star_drop']):
            if "angelic" in image_filename.lower(): return "angelic"
            if "demonic" in image_filename.lower(): return "demonic"
            if "starr_nova" in image_filename.lower(): return "starr_nova"
            return "regular"
    return False


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


def get_starr_nova_hub_back_button_center(image):
    current_height, current_width = image.shape[:2]
    width_ratio = current_width / orig_screen_width
    height_ratio = current_height / orig_screen_height

    back_crop = crop_scaled_region(image, [0, 0, 150, 115])
    if back_crop.size == 0:
        return None

    hsv = cv2.cvtColor(back_crop, cv2.COLOR_BGR2HSV)
    white_ratio = cv2.countNonZero(
        cv2.inRange(hsv, np.array((0, 0, 180), dtype=np.uint8), np.array((179, 75, 255), dtype=np.uint8))
    ) / max(1, back_crop.shape[0] * back_crop.shape[1])
    dark_ratio = cv2.countNonZero(
        cv2.inRange(hsv, np.array((0, 0, 0), dtype=np.uint8), np.array((179, 255, 130), dtype=np.uint8))
    ) / max(1, back_crop.shape[0] * back_crop.shape[1])

    if white_ratio < 0.055 or dark_ratio < 0.18:
        return None

    return int(65 * width_ratio), int(55 * height_ratio)


def is_starr_nova_hub_screen(image):
    if get_starr_nova_hub_back_button_center(image) is None:
        return False

    top_logo = crop_scaled_region(image, [135, 0, 750, 130])
    event_timer = crop_scaled_region(image, [1120, 0, 560, 105])
    skin_card = crop_scaled_region(image, [250, 70, 650, 210])
    bottom_tabs = crop_scaled_region(image, [260, 880, 1400, 200])
    comic_background = crop_scaled_region(image, [900, 110, 880, 650])
    if (
            top_logo.size == 0
            or event_timer.size == 0
            or skin_card.size == 0
            or bottom_tabs.size == 0
            or comic_background.size == 0
    ):
        return False

    logo_white = mask_ratio(top_logo, (0, 0, 165), (179, 105, 255))
    logo_cyan = mask_ratio(top_logo, (80, 70, 110), (105, 255, 255))
    timer_magenta = mask_ratio(event_timer, (140, 80, 110), (172, 255, 255))
    timer_cyan = mask_ratio(event_timer, (82, 70, 110), (102, 255, 255))
    timer_black = mask_ratio(event_timer, (0, 0, 0), (179, 255, 70))
    card_cyan = mask_ratio(skin_card, (80, 70, 110), (105, 255, 255))
    card_pink = mask_ratio(skin_card, (135, 70, 110), (172, 255, 255))
    bottom_yellow = mask_ratio(bottom_tabs, (18, 80, 120), (42, 255, 255))
    bottom_magenta = mask_ratio(bottom_tabs, (135, 80, 110), (172, 255, 255))
    bottom_gray = mask_ratio(bottom_tabs, (0, 0, 70), (179, 80, 190))
    background_gray = mask_ratio(comic_background, (0, 0, 95), (179, 80, 255))
    background_blue = mask_ratio(comic_background, (95, 70, 70), (125, 255, 255))

    top_event_anchor = timer_black > 0.20 and timer_magenta > 0.012 and timer_cyan > 0.010
    content_anchor = (
            (card_cyan > 0.012 and card_pink > 0.006)
            or card_pink > 0.018
            or background_gray > 0.42
    )
    bottom_anchor = bottom_gray > 0.22 and (bottom_yellow > 0.008 or bottom_magenta > 0.012)
    comic_anchor = background_gray > 0.34 and background_blue < 0.18
    return (
            logo_white > 0.025
            and logo_cyan > 0.003
            and top_event_anchor
            and comic_anchor
            and content_anchor
            and bottom_anchor
    )


def get_state(screenshot):
    if screenshot is None:
        raise ValueError("get_state called with None screenshot")
    state = get_in_game_state(screenshot)
    if config_bool(load_toml_as_dict("cfg/debug_settings.toml").get('verbose_debug'), False): cv2.imwrite(f"./debug_frames/state_screenshot_{state}_{len(os.listdir('./debug_frames'))}.png", cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB))
    return state

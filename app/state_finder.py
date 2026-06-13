import os

import cv2
import numpy as np

from utils import imread_unicode, imwrite_unicode, load_toml_as_dict, config_bool, resolve_project_path

orig_screen_width, orig_screen_height = 1920, 1080

states_path = resolve_project_path("images/states/")

star_drops_path = resolve_project_path("images/star_drop_types/")
images_with_star_drop = []
for file in os.listdir(star_drops_path):
    if "star_drop" in file:
        images_with_star_drop.append(file)

end_results_path = resolve_project_path("images/end_results/")

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
    resolved_image_path = resolve_project_path(image_path)
    cache_key = (resolved_image_path, width, height)
    if cache_key in cached_templates:
        return cached_templates[cache_key]
    current_width_ratio, current_height_ratio = width / orig_screen_width, height / orig_screen_height
    image = imread_unicode(resolved_image_path)
    if image is None:
        return None
    orig_height, orig_width = image.shape[:2]
    resized_image = cv2.resize(image, (int(orig_width * current_width_ratio), int(orig_height * current_height_ratio)))
    resized_colored_image = cv2.cvtColor(resized_image, cv2.COLOR_BGR2RGB)
    cached_templates[cache_key] = resized_colored_image
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

    if is_in_reward_unlock(image):
        return "reward_unlock"

    if is_in_prestige_reward(image):
        return "prestige_reward"

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


def is_in_reward_unlock(image):
    if is_in_skin_reward_unlock(image):
        return True

    full = crop_scaled_region(image, [0, 0, 1920, 1080])
    if full.size == 0:
        return False

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


def get_skin_reward_equip_button_center(image):
    button_region = [1330, 830, 520, 180]
    crop = crop_scaled_region(image, button_region)
    if crop.size == 0:
        return None

    green_ratio = mask_ratio(crop, (45, 80, 100), (82, 255, 255))
    white_ratio = mask_ratio(crop, (0, 0, 170), (179, 90, 255))
    dark_ratio = mask_ratio(crop, (0, 0, 0), (179, 255, 85))
    if green_ratio < 0.24 or white_ratio < 0.02 or dark_ratio < 0.05:
        return None

    current_height, current_width = image.shape[:2]
    width_ratio = current_width / orig_screen_width
    height_ratio = current_height / orig_screen_height
    x, y, w, h = button_region
    return int((x + w / 2) * width_ratio), int((y + h / 2) * height_ratio)


def is_in_skin_reward_unlock(image):
    continue_center = get_skin_reward_continue_button_center(image)
    equip_center = get_skin_reward_equip_button_center(image)
    if continue_center is None and equip_center is None:
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
    if config_bool(load_toml_as_dict("cfg/debug_settings.toml").get('verbose_debug'), False):
        debug_dir = resolve_project_path("debug_frames")
        os.makedirs(debug_dir, exist_ok=True)
        frame_path = os.path.join(
            debug_dir,
            f"state_screenshot_{state}_{len(os.listdir(debug_dir))}.png",
        )
        imwrite_unicode(frame_path, cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB))
    return state

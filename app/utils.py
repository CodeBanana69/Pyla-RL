import hashlib
import io
import math
import os
import random
import re
import sys
import time
from pathlib import Path
from io import BytesIO
import ctypes
import json
import aiohttp
import requests
import toml
from PIL import Image
from discord import Webhook
import discord
import cv2
import numpy as np
from packaging import version

DEVELOPER_API_BASE_URL = "https://developer.brawlstars.com/api/"
_brawl_stars_api_refresh_done = False
_brawl_stars_api_refresh_signature = None
_brawler_name_aliases = None
BRAWL_STARS_API_CONFIG_PATH = "cfg/brawl_stars_api.toml"
LOCAL_BRAWL_STARS_API_CONFIG_PATH = "cfg/brawl_stars_api.local.toml"
DEFAULT_QUEUE_PATH = "data/latest_brawler_data.json"
LEGACY_QUEUE_PATH = "latest_brawler_data.json"


def install_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def project_root():
    if getattr(sys, "frozen", False):
        return os.path.join(install_root(), "app")
    return os.path.dirname(os.path.abspath(__file__))


def default_queue_path():
    resolved = resolve_project_path(DEFAULT_QUEUE_PATH)
    legacy = resolve_project_path(LEGACY_QUEUE_PATH)
    if os.path.exists(legacy) and not os.path.exists(resolved):
        return legacy
    return resolved


def resolve_project_path(file_path):
    file_path = os.fspath(file_path)
    if os.path.isabs(file_path):
        return file_path
    normalized = file_path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return os.path.join(project_root(), normalized)


def _config_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _developer_api_post(session, endpoint, payload, timeout):
    response = session.post(
        DEVELOPER_API_BASE_URL + endpoint,
        json=payload,
        timeout=timeout,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://developer.brawlstars.com",
            "Referer": "https://developer.brawlstars.com/",
        },
    )
    if response.status_code == 200:
        try:
            return response.json()
        except ValueError:
            return {}
    try:
        error_payload = response.json()
        reason = error_payload.get("description") or error_payload.get("message") or response.text
    except ValueError:
        reason = response.text
    raise RuntimeError(f"Developer portal error {response.status_code} at {endpoint}: {reason}")


def _is_developer_session_not_found(error):
    text = str(error).lower()
    return "account/load" in text and "401" in text and "session not found" in text


def _is_developer_key_limit_reached(error):
    text = str(error).lower()
    return "apikey/create" in text and "allowed keys limit reached" in text


def _revoke_developer_api_keys(session, existing_keys, key_name_prefix, delete_all_tokens, timeout):
    revoked = 0
    for api_key in existing_keys:
        key_name = str(api_key.get("name", ""))
        if delete_all_tokens or key_name.startswith(key_name_prefix):
            key_id = api_key.get("id")
            if key_id:
                _developer_api_post(session, "apikey/revoke", {"id": key_id}, timeout)
                revoked += 1
    return revoked


def _create_developer_api_key(session, create_payload, timeout):
    return _developer_api_post(session, "apikey/create", create_payload, timeout)


def _api_refresh_signature(file_path, config):
    return (
        resolve_project_path(file_path),
        str(config.get("developer_email", "")).strip(),
        str(config.get("developer_password", "")).strip(),
        str(config.get("player_tag", "")).strip(),
    )


def _extract_api_token(value):
    if isinstance(value, dict):
        return str(value.get("key") or value.get("token") or "").strip()
    return str(value or "").strip()


def _masked_presence(value):
    return "yes" if str(value or "").strip() else "no"


def _player_tag_presence(config):
    tag = str(get_config_player_tag(config) or "").strip().upper()
    return "yes" if tag and tag != "#YOURTAG" else "no"


def brawl_stars_api_config_status(config, file_path="cfg/brawl_stars_api.toml"):
    resolved_file_path = resolve_project_path(file_path)
    return (
        f"file={resolved_file_path}; "
        f"exists={'yes' if os.path.exists(resolved_file_path) else 'no'}; "
        f"auto_refresh_token={'yes' if _config_bool(config.get('auto_refresh_token'), False) else 'no'}; "
        f"developer_email_present={_masked_presence(config.get('developer_email'))}; "
        f"developer_password_present={_masked_presence(config.get('developer_password'))}; "
        f"player_tag_present={_player_tag_presence(config)}; "
        f"api_token_present={_masked_presence(_extract_api_token(config.get('api_token', '')))}"
    )


def _is_default_brawl_stars_api_config_path(file_path):
    return os.path.normcase(resolve_project_path(file_path)) == os.path.normcase(resolve_project_path(BRAWL_STARS_API_CONFIG_PATH))


def _brawl_stars_api_write_path(file_path):
    if _is_default_brawl_stars_api_config_path(file_path):
        return LOCAL_BRAWL_STARS_API_CONFIG_PATH
    return file_path


def _load_brawl_stars_api_toml_config(file_path):
    clear_toml_cache(file_path)
    config = dict(load_toml_as_dict(file_path))
    if _is_default_brawl_stars_api_config_path(file_path):
        local_path = resolve_project_path(LOCAL_BRAWL_STARS_API_CONFIG_PATH)
        if os.path.exists(local_path):
            clear_toml_cache(LOCAL_BRAWL_STARS_API_CONFIG_PATH)
            config.update(load_toml_as_dict(LOCAL_BRAWL_STARS_API_CONFIG_PATH))
    return config


def get_public_ip(service_url="https://api.ipify.org"):
    response = requests.get(service_url, timeout=15)
    response.raise_for_status()
    ip_address = response.text.strip()
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip_address):
        raise RuntimeError(f"Public IP service returned an invalid IPv4 address: {ip_address}")
    return ip_address


def refresh_brawl_stars_api_token_if_enabled(config, file_path="cfg/brawl_stars_api.toml", force=False):
    global _brawl_stars_api_refresh_done, _brawl_stars_api_refresh_signature
    if not _config_bool(config.get("auto_refresh_token"), False):
        _brawl_stars_api_refresh_done = True
        return config

    email = str(config.get("developer_email", "")).strip()
    password = str(config.get("developer_password", "")).strip()
    player_tag = str(config.get("player_tag", "")).strip()
    existing_token = _extract_api_token(config.get("api_token", ""))
    write_path = _brawl_stars_api_write_path(file_path)
    resolved_file_path = resolve_project_path(write_path)
    refresh_signature = _api_refresh_signature(file_path, config)

    if (
            not force
            and
            _brawl_stars_api_refresh_done
            and _brawl_stars_api_refresh_signature == refresh_signature
            and existing_token
    ):
        return config

    if not email or not password:
        _brawl_stars_api_refresh_done = False
        _brawl_stars_api_refresh_signature = None
        raise ValueError(
            "auto_refresh_token is enabled, but developer_email/developer_password are missing. "
            f"Open {resolved_file_path} and fill developer_email, developer_password, and player_tag. "
            f"Detected: {brawl_stars_api_config_status(config, file_path)}"
        )

    timeout = int(config.get("timeout_seconds", 15))
    key_name_prefix = str(config.get("key_name_prefix", "PylaAi-XXZ Auto")).strip() or "PylaAi-XXZ Auto"
    delete_old_auto_tokens = _config_bool(config.get("delete_old_auto_tokens"), True)
    delete_all_tokens = _config_bool(config.get("delete_all_tokens"), False)
    public_ip_service = str(config.get("public_ip_service", "https://api.ipify.org")).strip()
    public_ip = get_public_ip(public_ip_service)

    last_session_error = None
    for attempt in range(2):
        session = requests.Session()
        _developer_api_post(session, "login", {"email": email, "password": password}, timeout)
        try:
            account = _developer_api_post(session, "account/load", {}, timeout)
            break
        except RuntimeError as e:
            last_session_error = e
            if attempt == 0 and _is_developer_session_not_found(e):
                time.sleep(0.5)
                continue
            raise
    else:
        raise last_session_error
    developer = account.get("developer", {})
    scopes = developer.get("allowedScopes") or ["brawlstars"]

    existing_keys = _developer_api_post(session, "apikey/list", {}, timeout).get("keys", [])
    if delete_all_tokens or delete_old_auto_tokens:
        _revoke_developer_api_keys(session, existing_keys, key_name_prefix, delete_all_tokens, timeout)

    key_name = f"{key_name_prefix} {time.strftime('%Y-%m-%d %H:%M:%S')}"
    description = str(config.get("key_description", "Auto-generated by PylaAi-XXZ for the current public IP."))
    create_payload = {
        "name": key_name,
        "description": description,
        "cidrRanges": [public_ip],
        "scopes": scopes,
    }
    try:
        created = _create_developer_api_key(session, create_payload, timeout)
    except RuntimeError as e:
        if not _is_developer_key_limit_reached(e):
            raise
        print(
            "Brawl Stars API key limit reached; revoking old auto-generated keys and retrying token refresh."
        )
        refreshed_keys = _developer_api_post(session, "apikey/list", {}, timeout).get("keys", [])
        revoked = _revoke_developer_api_keys(session, refreshed_keys, key_name_prefix, delete_all_tokens, timeout)
        if revoked == 0:
            raise RuntimeError(
                "Brawl Stars API key limit reached and no auto-generated keys matched "
                f"'{key_name_prefix}'. Delete unused keys at https://developer.brawlstars.com/ "
                "or enable delete_old_auto_tokens in cfg/brawl_stars_api.toml."
            ) from e
        created = _create_developer_api_key(session, create_payload, timeout)

    new_token = _extract_api_token(created.get("key") or created.get("token"))
    if not new_token:
        refreshed_keys = _developer_api_post(session, "apikey/list", {}, timeout).get("keys", [])
        matching_keys = [api_key for api_key in refreshed_keys if api_key.get("name") == key_name]
        if matching_keys:
            new_token = _extract_api_token(matching_keys[0].get("key") or matching_keys[0].get("token"))

    if not new_token:
        raise RuntimeError("Created a developer key, but could not find the returned API token.")

    config["api_token"] = new_token
    config["last_public_ip"] = public_ip
    save_dict_as_toml(config, write_path)
    _brawl_stars_api_refresh_done = True
    _brawl_stars_api_refresh_signature = refresh_signature
    print(f"Refreshed Brawl Stars API token for public IP {public_ip}.")
    return config


class EasyOCRInitializationError(RuntimeError):
    pass


class DefaultEasyOCR:
    def __init__(self):
        import easyocr

        try:
            self.reader = easyocr.Reader(['en'], verbose=False, gpu=False)
        except Exception as exc:
            raise EasyOCRInitializationError(f"EasyOCR initialization failed: {exc}") from exc

    def readtext(self, image_input):
        return self.reader.readtext(image_input)


cached_toml = {}

def load_toml_as_dict(file_path):
    resolved_file_path = resolve_project_path(file_path)
    if resolved_file_path not in cached_toml:
        if os.path.exists(resolved_file_path):
            with open(resolved_file_path, 'r', encoding='utf-8-sig') as f:
                cached_toml[resolved_file_path] = toml.load(f)
        else:
            cached_toml[resolved_file_path] = {}
    return cached_toml[resolved_file_path]

def clear_toml_cache(file_path=None):
    if file_path is None:
        cached_toml.clear()
    else:
        cached_toml.pop(resolve_project_path(file_path), None)

def save_dict_as_toml(data, file_path):
    resolved_file_path = resolve_project_path(file_path)
    os.makedirs(os.path.dirname(resolved_file_path), exist_ok=True)
    with open(resolved_file_path, 'w', encoding='utf-8') as f:
        toml.dump(data, f)
    cached_toml[resolved_file_path] = data


reader = None


def get_ocr_reader():
    global reader
    if reader is None:
        reader = DefaultEasyOCR()
    return reader


def extract_text_and_positions(image_path):
    results = get_ocr_reader().readtext(image_path)
    text_details = {}
    for (bbox, text, prob) in results:
        top_left, top_right, bottom_right, bottom_left = bbox
        cx = (top_left[0] + top_right[0] + bottom_right[0] + bottom_left[0]) / 4
        cy = (top_left[1] + top_right[1] + bottom_right[1] + bottom_left[1]) / 4
        center = (cx, cy)
        formatted_bbox = {
            'top_left': top_left,
            'top_right': top_right,
            'bottom_right': bottom_right,
            'bottom_left': bottom_left,
            'center': center
        }

        text_details[text.lower()] = formatted_bbox

    return text_details


def extract_all_text_boxes(image_input):
    results = get_ocr_reader().readtext(image_input)
    entries = []
    for (bbox, text, prob) in results:
        top_left, top_right, bottom_right, bottom_left = bbox
        cx = (top_left[0] + top_right[0] + bottom_right[0] + bottom_left[0]) / 4
        cy = (top_left[1] + top_right[1] + bottom_right[1] + bottom_left[1]) / 4
        entries.append({
            "text": str(text),
            "text_lower": str(text).lower(),
            "confidence": float(prob),
            "box": {
                "top_left": top_left,
                "top_right": top_right,
                "bottom_right": bottom_right,
                "bottom_left": bottom_left,
                "center": (cx, cy),
            },
        })
    return entries


def extract_text_strings(image_input):
    return [str(result[1]).lower() for result in get_ocr_reader().readtext(image_input)]


cfg_api_base_url = load_toml_as_dict("cfg/general_config.toml").get("api_base_url", "default")
api_base_url = cfg_api_base_url if cfg_api_base_url != "default" else "localhost"
PYLA_VERSION = str(load_toml_as_dict("cfg/general_config.toml").get("pyla_version", "pyla-rl"))
brawlers_info_file_path = "cfg/brawlers_info.json"

def count_hsv_pixels(cv_image, low_hsv, high_hsv):
    hsv_image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv_image, low_hsv, high_hsv)
    return cv2.countNonZero(mask)

def save_brawler_data(data):
    """Save farm plan JSON for the active instance (if any)."""
    try:
        from core.integration import save_queue_data

        save_queue_data(data)
        return
    except Exception:
        pass
    queue_path = default_queue_path()
    os.makedirs(os.path.dirname(queue_path), exist_ok=True)
    with open(queue_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=4)


def normalize_brawler_name(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def load_brawler_name_aliases(file_path="cfg/names.json"):
    global _brawler_name_aliases
    if _brawler_name_aliases is not None:
        return _brawler_name_aliases

    aliases = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_aliases = json.load(f)
    except FileNotFoundError:
        raw_aliases = {}
    except Exception as e:
        print(f"Could not load brawler OCR aliases from {file_path}: {e}")
        raw_aliases = {}

    for canonical, values in raw_aliases.items():
        canonical_key = normalize_brawler_name(canonical)
        if not canonical_key:
            continue
        aliases[canonical_key] = canonical_key
        if not isinstance(values, list):
            values = [values]
        for value in values:
            alias_key = normalize_brawler_name(value)
            if alias_key:
                aliases[alias_key] = canonical_key

    _brawler_name_aliases = aliases
    return aliases


def resolve_brawler_name_alias(name):
    normalized = normalize_brawler_name(name)
    return load_brawler_name_aliases().get(normalized, normalized)


def resolve_brawler_info_key(name, brawlers_info=None):
    brawlers_info = brawlers_info or load_brawlers_info()
    if not name:
        return name
    if name in brawlers_info:
        return name
    needle = normalize_brawler_name(name)
    if not needle:
        return name
    for key in brawlers_info:
        if normalize_brawler_name(key) == needle:
            return key
    return name

def get_config_player_tag(config):
    tag = str(config.get("player_tag", "")).strip()
    if tag and tag.upper() != "#YOURTAG":
        return tag
    general_tag = str(load_toml_as_dict("cfg/general_config.toml").get("player_tag", "")).strip()
    if general_tag and general_tag.upper() != "#YOURTAG":
        return general_tag
    return tag


def fetch_brawl_stars_player(api_token, player_tag, timeout=15):
    api_token = _extract_api_token(api_token)
    cleaned_tag = str(player_tag).strip().upper()
    if not api_token:
        config_path = resolve_project_path("cfg/brawl_stars_api.toml")
        raise ValueError(
            "Missing Brawl Stars API token. Enable auto_refresh_token and fill "
            f"developer_email/developer_password in {config_path}."
        )
    if not cleaned_tag or cleaned_tag == "#YOURTAG":
        raise ValueError(
            "Missing player_tag in cfg/brawl_stars_api.toml. Replace #YOURTAG with your Brawl Stars player tag."
        )
    if not cleaned_tag.startswith("#"):
        cleaned_tag = f"#{cleaned_tag}"

    encoded_tag = cleaned_tag.replace("#", "%23")
    response = requests.get(
        f"https://api.brawlstars.com/v1/players/{encoded_tag}",
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=timeout,
    )
    if response.status_code == 200:
        return response.json()
    try:
        error_payload = response.json()
        reason = error_payload.get("reason") or error_payload.get("message") or response.text
    except ValueError:
        reason = response.text
    if response.status_code == 403:
        config_path = resolve_project_path("cfg/brawl_stars_api.toml")
        raise RuntimeError(
            "Brawl Stars API accessDenied. Your API token is not valid for the current public IP. "
            f"Enable auto_refresh_token and fill developer_email/developer_password in {config_path}, "
            "or create a new token manually for this PC's public IP."
        )
    raise RuntimeError(f"Brawl Stars API error {response.status_code}: {reason}")


def _use_existing_api_token_after_refresh_failure(config, file_path, error):
    global _brawl_stars_api_refresh_done, _brawl_stars_api_refresh_signature
    if not _extract_api_token(config.get("api_token", "")):
        raise error
    _brawl_stars_api_refresh_done = True
    _brawl_stars_api_refresh_signature = _api_refresh_signature(file_path, config)
    print(f"Brawl Stars API auto-refresh failed ({error}); using existing api_token.")
    return config


def _extract_config_text_value(text, key):
    match = re.search(rf'^\s*{re.escape(key)}\s*=\s*"(.*?)"\s*(?:#.*)?$', text, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*([^\r\n#]+)", text, re.MULTILINE)
    if match:
        return match.group(1).strip().strip("'\"")
    return None


def load_brawl_stars_api_config(file_path="cfg/brawl_stars_api.toml", force_refresh=False):
    resolved_file_path = resolve_project_path(file_path)
    try:
        config = _load_brawl_stars_api_toml_config(file_path)
        config["player_tag"] = get_config_player_tag(config)
        try:
            if force_refresh:
                return refresh_brawl_stars_api_token_if_enabled(config, file_path, force=True)
            return refresh_brawl_stars_api_token_if_enabled(config, file_path)
        except Exception as e:
            if force_refresh:
                raise
            return _use_existing_api_token_after_refresh_failure(config, file_path, e)
    except toml.TomlDecodeError:
        pass

    if not os.path.exists(resolved_file_path):
        return {
            "player_tag": get_config_player_tag({}),
            "timeout_seconds": 15,
            "auto_refresh_token": True,
        }

    with open(resolved_file_path, "r", encoding="utf-8-sig") as f:
        text = f.read()

    config = {}
    token_value = _extract_config_text_value(text, "api_token")
    if token_value is not None:
        config["api_token"] = "".join(token_value.split())

    tag_value = _extract_config_text_value(text, "player_tag")
    if tag_value is not None:
        config["player_tag"] = tag_value.strip()
    else:
        config["player_tag"] = str(load_toml_as_dict("cfg/general_config.toml").get("player_tag", "")).strip()

    config["player_tag"] = get_config_player_tag(config)

    timeout_match = re.search(r"timeout_seconds\s*=\s*(\d+)", text)
    if timeout_match:
        config["timeout_seconds"] = int(timeout_match.group(1))
    else:
        config["timeout_seconds"] = 15

    auto_refresh_match = re.search(r"auto_refresh_token\s*=\s*(true|false)", text, re.IGNORECASE)
    config["auto_refresh_token"] = (
        auto_refresh_match.group(1).lower() == "true" if auto_refresh_match else True
    )

    for key in (
        "developer_email",
        "developer_password",
        "public_ip_service",
        "key_name_prefix",
        "key_description",
        "last_public_ip",
    ):
        value = _extract_config_text_value(text, key)
        if value is not None:
            config[key] = value

    for key in ("delete_old_auto_tokens", "delete_all_tokens", "sync_trophies_after_match"):
        match = re.search(rf"{key}\s*=\s*(true|false)", text, re.IGNORECASE)
        if match:
            config[key] = match.group(1).lower() == "true"

    if "sync_trophies_after_match" not in config:
        config["sync_trophies_after_match"] = True

    try:
        if force_refresh:
            return refresh_brawl_stars_api_token_if_enabled(config, file_path, force=True)
        return refresh_brawl_stars_api_token_if_enabled(config, file_path)
    except Exception as e:
        if force_refresh:
            raise
        return _use_existing_api_token_after_refresh_failure(config, file_path, e)


def find_template_center(main_img, template, threshold=0.8):

    main_image_cv = cv2.cvtColor(main_img, cv2.COLOR_RGB2GRAY)
    if len(template.shape) == 3 and template.shape[2] == 3:
        template_cv = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    else:
        template_cv = template
    w, h = template_cv.shape[::-1]

    # Perform template matching
    result = cv2.matchTemplate(main_image_cv, template_cv, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

    # Check if the match is found based on a threshold value
    if max_val >= threshold:
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2

        return center_x, center_y
    else:
        return False


def load_brawlers_info():
    if os.path.exists(brawlers_info_file_path):
        with open(brawlers_info_file_path, 'r') as f:
            return json.load(f)
    else:
        return {}

def update_brawlers_info(brawlers_info):
    with open(brawlers_info_file_path, 'w') as f:
        json.dump(brawlers_info, f, indent=4)


def get_brawler_list():
    if api_base_url == "localhost":
        brawler_list = list(load_brawlers_info().keys())
        return brawler_list
    url = f'https://{api_base_url}/get_brawler_list'
    response = requests.post(url)
    if response.status_code == 201:
        data = response.json()
        return data.get('brawlers', [])
    else:
        return []


def update_missing_brawlers_info(brawlers):
    brawlers_info = load_brawlers_info()
    for brawler in brawlers:
        if brawler not in brawlers_info:
            brawler_info = get_brawler_info(brawler)
            if brawler_info:
                brawlers_info[brawler] = brawler_info
                update_brawlers_info(brawlers_info)
                print(f"Added info for brawler '{brawler}': {brawler_info}")
                # Download the brawler icon
                save_brawler_icon(brawler)
            else:
                print(f"Could not find info for brawler '{brawler}'")
        if not os.path.exists(f"./api/assets/brawler_icons/{brawler}.png"):
            save_brawler_icon(brawler)


def get_brawler_info(brawler_name):
    url = f'https://{api_base_url}/get_brawler_info'  # Adjust the URL if necessary
    response = requests.post(url, json={'brawler_name': brawler_name})
    if response.status_code == 200:
        data = response.json()
        return data.get('info', [])
    else:
        print(f"Error fetching range for '{brawler_name}': {response.status_code} - {response.text}")
        return None


def save_brawler_icon(brawler_name):
    # Clean the brawler name for filename
    brawler_name_clean = brawler_name.lower().replace(' ', '').replace('-', '').replace('.', '').replace('&',
                                                                                                         '')
    brawlers_url = "https://api.brawlify.com/v1/brawlers"
    response = requests.get(brawlers_url)
    if response.status_code != 200:
        print(f"Failed to fetch brawlers from API: {response.status_code}")
        return
    brawlers_data = response.json()['list']

    # Find the brawler in the API data
    for brawler_obj in brawlers_data:
        api_brawler_name = brawler_obj['name'].lower().replace(' ', '').replace('-', '').replace('.',
                                                                                                 '').replace(
            '&', '')
        if api_brawler_name == brawler_name_clean:
            icon_url = brawler_obj['imageUrl2']
            img_response = requests.get(icon_url)
            if img_response.status_code == 200:
                image = Image.open(BytesIO(img_response.content))
                safe_name = os.path.basename(brawler_name_clean).replace('.', '').replace('/', '').replace('\\', '')
                image.save(f"api/assets/brawler_icons/{safe_name}.png")
                print(f"Saved icon for brawler '{brawler_name}'")
            else:
                print(f"Failed to download icon for '{brawler_name}'")
            return
    print(f"Icon not found for brawler '{brawler_name}'")




def get_latest_version():
    url = f'https://{api_base_url}/check_version'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get('version', '')
    else:
        return None

def check_version():
    if api_base_url != "localhost":
        latest_version = get_latest_version()
        if latest_version:
            current_version = load_toml_as_dict("cfg/general_config.toml").get('pyla_version', '')
            if version.parse(current_version) < version.parse(latest_version):
                print(f"Warning: (ignore if you're using early access) You are not using the latest public version of Pyla. \nCheck the discord for the latest download link.")
        else:
            print("Error, couldn't get the version, please check your internet connection or go ask for help in the discord.")


async def async_notify_user(message_type: str | None = None, screenshot: Image = None, details=None) -> bool:
    from discord_notifier import async_notify_user as send_discord_notification
    from telegram_notifier import async_notify_user as send_telegram_notification

    discord_sent = await send_discord_notification(message_type, screenshot=screenshot, details=details)
    telegram_sent = await send_telegram_notification(message_type, screenshot=screenshot, details=details)
    return bool(discord_sent or telegram_sent)
        
def get_discord_link():
    if api_base_url == "localhost":
        return "https://discord.gg/xUusk3fw4A"
    url = f'https://{api_base_url}/get_discord_link'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get('link', '')
    else:
        return None

def get_online_wall_model_hash():
    url = f'https://{api_base_url}/get_wall_model_hash'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get('hash', '')
    else:
        return None

def calculate_sha256(file_path):
    """
    Calculate the SHA-256 hash of a file.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as file:
        # Read the file in chunks to handle large files
        for chunk in iter(lambda: file.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def current_wall_model_is_latest() -> bool:
    """
    Check if the current wall model is the latest version.
    """
    local_hash = calculate_sha256("models/tileDetector.onnx")
    online_hash = get_online_wall_model_hash()
    return local_hash == online_hash

def get_latest_wall_model_file():
    #download the new model to replace the current file and also updates the tile list
    url = f'https://{api_base_url}/get_wall_model_file'
    response = requests.get(url)
    if response.status_code == 200:
        with open("./models/tileDetector.onnx", "wb") as file:
            file.write(response.content)
        print("Downloaded the latest wall model.")
    else:
        print(f"Failed to download the latest wall model. Status code: {response.status_code}")

def get_latest_wall_model_classes():
    url = f'https://{api_base_url}/get_wall_model_classes'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get('classes', [])
    else:
        return None

def update_wall_model_classes():
    classes = get_latest_wall_model_classes()
    current_classes = load_toml_as_dict("cfg/bot_config.toml")["wall_model_classes"]
    if classes:
        if classes != current_classes:
            print("New wall model classes found. Updating...")
            full_config = load_toml_as_dict("cfg/bot_config.toml")
            full_config["wall_model_classes"] = classes
            save_dict_as_toml(full_config, "cfg/bot_config.toml")
            print("Updated the wall model classes.")
    else:
        print("Failed to update the wall model classes, please report this error.")


def cprint(text: str, hex_color: str): #omg color!!!
    try:
        hex_color = hex_color.lstrip("#")
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        print(f"\033[38;2;{r};{g};{b}m{text}\033[0m")
    except Exception:
        print(text)

def get_dpi_scale():
    if sys.platform != "win32":
        return 96
    try:
        return int(ctypes.windll.user32.GetDpiForSystem())
    except (AttributeError, OSError, TypeError, ValueError):
        return 96


def config_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def clamp(x, low, high):
    if x < low:
        return low
    if x > high:
        return high
    return x


JOYSTICK_RADIUS = 75

SAFE_GLOBALS = {
    "math": math,
    "random": random,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "round": round,
    "len": len,
    "range": range,
    "zip": zip,
    "map": map,
    "int": int,
    "float": float,
    "str": str,
    "print": print,
    "time_now": lambda: time.time(),
    "random_int": random.randint,
}


def count_mask_pixels(mask, x1, y1, x2, y2):
    height, width = mask.shape[:2]
    x1 = max(0, min(width, int(x1)))
    x2 = max(0, min(width, int(x2)))
    y1 = max(0, min(height, int(y1)))
    y2 = max(0, min(height, int(y2)))
    if x1 >= x2 or y1 >= y2:
        return 0
    return cv2.countNonZero(mask[y1:y2, x1:x2])


def clean_queue(data):
    from core.integration import clean_queue as _clean_queue

    return _clean_queue(data)


def load_brawler_data():
    try:
        from core.integration import get_queue_path

        queue_path = get_queue_path()
        if not queue_path.exists():
            return []
        with open(queue_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        queue_path = default_queue_path()
        if not os.path.exists(queue_path):
            return []
        with open(queue_path, "r", encoding="utf-8") as handle:
            return json.load(handle)


def interpret_pyla_code(pyla_code, context):
    import traceback

    safe_globals = SAFE_GLOBALS.copy()
    safe_globals.update(context)
    try:
        exec(pyla_code, safe_globals)
    except Exception:
        print("Error executing .pyla code")
        traceback.print_exc()
        return None, safe_globals
    return safe_globals.get("movement", None), safe_globals


def load_all_brawlers_names():
    brawler_names_path = Path(resolve_project_path("cfg/names.json"))
    if not brawler_names_path.exists():
        return {}
    try:
        with open(brawler_names_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"Error loading brawler names from {brawler_names_path}: {exc}")
        return {}


def load_pyla_script(filename):
    import traceback

    script_path = resolve_project_path(os.path.join("playstyles", filename))
    try:
        with open(script_path, "r", encoding="utf-8-sig") as handle:
            metadata_header = handle.readline().strip()
            metadata = json.loads(metadata_header) if metadata_header else {}
            pyla_script = handle.read()
        return metadata, pyla_script
    except FileNotFoundError:
        print(f"Error: The file {script_path} was not found.")
        return {}, ""
    except Exception as exc:
        print(f"An error occurred while loading the .pyla script: {exc}")
        traceback.print_exc()
        return {}, ""


def get_playstyles_list():
    playstyles_dir = resolve_project_path("playstyles")
    playstyles = []
    if os.path.isdir(playstyles_dir):
        for filename in os.listdir(playstyles_dir):
            if filename.endswith(".pyla"):
                metadata, _ = load_pyla_script(filename)
                playstyles.append({"filename": filename, "metadata": metadata})
    return playstyles


def load_default_pyla_script():
    config = load_toml_as_dict("cfg/bot_config.toml")
    return load_pyla_script(config.get("current_playstyle", "team_showdown.pyla"))


def hash_playstyle(playstyle_info):
    return hashlib.sha256(str(playstyle_info).encode("utf-8")).hexdigest()


def _map_notification_event_type(message_type: str) -> str:
    if message_type == "brawler_goal":
        return "brawler_complete"
    return message_type


def _notification_message(message_type: str, stage_manager) -> str:
    queue = getattr(stage_manager, "brawlers_pick_data", None) or []
    current = queue[0] if queue else {}
    brawler = str(current.get("brawler", "") or "brawler")
    messages = {
        "completed": "Pyla has completed all its targets!",
        "bot_is_stuck": "Your bot is currently stuck; attempted to restart Brawl Stars.",
        "brawler_goal": f"Pyla completed brawler goal for {brawler}!",
        "regular_minutes_ping": "Pyla is still running.",
        "regular_matches_ping": "Pyla is still running.",
        "bot_failed_brawler_selection": (
            f"Pyla failed to select the brawler {brawler} after multiple attempts. "
            "Try changing the OCR Scale Down setting or select it manually and restart."
        ),
    }
    return messages.get(message_type, "Notification")


def build_match_notification_details(stage_manager, match_record: dict) -> dict:
    details = dict(match_record or {})
    queue = getattr(stage_manager, "brawlers_pick_data", None) or []
    trophy_observer = getattr(stage_manager, "Trophy_observer", None)
    if queue:
        current = queue[0]
        details.setdefault("brawler", current.get("brawler", ""))
        details.setdefault("target", current.get("push_until", ""))
        details["brawlers_left"] = len(queue)
        if trophy_observer is not None:
            details.setdefault("trophies", trophy_observer.current_trophies)
            details.setdefault("wins", trophy_observer.current_wins)
            details.setdefault("win_streak", trophy_observer.win_streak)
        if len(queue) > 1:
            details.setdefault("next_up", queue[1].get("brawler", ""))
    try:
        from gui.instance_config import instance_context_for_notifications

        details.update(instance_context_for_notifications())
    except Exception:
        pass
    return details


def build_notification_details(message_type, stage_manager) -> dict:
    details = {"message": _notification_message(message_type, stage_manager)}
    queue = getattr(stage_manager, "brawlers_pick_data", None) or []
    trophy_observer = getattr(stage_manager, "Trophy_observer", None)
    if queue:
        current = queue[0]
        details["brawler"] = current.get("brawler", "")
        details["target"] = current.get("push_until", "")
        details["brawlers_left"] = len(queue)
        if trophy_observer is not None:
            details["trophies"] = trophy_observer.current_trophies
            details["wins"] = trophy_observer.current_wins
            details["win_streak"] = trophy_observer.win_streak
        if len(queue) > 1:
            details["next_up"] = queue[1].get("brawler", "")
            try:
                from gui.remote_formatting import format_queue_preview_names

                preview = format_queue_preview_names(queue[1:3])
                if preview:
                    details["queue_preview"] = preview
            except Exception:
                pass
    try:
        from gui.instance_config import instance_context_for_notifications

        details.update(instance_context_for_notifications())
    except Exception:
        pass
    return details


def notify_user(message_type, screenshot, stage_manager, *, match_record=None) -> None:
    import asyncio

    if isinstance(stage_manager, dict):
        details = stage_manager
        event_type = message_type
    elif message_type == "match" and match_record is not None:
        details = build_match_notification_details(stage_manager, match_record)
        event_type = "match"
    else:
        details = build_notification_details(message_type, stage_manager)
        event_type = _map_notification_event_type(message_type)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(async_notify_user(event_type, screenshot, details=details))
            return
    except RuntimeError:
        pass
    asyncio.run(async_notify_user(event_type, screenshot, details=details))


def debug_beep():
    import threading
    import winsound

    threading.Thread(target=lambda: winsound.Beep(1200, 500), daemon=True).start()

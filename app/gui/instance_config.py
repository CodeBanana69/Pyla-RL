from __future__ import annotations

"""Per-instance paths and multi-instance registry.

Data tiers:
- cfg/*.toml — shipped defaults (versioned)
- cfg/*.local.toml — machine secrets (gitignored)
- instances/<id>/ — per-bot farm plan and overrides (runtime)
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from utils import (
    DEFAULT_QUEUE_PATH,
    LEGACY_QUEUE_PATH,
    default_queue_path,
    load_toml_as_dict,
    resolve_project_path,
    save_dict_as_toml,
)


INSTANCES_CONFIG_PATH = "cfg/instances.toml"
INSTANCES_ROOT = "instances"
MANIFEST_DIR = "logs/instances"
REPLIES_DIR = "logs/instances/replies"
INSTANCE_LOCAL_FILENAME = "instance.local.toml"

_active_instance_id: str | None = None

EMULATOR_PORT_DEFAULTS = {
    "ldplayer": 5555,
    "mumu": 16384,
}

LDPLAYER_PORTS = {
    5554: 0,
    5555: 0,
    5557: 1,
    5559: 2,
    5561: 3,
    5563: 4,
    5565: 5,
    5567: 6,
    5569: 7,
}
MUMU_PORTS = {16384: 0, 16416: 1, 16448: 2}

COMMON_LDPLAYER_CONSOLES = [
    r"C:\LDPlayer\LDPlayer9\dnconsole.exe",
    r"C:\LDPlayer\LDPlayer4.0\dnconsole.exe",
    r"C:\Program Files\LDPlayer\LDPlayer9\dnconsole.exe",
    r"C:\Program Files\LDPlayer\LDPlayer4.0\dnconsole.exe",
    r"C:\Program Files (x86)\LDPlayer\LDPlayer9\dnconsole.exe",
    r"C:\Program Files (x86)\LDPlayer\LDPlayer4.0\dnconsole.exe",
]

COMMON_MUMU_MANAGERS = [
    r"C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe",
    r"C:\Program Files (x86)\Netease\MuMuPlayer\nx_main\MuMuManager.exe",
]


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", str(value or "").strip().lower())
    return cleaned.strip("-") or "instance"


def set_active_instance(instance_id: str | None) -> None:
    global _active_instance_id
    instance_id = str(instance_id or "").strip() or None
    _active_instance_id = instance_id
    if instance_id:
        os.environ["PYLA_INSTANCE_ID"] = instance_id
    else:
        os.environ.pop("PYLA_INSTANCE_ID", None)


def get_active_instance_id() -> str | None:
    if _active_instance_id:
        return _active_instance_id
    env_value = os.environ.get("PYLA_INSTANCE_ID", "").strip()
    return env_value or None


def is_multi_instance_enabled() -> bool:
    data = load_instances_config()
    return _to_bool(data.get("multi_instance", {}).get("enabled"))


def is_multi_instance_worker() -> bool:
    return bool(get_active_instance_id()) and is_multi_instance_enabled()


def _to_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "yes", "true", "on"}


def default_instances_config() -> dict[str, Any]:
    return {
        "multi_instance": {
            "enabled": False,
            "default_instance": "",
            "setup_wizard_dismissed": False,
            "auto_restart_crashed": False,
        },
        "instances": {},
    }


def load_instances_config() -> dict[str, Any]:
    path = Path(resolve_project_path(INSTANCES_CONFIG_PATH))
    if not path.exists():
        return default_instances_config()
    data = dict(load_toml_as_dict(INSTANCES_CONFIG_PATH))
    data.setdefault("multi_instance", {})
    data.setdefault("instances", {})
    if not isinstance(data["instances"], dict):
        data["instances"] = {}
    return data


def save_instances_config(data: dict[str, Any]) -> str:
    normalized = default_instances_config()
    normalized["multi_instance"].update(data.get("multi_instance") or {})
    instances = data.get("instances") or {}
    normalized["instances"] = instances if isinstance(instances, dict) else {}
    path = save_dict_as_toml(normalized, INSTANCES_CONFIG_PATH)
    return path


def set_multi_instance_enabled(enabled: bool) -> dict[str, Any]:
    data = load_instances_config()
    data["multi_instance"]["enabled"] = bool(enabled)
    save_instances_config(data)
    return data


def set_multi_instance_setup_dismissed(dismissed: bool = True) -> dict[str, Any]:
    data = load_instances_config()
    data["multi_instance"]["setup_wizard_dismissed"] = bool(dismissed)
    save_instances_config(data)
    return data


def is_multi_instance_setup_dismissed() -> bool:
    data = load_instances_config()
    return _to_bool(data.get("multi_instance", {}).get("setup_wizard_dismissed"))


def is_auto_restart_crashed_enabled() -> bool:
    data = load_instances_config()
    return _to_bool(data.get("multi_instance", {}).get("auto_restart_crashed"))


def set_auto_restart_crashed(enabled: bool) -> dict[str, Any]:
    data = load_instances_config()
    data["multi_instance"]["auto_restart_crashed"] = bool(enabled)
    save_instances_config(data)
    return data


def normalize_emulator_name(value: str) -> str:
    text = str(value or "ldplayer").strip().lower()
    if text in {"mumu", "mumuplayer"}:
        return "mumu"
    return "ldplayer"


def emulator_display_name(value: str) -> str:
    return "MuMu" if normalize_emulator_name(value) == "mumu" else "LDPlayer"


def default_port_for_emulator(emulator: str) -> int:
    return EMULATOR_PORT_DEFAULTS.get(normalize_emulator_name(emulator), 5555)


def infer_profile_index(emulator: str, port: int) -> str:
    emulator = normalize_emulator_name(emulator)
    port = int(port)
    if emulator == "mumu":
        if port in MUMU_PORTS:
            return str(MUMU_PORTS[port])
        if port >= 16384 and (port - 16384) % 32 == 0:
            return str((port - 16384) // 32)
        return "0"
    if port in LDPLAYER_PORTS:
        return str(LDPLAYER_PORTS[port])
    if port >= 5557 and (port - 5555) % 2 == 0:
        return str((port - 5555) // 2)
    return "0"


def port_for_profile_index(emulator: str, profile_index: int) -> int:
    emulator = normalize_emulator_name(emulator)
    profile_index = int(profile_index)
    if emulator == "mumu":
        for port, index in MUMU_PORTS.items():
            if index == profile_index:
                return port
        return 16384 + (32 * profile_index)
    return 5555 + (2 * profile_index)


def _find_existing_path(paths: list[str]) -> str:
    for path in paths:
        if Path(path).exists():
            return path
    return ""


def _clean_instance_name(value: str) -> str:
    return str(value or "").strip().strip("\"'")


def _instance_name_matches(candidate: str, wanted: str) -> bool:
    candidate = _clean_instance_name(candidate).lower()
    wanted = _clean_instance_name(wanted).lower()
    return candidate == wanted or candidate.replace(" ", "") == wanted.replace(" ", "")


def _ldplayer_console_path(general: dict[str, Any] | None = None) -> str:
    general = general or load_toml_as_dict("cfg/general_config.toml")
    configured = str(general.get("ldplayer_console_path", "")).strip()
    if configured:
        return configured
    return _find_existing_path(COMMON_LDPLAYER_CONSOLES)


def _mumu_manager_path(general: dict[str, Any] | None = None) -> str:
    general = general or load_toml_as_dict("cfg/general_config.toml")
    configured = str(general.get("mumu_manager_path", "")).strip()
    if configured:
        return configured
    return _find_existing_path(COMMON_MUMU_MANAGERS)


def list_ldplayer_instances(general: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    console = _ldplayer_console_path(general)
    if not console:
        return []
    try:
        completed = subprocess.run(
            [console, "list2"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return []
    if completed.returncode != 0:
        return []

    instances = []
    for line in (completed.stdout or "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            index = int(parts[0])
        except ValueError:
            continue
        name = parts[1] or f"LDPlayer {index}"
        instances.append({
            "name": name,
            "index": index,
            "adb_port": port_for_profile_index("ldplayer", index),
        })
    return instances


def list_mumu_instances(general: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    manager = _mumu_manager_path(general)
    if not manager:
        return []
    try:
        completed = subprocess.run(
            [manager, "info", "--vmindex", "all"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return []
    if completed.returncode != 0:
        return []
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return []

    instances = []
    for _, profile in payload.items():
        if not isinstance(profile, dict):
            continue
        try:
            index = int(profile.get("index", 0))
        except (TypeError, ValueError):
            continue
        try:
            adb_port = int(profile.get("adb_port", 0) or 0)
        except (TypeError, ValueError):
            adb_port = 0
        instances.append({
            "name": str(profile.get("name", "") or f"MuMu {index}"),
            "index": index,
            "adb_port": adb_port or port_for_profile_index("mumu", index),
        })
    return instances


def list_available_emulator_instances() -> list[dict[str, Any]]:
    available = []
    for emulator, items in (
        ("ldplayer", list_ldplayer_instances()),
        ("mumu", list_mumu_instances()),
    ):
        for item in items:
            available.append({
                "emulator": emulator,
                "display_emulator": emulator_display_name(emulator),
                "name": str(item.get("name", "")),
                "index": int(item.get("index", 0)),
                "adb_port": int(item.get("adb_port", port_for_profile_index(emulator, int(item.get("index", 0))))),
            })
    available.sort(key=lambda item: (item["display_emulator"], item["index"], item["name"].lower()))
    return available


def resolve_emulator_instance(emulator: str, instance_name: str) -> dict[str, Any]:
    emulator = normalize_emulator_name(emulator)
    instance_name = _clean_instance_name(instance_name)
    if not instance_name:
        raise ValueError("Type the emulator instance name first.")

    if ":" in instance_name:
        try:
            port = int(instance_name.rsplit(":", 1)[1])
        except ValueError:
            port = 0
        if port:
            return {
                "name": instance_name,
                "emulator": emulator,
                "emulator_port": port,
                "emulator_profile_index": infer_profile_index(emulator, port),
            }

    if instance_name.lower().startswith("emulator-"):
        try:
            port = int(instance_name.rsplit("-", 1)[1])
        except ValueError:
            port = 0
        if port:
            return {
                "name": instance_name,
                "emulator": emulator,
                "emulator_port": port,
                "emulator_profile_index": infer_profile_index(emulator, port),
            }

    if instance_name.isdigit():
        index = int(instance_name)
        return {
            "name": f"{emulator_display_name(emulator)} {index}",
            "emulator": emulator,
            "emulator_port": port_for_profile_index(emulator, index),
            "emulator_profile_index": str(index),
        }

    instances = list_mumu_instances() if emulator == "mumu" else list_ldplayer_instances()
    for item in instances:
        if _instance_name_matches(item.get("name", ""), instance_name):
            index = int(item["index"])
            return {
                "name": str(item["name"]),
                "emulator": emulator,
                "emulator_port": int(item["adb_port"]),
                "emulator_profile_index": str(index),
            }

    raise ValueError(
        f"Could not find {emulator_display_name(emulator)} instance '{instance_name}'. "
        "Start the emulator manager once or type its numeric index/ADB serial instead."
    )


def instance_local_path(instance_id: str) -> Path:
    return Path(resolve_project_path(INSTANCES_ROOT)) / _slugify(instance_id) / INSTANCE_LOCAL_FILENAME


def load_instance_local_settings(instance_id: str) -> dict[str, Any]:
    path = instance_local_path(instance_id)
    if not path.exists():
        return {}
    data = load_toml_as_dict(str(path))
    return data if isinstance(data, dict) else {}


def save_instance_local_settings(instance_id: str, settings: dict[str, Any]) -> str:
    instance_id = _slugify(instance_id)
    ensure_instance_dirs(instance_id)
    path = instance_local_path(instance_id)
    normalized = {
        "player": dict(settings.get("player") or {}),
        "discord": dict(settings.get("discord") or {}),
        "telegram": dict(settings.get("telegram") or {}),
    }
    rel_path = f"{INSTANCES_ROOT}/{instance_id}/{INSTANCE_LOCAL_FILENAME}"
    return save_dict_as_toml(normalized, rel_path)


def normalize_instance_profile(instance_id: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = dict(profile or {})
    instance_id = _slugify(instance_id or profile.get("id", ""))
    emulator = normalize_emulator_name(profile.get("emulator", "ldplayer"))
    port = int(profile.get("emulator_port", default_port_for_emulator(emulator)) or default_port_for_emulator(emulator))
    profile_index = str(profile.get("emulator_profile_index") or infer_profile_index(emulator, port))
    instance_dir = Path(INSTANCES_ROOT) / instance_id
    queue_path = str(profile.get("queue_path") or (instance_dir / "latest_brawler_data.json"))
    local = load_instance_local_settings(instance_id)
    player_tag = str(
        profile.get("player_tag")
        or (local.get("player") or {}).get("tag")
        or ""
    ).strip()
    return {
        "id": instance_id,
        "name": str(profile.get("name") or instance_id).strip() or instance_id,
        "enabled": _to_bool(profile.get("enabled", True)),
        "emulator": emulator,
        "emulator_port": port,
        "emulator_profile_index": profile_index,
        "emulator_instance_name": str(profile.get("emulator_instance_name") or profile.get("name") or "").strip(),
        "player_tag": player_tag,
        "queue_path": queue_path.replace("\\", "/"),
    }


def list_instance_profiles() -> list[dict[str, Any]]:
    data = load_instances_config()
    profiles = []
    for instance_id, profile in sorted((data.get("instances") or {}).items()):
        if not isinstance(profile, dict):
            continue
        profiles.append(normalize_instance_profile(instance_id, profile))
    return profiles


def get_instance_profile(instance_id: str | None) -> dict[str, Any] | None:
    instance_id = _slugify(instance_id or "")
    if not instance_id:
        return None
    data = load_instances_config()
    profile = (data.get("instances") or {}).get(instance_id)
    if not isinstance(profile, dict):
        return None
    return normalize_instance_profile(instance_id, profile)


def upsert_instance_profile(instance_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    data = load_instances_config()
    instance_id = _slugify(instance_id or profile.get("id", ""))
    normalized = normalize_instance_profile(instance_id, profile)
    collision = find_port_collision(instance_id, normalized["emulator_port"])
    if collision:
        raise ValueError(
            f"Port {normalized['emulator_port']} is already used by instance '{collision}'."
        )
    instances = dict(data.get("instances") or {})
    instances[instance_id] = {
        "name": normalized["name"],
        "enabled": normalized["enabled"],
        "emulator": normalized["emulator"],
        "emulator_port": normalized["emulator_port"],
        "emulator_profile_index": normalized["emulator_profile_index"],
        "emulator_instance_name": normalized["emulator_instance_name"],
        "player_tag": normalized["player_tag"],
        "queue_path": normalized["queue_path"],
    }
    data["instances"] = instances
    save_instances_config(data)
    ensure_instance_dirs(instance_id)
    if normalized["player_tag"]:
        local = load_instance_local_settings(instance_id)
        local.setdefault("player", {})["tag"] = normalized["player_tag"]
        save_instance_local_settings(instance_id, local)
    return normalized


def set_instance_player_tag(instance_id: str, player_tag: str) -> dict[str, Any]:
    profile = get_instance_profile(instance_id)
    if not profile:
        raise ValueError(f"Unknown instance '{instance_id}'.")
    profile["player_tag"] = str(player_tag or "").strip()
    local = load_instance_local_settings(instance_id)
    local.setdefault("player", {})["tag"] = profile["player_tag"]
    save_instance_local_settings(instance_id, local)
    return upsert_instance_profile(instance_id, profile)


def delete_instance_profile(instance_id: str) -> bool:
    data = load_instances_config()
    instances = dict(data.get("instances") or {})
    instance_id = _slugify(instance_id)
    if instance_id not in instances:
        return False
    instances.pop(instance_id, None)
    data["instances"] = instances
    save_instances_config(data)
    return True


def ensure_instance_dirs(instance_id: str) -> Path:
    instance_id = _slugify(instance_id)
    root = Path(resolve_project_path(INSTANCES_ROOT)) / instance_id
    root.mkdir(parents=True, exist_ok=True)
    queue_path = root / "latest_brawler_data.json"
    if not queue_path.exists():
        queue_path.write_text("[]", encoding="utf-8")
    local_path = root / INSTANCE_LOCAL_FILENAME
    if not local_path.exists():
        local_path.write_text("", encoding="utf-8")
    return root


def get_queue_path(instance_id: str | None = None) -> Path:
    instance_id = instance_id or get_active_instance_id()
    if instance_id and is_multi_instance_enabled():
        profile = get_instance_profile(instance_id)
        if profile:
            return Path(resolve_project_path(profile["queue_path"]))
        return Path(resolve_project_path(INSTANCES_ROOT)) / _slugify(instance_id) / "latest_brawler_data.json"
    return Path(default_queue_path())


def queue_has_data(path: Path | str | None = None, instance_id: str | None = None) -> bool:
    queue_path = Path(path) if path else get_queue_path(instance_id)
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, list) and bool(data)


def queue_brawler_count(instance_id: str | None = None) -> int:
    queue_path = get_queue_path(instance_id)
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return len(data) if isinstance(data, list) else 0


def copy_queue(from_instance_id: str | None, to_instance_id: str) -> bool:
    source = get_queue_path(from_instance_id)
    target = get_queue_path(to_instance_id)
    if not source.exists() or not queue_has_data(source):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return True


def find_port_collision(instance_id: str, port: int) -> str | None:
    target_port = int(port)
    for profile in list_instance_profiles():
        if profile["id"] == _slugify(instance_id):
            continue
        if int(profile.get("emulator_port", 0) or 0) == target_port:
            return profile["id"]
    return None


def used_emulator_ports(instance_id: str | None = None) -> set[int]:
    skip = _slugify(instance_id or "")
    ports: set[int] = set()
    for profile in list_instance_profiles():
        if profile["id"] == skip:
            continue
        ports.add(int(profile.get("emulator_port", 0) or 0))
    ports.discard(0)
    return ports


def next_free_emulator_port(emulator: str, instance_id: str | None = None) -> int:
    from gui.emulator_adb import ports_for_emulator

    used = used_emulator_ports(instance_id)
    for port in ports_for_emulator(emulator_display_name(emulator)):
        if port not in used:
            return port
    raise ValueError(f"No free ADB port available for {emulator_display_name(emulator)}.")


def suggest_instance_id(emulator: str, index: int, name: str = "") -> str:
    base = _slugify(name) if name else f"{normalize_emulator_name(emulator)}-{index}"
    existing = {profile["id"] for profile in list_instance_profiles()}
    if base not in existing:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing:
        suffix += 1
    return f"{base}-{suffix}"


def list_unassigned_emulator_instances() -> list[dict[str, Any]]:
    used_ports = used_emulator_ports()
    unassigned = []
    for item in list_available_emulator_instances():
        if int(item.get("adb_port", 0) or 0) in used_ports:
            continue
        unassigned.append(item)
    return unassigned


def quick_add_emulator_instances(
    items: list[dict[str, Any]] | None = None,
    *,
    copy_farm_plan_from: str | None = "default",
) -> list[dict[str, Any]]:
    created = []
    targets = items if items is not None else list_unassigned_emulator_instances()
    for item in targets:
        emulator = normalize_emulator_name(item.get("emulator", "ldplayer"))
        port = int(item.get("adb_port", 0) or port_for_profile_index(emulator, int(item.get("index", 0))))
        if find_port_collision("", port):
            continue
        name = str(item.get("name", "") or f"{emulator_display_name(emulator)} {item.get('index', 0)}")
        instance_id = suggest_instance_id(emulator, int(item.get("index", 0)), name)
        profile = upsert_instance_profile(instance_id, {
            "name": name,
            "enabled": True,
            "emulator": emulator,
            "emulator_port": port,
            "emulator_profile_index": str(item.get("index", infer_profile_index(emulator, port))),
            "emulator_instance_name": name,
        })
        if copy_farm_plan_from:
            copy_queue(copy_farm_plan_from, profile["id"])
        created.append(profile)
    return created


def compute_instance_readiness(instance_id: str) -> dict[str, Any]:
    profile = get_instance_profile(instance_id)
    if not profile:
        return {"status": "unknown", "message": f"Unknown instance '{instance_id}'."}

    collision = find_port_collision(instance_id, profile["emulator_port"])
    if collision:
        return {
            "status": "port_conflict",
            "message": f"Port {profile['emulator_port']} is used by '{collision}'.",
            "collision_with": collision,
        }

    if not int(profile.get("emulator_port", 0) or 0):
        return {"status": "no_emulator", "message": "No emulator port assigned."}

    if not queue_has_data(instance_id=instance_id):
        default_queue = Path(default_queue_path())
        if default_queue.exists() and queue_has_data(default_queue):
            return {
                "status": "needs_farm_plan",
                "message": "No farm plan yet. Copy from Default or edit the farm plan.",
                "can_copy_default": True,
            }
        return {
            "status": "needs_farm_plan",
            "message": "No farm plan yet. Add brawlers on the Farm Plan tab.",
            "can_copy_default": False,
        }

    return {
        "status": "ready",
        "message": "Ready to start.",
        "queue_count": queue_brawler_count(instance_id),
    }


def get_default_instance_id() -> str:
    data = load_instances_config()
    default_id = _slugify(str(data.get("multi_instance", {}).get("default_instance", "") or ""))
    if default_id:
        return default_id
    profiles = list_instance_profiles()
    return profiles[0]["id"] if profiles else "default"


def _repoint_default_instance_if_missing(data: dict[str, Any]) -> dict[str, Any]:
    default_id = _slugify(str(data.get("multi_instance", {}).get("default_instance", "") or ""))
    instances = data.get("instances") or {}
    if not default_id or default_id in instances:
        return data
    profiles = list_instance_profiles()
    if not profiles:
        return data
    data = load_instances_config()
    data["multi_instance"]["default_instance"] = profiles[0]["id"]
    save_instances_config(data)
    return load_instances_config()


def apply_instance_overrides(instance_id: str | None = None) -> dict[str, Any] | None:
    instance_id = instance_id or get_active_instance_id()
    profile = get_instance_profile(instance_id)
    if not profile:
        return None

    from utils import cached_toml

    general_path = resolve_project_path("cfg/general_config.toml")
    general = dict(load_toml_as_dict("cfg/general_config.toml"))
    general["current_emulator"] = emulator_display_name(profile["emulator"])
    general["emulator_port"] = int(profile["emulator_port"])
    general["emulator_profile_index"] = str(profile["emulator_profile_index"])
    general["emulator_instance_name"] = str(profile.get("emulator_instance_name", ""))
    cached_toml[general_path] = general

    player_tag = str(profile.get("player_tag", "")).strip()
    if player_tag:
        api_path = resolve_project_path("cfg/brawl_stars_api.toml")
        api_config = dict(load_toml_as_dict("cfg/brawl_stars_api.toml"))
        api_config["player_tag"] = player_tag
        cached_toml[api_path] = api_config
    return profile


def migrate_single_instance_to_default() -> dict[str, Any]:
    data = load_instances_config()
    if data.get("instances"):
        return data

    general = load_toml_as_dict("cfg/general_config.toml")
    emulator = normalize_emulator_name(general.get("current_emulator", "LDPlayer"))
    port = int(general.get("emulator_port", default_port_for_emulator(emulator)) or default_port_for_emulator(emulator))
    api_config = load_toml_as_dict("cfg/brawl_stars_api.toml")
    profile = upsert_instance_profile("default", {
        "name": "Default Instance",
        "enabled": True,
        "emulator": emulator,
        "emulator_port": port,
        "emulator_profile_index": general.get("emulator_profile_index", infer_profile_index(emulator, port)),
        "player_tag": api_config.get("player_tag", ""),
    })

    source_queue = Path(default_queue_path())
    if not source_queue.exists():
        source_queue = Path(resolve_project_path(LEGACY_QUEUE_PATH))
    target_queue = Path(profile["queue_path"])
    if source_queue.exists() and not target_queue.exists():
        target_queue.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_queue, target_queue)

    data = load_instances_config()
    data["multi_instance"]["default_instance"] = profile["id"]
    save_instances_config(data)
    return data


def ensure_multi_instance_profiles() -> dict[str, Any]:
    data = load_instances_config()
    if not is_multi_instance_enabled():
        return data

    instances = data.get("instances") or {}
    if not instances:
        return migrate_single_instance_to_default()

    default_id = _slugify(str(data.get("multi_instance", {}).get("default_instance", "") or ""))
    if default_id and default_id not in instances:
        general = load_toml_as_dict("cfg/general_config.toml")
        emulator = normalize_emulator_name(general.get("current_emulator", "LDPlayer"))
        port = int(
            general.get("emulator_port", default_port_for_emulator(emulator))
            or default_port_for_emulator(emulator)
        )
        if find_port_collision(default_id, port):
            try:
                port = next_free_emulator_port(emulator, instance_id=default_id)
            except ValueError:
                return _repoint_default_instance_if_missing(data)
        try:
            upsert_instance_profile(default_id, {
                "name": "Default Instance" if default_id == "default" else default_id.replace("-", " ").title(),
                "enabled": True,
                "emulator": emulator,
                "emulator_port": port,
                "emulator_profile_index": general.get(
                    "emulator_profile_index",
                    infer_profile_index(emulator, port),
                ),
            })
        except ValueError:
            return _repoint_default_instance_if_missing(data)
        data = load_instances_config()
        data["multi_instance"]["default_instance"] = default_id
        save_instances_config(data)
        return load_instances_config()
    return data


def instance_context_for_notifications(instance_id: str | None = None) -> dict[str, str]:
    profile = get_instance_profile(instance_id or get_active_instance_id())
    if not profile:
        return {}
    return {
        "instance_id": profile["id"],
        "instance_name": profile["name"],
    }


def legacy_instance_profile_secrets(instance_id: str) -> dict[str, Any]:
    """Read fork-style per-instance secrets stored on instances.toml profile sections."""
    data = load_instances_config()
    profile = (data.get("instances") or {}).get(_slugify(instance_id))
    if not isinstance(profile, dict):
        return {}
    return profile

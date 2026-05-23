from __future__ import annotations

"""Per-instance paths and multi-instance registry.

Data tiers:
- cfg/*.toml — shipped defaults (versioned)
- cfg/*.local.toml — machine secrets (gitignored)
- instances/<id>/ — per-bot farm plan and overrides (runtime)
"""
import os
import re
from pathlib import Path
from typing import Any

from utils import load_toml_as_dict, resolve_project_path, save_dict_as_toml


INSTANCES_CONFIG_PATH = "cfg/instances.toml"
INSTANCES_ROOT = "instances"
MANIFEST_DIR = "logs/instances"
REPLIES_DIR = "logs/instances/replies"

_active_instance_id: str | None = None

EMULATOR_PORT_DEFAULTS = {
    "ldplayer": 5555,
    "mumu": 16384,
}

LDPLAYER_PORTS = {5555: 0, 5557: 1, 5559: 2}
MUMU_PORTS = {16384: 0, 16416: 1, 16448: 2}


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
    if emulator == "mumu":
        return str(MUMU_PORTS.get(int(port), 0))
    return str(LDPLAYER_PORTS.get(int(port), 0))


def normalize_instance_profile(instance_id: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = dict(profile or {})
    instance_id = _slugify(instance_id or profile.get("id", ""))
    emulator = normalize_emulator_name(profile.get("emulator", "ldplayer"))
    port = int(profile.get("emulator_port", default_port_for_emulator(emulator)) or default_port_for_emulator(emulator))
    profile_index = str(profile.get("emulator_profile_index") or infer_profile_index(emulator, port))
    instance_dir = Path(INSTANCES_ROOT) / instance_id
    queue_path = str(profile.get("queue_path") or (instance_dir / "latest_brawler_data.json"))
    return {
        "id": instance_id,
        "name": str(profile.get("name") or instance_id).strip() or instance_id,
        "enabled": _to_bool(profile.get("enabled", True)),
        "emulator": emulator,
        "emulator_port": port,
        "emulator_profile_index": profile_index,
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
        "queue_path": normalized["queue_path"],
    }
    data["instances"] = instances
    save_instances_config(data)
    ensure_instance_dirs(instance_id)
    return normalized


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
    root = Path(INSTANCES_ROOT) / instance_id
    root.mkdir(parents=True, exist_ok=True)
    queue_path = root / "latest_brawler_data.json"
    if not queue_path.exists():
        queue_path.write_text("[]", encoding="utf-8")
    local_path = root / "instance.local.toml"
    if not local_path.exists():
        local_path.write_text("", encoding="utf-8")
    return root


def get_queue_path(instance_id: str | None = None) -> Path:
    instance_id = instance_id or get_active_instance_id()
    if instance_id and is_multi_instance_enabled():
        profile = get_instance_profile(instance_id)
        if profile:
            return Path(profile["queue_path"])
        return Path(INSTANCES_ROOT) / _slugify(instance_id) / "latest_brawler_data.json"
    return Path("latest_brawler_data.json")


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
    cached_toml[general_path] = general
    return profile


def migrate_single_instance_to_default() -> dict[str, Any]:
    data = load_instances_config()
    if data.get("instances"):
        return data

    general = load_toml_as_dict("cfg/general_config.toml")
    emulator = normalize_emulator_name(general.get("current_emulator", "LDPlayer"))
    port = int(general.get("emulator_port", default_port_for_emulator(emulator)) or default_port_for_emulator(emulator))
    profile = upsert_instance_profile("default", {
        "name": "Default Instance",
        "enabled": True,
        "emulator": emulator,
        "emulator_port": port,
        "emulator_profile_index": general.get("emulator_profile_index", infer_profile_index(emulator, port)),
    })

    source_queue = Path("latest_brawler_data.json")
    target_queue = Path(profile["queue_path"])
    if source_queue.exists() and not target_queue.exists():
        target_queue.parent.mkdir(parents=True, exist_ok=True)
        target_queue.write_text(source_queue.read_text(encoding="utf-8"), encoding="utf-8")

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

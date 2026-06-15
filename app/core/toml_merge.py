"""Shared flat-TOML merge and duplicate-key repair helpers."""

from __future__ import annotations

import re

_TOML_KEY_PATTERN = re.compile(
    r'^(\s*)("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z0-9_\-]+)(\s*=\s*)(.*)$'
)


def split_toml_value_and_comment(raw_value: str) -> tuple[str, str]:
    in_single_quote = False
    in_double_quote = False
    escaped = False

    for index, char in enumerate(raw_value):
        if escaped:
            escaped = False
            continue
        if in_double_quote and char == "\\":
            escaped = True
            continue
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            continue
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            continue
        if char == "#" and not in_single_quote and not in_double_quote:
            return raw_value[:index].rstrip(), raw_value[index:]
    return raw_value.rstrip(), ""


def clean_preserved_toml_value(key: str, value: str) -> str:
    if key != "player_tag":
        return value
    stripped = value.strip()
    if len(stripped) < 2 or stripped[0] not in ('"', "'") or stripped[-1] != stripped[0]:
        return value
    inner = stripped[1:-1]
    placeholder = "#YOURTAG"
    if inner.upper().endswith(placeholder) and inner.upper() != placeholder:
        return f"{stripped[0]}{inner[:-len(placeholder)]}{stripped[0]}"
    return value


def normalize_toml_key(key: str) -> str:
    key = key.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in ('"', "'"):
        key = key[1:-1]
    stripped = key.replace("\\ufeff", "").lstrip("\ufeff")
    if stripped == "personal_webhook":
        return "personal_webhook"
    return stripped or key


def parse_simple_toml(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        raw_key, raw_value = stripped.split("=", 1)
        key = normalize_toml_key(raw_key)
        raw_value = split_toml_value_and_comment(raw_value.strip())[0].strip()
        if key:
            values[key] = clean_preserved_toml_value(key, raw_value)
    return values


def dedupe_toml_text(text: str) -> str:
    """Keep the first assignment for each normalized key."""
    output: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = _TOML_KEY_PATTERN.match(line)
        if not match:
            output.append(line)
            continue
        key = normalize_toml_key(match.group(2))
        if key in seen:
            continue
        seen.add(key)
        output.append(line)
    if not output:
        return ""
    result = "\n".join(output)
    if text.endswith("\n"):
        result += "\n"
    return result


def merge_toml_text(new_text: str, old_text: str) -> str:
    old_values = parse_simple_toml(old_text)
    new_values = parse_simple_toml(new_text)
    merged_lines: list[str] = []
    used_keys: set[str] = set()

    for line in new_text.splitlines():
        match = _TOML_KEY_PATTERN.match(line)
        if not match:
            merged_lines.append(line)
            continue
        prefix, raw_key, equals, new_value = match.groups()
        key = normalize_toml_key(raw_key)
        _, suffix = split_toml_value_and_comment(new_value)
        if key in old_values:
            separator = " " if suffix and not suffix.startswith(" ") else ""
            merged_lines.append(f"{prefix}{key}{equals}{old_values[key]}{separator}{suffix}")
            used_keys.add(key)
        else:
            merged_lines.append(line)
            used_keys.add(key)

    merged_body = "\n".join(merged_lines)
    present_after_merge = set(parse_simple_toml(merged_body).keys())
    missing_user_keys = [key for key in old_values if key not in present_after_merge]
    if missing_user_keys:
        if merged_lines and merged_lines[-1].strip():
            merged_lines.append("")
        merged_lines.append("# Kept from your previous config")
        for key in missing_user_keys:
            merged_lines.append(f"{key} = {old_values[key]}")

    return dedupe_toml_text("\n".join(merged_lines).rstrip() + "\n")


def repair_unquoted_windows_paths(text: str) -> str:
    """Quote bare Windows paths so TOML parsers do not treat backslashes as escapes."""
    output: list[str] = []
    changed = False
    for line in text.splitlines():
        match = _TOML_KEY_PATTERN.match(line)
        if not match:
            output.append(line)
            continue
        prefix, raw_key, equals, raw_value = match.groups()
        value, comment = split_toml_value_and_comment(raw_value.strip())
        if not value or value[0] in ('"', "'"):
            output.append(line)
            continue
        needs_quotes = "\\" in value or (
            len(value) >= 2 and value[1] == ":" and value[0].isalpha()
        )
        if not needs_quotes:
            output.append(line)
            continue
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        suffix = f" {comment}" if comment and not comment.startswith(" ") else comment
        key = normalize_toml_key(raw_key)
        output.append(f"{prefix}{key}{equals}\"{escaped}\"{suffix}")
        changed = True
    if not changed:
        return text
    result = "\n".join(output)
    if text.endswith("\n"):
        result += "\n"
    return result


def repair_toml_text(text: str) -> str:
    return repair_unquoted_windows_paths(dedupe_toml_text(text))

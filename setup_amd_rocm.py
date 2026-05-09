"""
AMD RDNA3 / gfx110x-class detection and optional TheRock ROCm PyTorch wheels.

Used only from setup.py --pyla-install when PYLAAI_SETUP_AUTO is set (setup.exe).
Pin URLs to a specific GitHub release; bump intentionally when upgrading.

Python 3.11 (cp311) only — must match tools/setup_bootstrap.py TARGET_PYTHON_VERSION.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import FrozenSet, Iterable, List, Sequence, Tuple

# Release: https://github.com/scottt/rocm-TheRock/releases/tag/v6.5.0rc-pytorch-gfx110x
_THE_ROCK_RELEASE = "v6.5.0rc-pytorch-gfx110x"
_THE_ROCK_BASE = (
    f"https://github.com/scottt/rocm-TheRock/releases/download/{_THE_ROCK_RELEASE}/"
)

# Pinned cp311 assets (June 2025 upload). Order: torch, torchvision, torchaudio.
THE_ROCK_PYTORCH_CP311_WHEELS: Tuple[str, ...] = (
    _THE_ROCK_BASE + "torch-2.7.0a0+rocm_git3f903c3-cp311-cp311-win_amd64.whl",
    _THE_ROCK_BASE + "torchvision-0.22.0+9eb57cd-cp311-cp311-win_amd64.whl",
    _THE_ROCK_BASE + "torchaudio-2.7.0a0+52638ef-cp311-cp311-win_amd64.whl",
)

# Navi 31 / 32 / 33and closely related gfx11 consumer IDs (hex, no 0x prefix).
# Extend when new AMD discrete IDs are confirmed for this wheel line.
RDNA3_AMD_PCI_DEV_IDS: FrozenSet[str] = frozenset(
    {
        "744C",
        "7448",  # Navi 31 variants
        "747E",  # Navi 32 (e.g. RX 7800 / 7700 class)
        "7480",
        "7481",
        "7483",  # Navi 33 (e.g. RX 7600 class)
        "7489",  # e.g. RX 7600 XT class
    }
)

# Used only when PNPDeviceID does not yield a known DEV id (driver quirks / WMI).
_NAME_FALLBACK_SUBSTRINGS: Tuple[str, ...] = (
    "RX 7900",
    "RX 7800",
    "RX 7700",
    "RX 7600",
    "RX 7500",
    "RX 9070",
    "RX 9060",
    "8060S",
    "Strix Halo",
)


def pci_dev_ids_from_pnp(pnp: str) -> List[str]:
    """Extract DEV_xxxx hex tokens from a PNPDeviceID string (AMD or any PCI)."""
    if not pnp:
        return []
    return [m.group(1).upper() for m in re.finditer(r"DEV_([0-9A-Fa-f]{4})", pnp)]


def rdna3_match_from_dev_ids(dev_ids: Iterable[str]) -> bool:
    return bool(set(d.upper() for d in dev_ids) & RDNA3_AMD_PCI_DEV_IDS)


def rdna3_match_from_gpu_name(name: str) -> bool:
    if not name:
        return False
    upper = name.upper()
    if "AMD" not in upper and "RADEON" not in upper:
        return False
    # Avoid common RDNA2 false positives if only using name.
    block_rdna2 = ("RX 6900", "RX 6800", "RX 6700", "RX 6650", "RX 6600", "RX 6500")
    if any(b.upper() in upper for b in block_rdna2):
        return False
    return any(s.upper() in upper for s in _NAME_FALLBACK_SUBSTRINGS)


def _wmic_video_controller_records() -> List[Tuple[str, str]]:
    """Return [(PNPDeviceID, Name), ...] from WMI (best-effort)."""
    try:
        raw = subprocess.check_output(
            ["wmic", "path", "win32_VideoController", "get", "PNPDeviceID,Name", "/format:list"],
            encoding="utf-8",
            errors="ignore",
            stderr=subprocess.DEVNULL,
            timeout=45,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return []

    records: List[Tuple[str, str]] = []
    pnp, name = "", ""
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            if pnp or name:
                records.append((pnp, name))
            pnp, name = "", ""
            continue
        if line.upper().startswith("PNPDEVICEID="):
            pnp = line.split("=", 1)[1].strip()
        elif line.upper().startswith("NAME="):
            name = line.split("=", 1)[1].strip()
    if pnp or name:
        records.append((pnp, name))
    return records


def is_amd_rdna3_gfx110x_class_windows() -> bool:
    """True if WMI suggests an AMD discrete/class GPU we ship TheRock wheels for."""
    if sys.platform != "win32":
        return False

    all_dev_ids: List[str] = []
    any_amd_name = False
    for pnp, name in _wmic_video_controller_records():
        if "VEN_1002" in pnp.upper() or "VEN_1022" in pnp.upper():
            all_dev_ids.extend(pci_dev_ids_from_pnp(pnp))
        if name and ("AMD" in name or "Radeon" in name):
            any_amd_name = True

    if rdna3_match_from_dev_ids(all_dev_ids):
        return True

    # Fallback: name hints for RDNA3-class marketing strings on AMD adapters.
    if any_amd_name:
        for _pnp, name in _wmic_video_controller_records():
            if rdna3_match_from_gpu_name(name):
                return True
    return False


def _setup_auto_enabled() -> bool:
    return os.environ.get("PYLAAI_SETUP_AUTO", "").strip().lower() in ("1", "true", "yes")


def _skip_rocm_install() -> bool:
    return os.environ.get("PYLAAI_SKIP_AMD_ROCM_PYTORCH", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def should_offer_amd_rocm_the_rock() -> bool:
    return (
        sys.platform == "win32"
        and _setup_auto_enabled()
        and not _skip_rocm_install()
        and is_amd_rdna3_gfx110x_class_windows()
        and sys.version_info[:2] == (3, 11)
    )


def try_install_amd_rocm_pytorch_the_rock(force_install_fn) -> bool:
    """
    Uninstall stock torch packages and install pinned TheRock wheels.

    ``force_install_fn`` is setup.force_install (pip install helper).
    """
    print("\nAuto setup: installing ROCm PyTorch (TheRock gfx110x wheels) for RDNA3-class AMD GPU...")
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "torch", "torchvision", "torchaudio"],
        check=False,
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    try:
        force_install_fn(list(THE_ROCK_PYTORCH_CP311_WHEELS))
    except subprocess.CalledProcessError as exc:
        print(f"\n[WARNING] TheRock PyTorch install failed ({exc}). Falling back to CPU PyTorch.")
        return False

    try:
        probe = subprocess.check_output(
            [
                sys.executable,
                "-c",
                "import torch; print(getattr(torch.version, 'hip', None) or '', torch.__version__)",
            ],
            encoding="utf-8",
            errors="ignore",
            timeout=120,
        ).strip()
        print(f"PyTorch probe after TheRock: {probe}")
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"\n[WARNING] Could not verify torch import ({exc}).")

    return True

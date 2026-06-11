import platform
import subprocess


VIRTUAL_GPU_TOKENS = (
    "microsoft basic",
    "virtual",
    "parsec",
    "remote",
    "iddcx",
    "mirror",
    "display only",
)


def _normalize_name(name):
    return str(name or "").strip()


def _is_virtual_gpu(name):
    lower = _normalize_name(name).lower()
    return not lower or any(token in lower for token in VIRTUAL_GPU_TOKENS)


def _classify_vendor(name):
    lower = _normalize_name(name).lower()
    if "nvidia" in lower or "geforce" in lower or "quadro" in lower:
        return "nvidia"
    if "amd" in lower or "radeon" in lower:
        return "amd"
    if "intel" in lower or "arc" in lower:
        return "intel"
    return None


def _wmic_video_controllers():
    try:
        output = subprocess.check_output(
            ["wmic", "path", "win32_VideoController", "get", "name"],
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []

    names = []
    for line in output.splitlines():
        name = _normalize_name(line)
        if not name or name.lower() == "name":
            continue
        names.append(name)
    return names


def _cim_video_controllers():
    if platform.system() != "Windows":
        return []
    try:
        output = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }",
            ],
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
    except Exception:
        return []

    names = []
    for line in output.splitlines():
        name = _normalize_name(line)
        if name:
            names.append(name)
    return names


def _enumerate_video_controller_names():
    names = _wmic_video_controllers()
    if names:
        return names
    return _cim_video_controllers()


def _prefer_discrete_gpu_name(names, vendor):
    matching = [name for name in names if _classify_vendor(name) == vendor]
    if not matching:
        return None
    discrete_markers = ("geforce", "quadro", "rtx ", "gtx ", " rx ", "arc ", "iris xe")
    for name in matching:
        lower = f" {_normalize_name(name).lower()} "
        if any(marker in lower for marker in discrete_markers):
            return name
    for name in matching:
        lower = _normalize_name(name).lower()
        if "radeon" in lower and "(tm) graphics" in lower:
            continue
        return name
    return matching[0]


def detect_graphics_cards():
    cards = []
    seen = set()

    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        ).strip()
        for line in output.splitlines():
            name = _normalize_name(line)
            if name and name not in seen:
                cards.append(("nvidia", name))
                seen.add(name)
    except Exception:
        pass

    for name in _enumerate_video_controller_names():
        if name in seen or _is_virtual_gpu(name):
            continue
        vendor = _classify_vendor(name)
        if vendor:
            cards.append((vendor, name))
            seen.add(name)

    return cards


def primary_vendor(cards=None):
    cards = cards if cards is not None else detect_graphics_cards()
    vendors = [vendor for vendor, _name in cards]
    for preferred in ("nvidia", "amd", "intel"):
        if preferred in vendors:
            return preferred
    return "cpu"


def primary_gpu_name(cards=None):
    cards = cards if cards is not None else detect_graphics_cards()
    vendor = primary_vendor(cards)
    if vendor == "cpu":
        return "Generic CPU"
    controller_names = _enumerate_video_controller_names()
    preferred_name = _prefer_discrete_gpu_name(controller_names, vendor)
    if preferred_name:
        return preferred_name
    for card_vendor, name in cards:
        if card_vendor == vendor:
            return name
    return "Generic CPU"


def get_gpu_data():
    """Legacy setup helper: (target_key, version, display_name)."""
    cards = detect_graphics_cards()
    vendor = primary_vendor(cards)
    name = primary_gpu_name(cards)

    if vendor == "nvidia":
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,compute_cap", "--format=csv,noheader,nounits"],
                encoding="utf-8",
                stderr=subprocess.DEVNULL,
            ).strip()
            nvidia_name, compute_cap = output.split(", ")
            return "nvidia", float(compute_cap), nvidia_name
        except Exception:
            return "nvidia", 0.0, name

    if vendor == "amd":
        return "amd_windows", 0.0, name
    if vendor == "intel":
        return "intel", 0.0, name
    return "cpu", 0.0, name


def normalize_preferred_device(preferred_device):
    preferred_device = str(preferred_device or "auto").strip().lower()
    if preferred_device in ("amd", "dml"):
        return "directml"
    if preferred_device == "gpu":
        return "auto"
    return preferred_device


def resolve_inference_device(preferred_device="auto", cards=None):
    """Resolve auto/gpu to the runtime that matches the detected primary GPU."""
    preferred_device = normalize_preferred_device(preferred_device)
    if preferred_device not in ("auto",):
        return preferred_device

    cards = cards if cards is not None else detect_graphics_cards()
    vendor = primary_vendor(cards)
    if vendor == "nvidia":
        return "cuda"
    if vendor in ("amd", "intel"):
        return "directml"
    if platform.system() == "Windows":
        # WMI can miss adapters in some environments; still try DirectML before CPU.
        return "directml"
    return "cpu"


def resolve_directml_device_id(device_id=None, cards=None):
    device_id = str(device_id or "auto").strip().lower()
    if device_id not in ("", "auto", "none"):
        return device_id
    return recommended_directml_device_id(cards)


def describe_directml_adapter(device_id=None, cards=None):
    device_id = resolve_directml_device_id(device_id, cards)
    if str(device_id).strip().lower() in ("", "auto", "none"):
        return "DirectML default adapter"
    try:
        adapter_index = int(device_id)
    except (TypeError, ValueError):
        return f"DirectML adapter {device_id!r}"
    adapters = list_directml_adapters(cards)
    if 0 <= adapter_index < len(adapters):
        adapter = adapters[adapter_index]
        return f"DirectML adapter {adapter_index}: {adapter.get('name')} ({adapter.get('vendor') or 'unknown'})"
    return f"DirectML adapter {adapter_index}"


def recommended_setup_onnx_variant(target=None, cards=None):
    """Pick the ONNX runtime variant for unattended setup.exe / auto install."""
    cards = cards if cards is not None else detect_graphics_cards()
    target_key = str(target or primary_vendor(cards) or "cpu").strip().lower()
    if target_key == "nvidia":
        return "cuda"
    if target_key in ("amd_windows", "amd") or "amd" in target_key:
        return "directml"
    if target_key == "intel":
        return "directml"
    if cards and primary_vendor(cards) != "cpu":
        return "directml"
    return "cpu"


def recommended_onnx_variant(vendor=None):
    cards = detect_graphics_cards()
    vendor = vendor or primary_vendor(cards)
    if vendor == "nvidia":
        return "cuda"
    if vendor in ("amd", "intel"):
        return "directml"
    return recommended_setup_onnx_variant(vendor, cards)


def list_directml_adapters(cards=None):
    adapters = []
    for index, name in enumerate(_enumerate_video_controller_names()):
        if _is_virtual_gpu(name):
            continue
        adapters.append({"index": index, "name": name, "vendor": _classify_vendor(name)})
    if not adapters:
        cards = cards if cards is not None else detect_graphics_cards()
        for vendor, name in cards:
            adapters.append({"index": len(adapters), "name": name, "vendor": vendor})
    return adapters


def recommended_directml_device_id(cards=None):
    adapters = list_directml_adapters(cards)
    physical = [adapter for adapter in adapters if adapter["vendor"] is not None]
    if len(physical) <= 1:
        return "auto"

    cards = cards if cards is not None else detect_graphics_cards()
    vendor = primary_vendor(cards)

    if vendor == "amd":
        for adapter in adapters:
            if adapter["vendor"] == "amd":
                return str(adapter["index"])
    if vendor == "nvidia":
        for adapter in adapters:
            if adapter["vendor"] == "nvidia":
                return str(adapter["index"])
    if vendor == "intel":
        for adapter in adapters:
            if adapter["vendor"] == "intel":
                return str(adapter["index"])

    return "auto"


def auto_candidate_variants(cards=None):
    cards = cards if cards is not None else detect_graphics_cards()
    vendors = {vendor for vendor, _name in cards}
    candidates = ["directml"]
    if "nvidia" in vendors:
        candidates.append("cuda")
    candidates.append("cpu")
    return candidates


def detect_runtime_variant():
    cards = detect_graphics_cards()
    return recommended_setup_onnx_variant(primary_vendor(cards), cards)


def normalize_runtime_variant(variant):
    variant = str(variant or "auto").strip().lower()
    if variant == "amd":
        return "directml"
    if variant == "openvino":
        return "openvino"
    return variant


def gpu_help_message(context, vendor=None, provider=None):
    vendor = vendor or primary_vendor()
    provider = provider or ""

    if context == "missing_gpu_provider":
        if vendor == "amd":
            return (
                "WARNING: GPU inference was requested but no usable GPU ONNX provider is installed. "
                "AMD users run: py -3.11-64 tools\\fix_gpu_runtime.py directml"
            )
        if vendor == "intel":
            return (
                "WARNING: GPU inference was requested but no usable GPU ONNX provider is installed. "
                "Intel users run: py -3.11-64 tools\\fix_gpu_runtime.py directml"
            )
        return (
            "WARNING: GPU inference was requested but no usable GPU ONNX provider is installed. "
            "NVIDIA users run: py -3.11-64 tools\\fix_gpu_runtime.py cuda"
        )

    if context == "session_cpu_fallback":
        if vendor == "amd":
            return (
                "AMD users repair DirectML with: py -3.11-64 tools\\fix_gpu_runtime.py directml"
            )
        if vendor == "intel":
            return (
                "Intel users repair DirectML with: py -3.11-64 tools\\fix_gpu_runtime.py directml"
            )
        return (
            "NVIDIA users can repair CUDA with: py -3.11-64 tools\\fix_gpu_runtime.py cuda"
        )

    if context == "runtime_provider_failure":
        if provider == "CUDAExecutionProvider":
            if vendor == "amd":
                return (
                    "CUDA is not supported on AMD Radeon. Use DirectML instead: "
                    "py -3.11-64 tools\\fix_gpu_runtime.py directml"
                )
            return (
                "CUDA/cuDNN runtime failed. NVIDIA users can repair it with: "
                "py -3.11-64 tools\\fix_gpu_runtime.py cuda"
            )
        if provider == "DmlExecutionProvider" and vendor == "amd":
            return (
                "DirectML failed on AMD. Reinstall with: "
                "py -3.11-64 tools\\fix_gpu_runtime.py directml"
            )

    return ""


def has_cuda_torch():
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False


def has_torch_directml():
    try:
        import torch_directml  # noqa: F401

        return True
    except Exception:
        return False


def resolve_easyocr_gpu():
    if has_cuda_torch():
        return True
    if primary_vendor() == "amd" and has_torch_directml():
        return True
    return False


def resolve_ultralytics_device(requested_device="0"):
    requested = str(requested_device).strip().lower()
    if requested not in ("", "0", "auto", "gpu"):
        return requested_device

    if has_cuda_torch():
        return "0"

    if has_torch_directml():
        try:
            import torch_directml

            device = torch_directml.device()
            return str(device)
        except Exception:
            pass

    return "cpu"


def apply_gpu_config(config, variant, cards=None):
    cards = cards if cards is not None else detect_graphics_cards()
    variant = normalize_runtime_variant(variant)
    if variant == "auto":
        variant = resolve_inference_device("auto", cards)
    config["cpu_or_gpu"] = variant
    if variant == "directml":
        device_id = resolve_directml_device_id(config.get("directml_device_id", "auto"), cards)
        if device_id != "auto":
            config["directml_device_id"] = device_id
    return config


def select_best_runtime_result(results, cards=None):
    """Prefer vendor-appropriate GPU runtimes over CPU when both benchmark successfully."""
    cards = cards if cards is not None else detect_graphics_cards()
    working = [
        result
        for result in results
        if result.get("ok") and float(result.get("ips") or 0) > 0
    ]
    if not working:
        return None

    vendor = primary_vendor(cards)
    if vendor == "amd":
        directml_results = [result for result in working if result.get("variant") == "directml"]
        if directml_results:
            return max(directml_results, key=lambda result: float(result.get("ips") or 0))
    if vendor == "intel":
        for preferred_variant in ("directml", "openvino"):
            matches = [result for result in working if result.get("variant") == preferred_variant]
            if matches:
                return max(matches, key=lambda result: float(result.get("ips") or 0))
    if vendor == "nvidia":
        cuda_results = [result for result in working if result.get("variant") == "cuda"]
        if cuda_results:
            return max(cuda_results, key=lambda result: float(result.get("ips") or 0))

    return max(working, key=lambda result: float(result.get("ips") or 0))


def describe_detected_gpus(cards=None):
    cards = cards if cards is not None else detect_graphics_cards()
    if not cards:
        return "No dedicated GPU detected."
    lines = [f"{vendor}: {name}" for vendor, name in cards]
    return f"Detected graphics: {', '.join(lines)} (primary={primary_vendor(cards)})"

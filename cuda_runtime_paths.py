import os
import site
import sys
from pathlib import Path


_CUDA_DLL_DIR_HANDLES = []
_CUDA_DLL_PATHS_ADDED = False


def _site_package_roots():
    roots = []
    for getter in (site.getsitepackages,):
        try:
            roots.extend(getter())
        except Exception:
            pass
    try:
        roots.append(site.getusersitepackages())
    except Exception:
        pass
    for entry in sys.path:
        if "site-packages" in str(entry).lower():
            roots.append(entry)

    seen = set()
    result = []
    for root in roots:
        try:
            path = Path(root).resolve()
        except Exception:
            continue
        key = os.path.normcase(str(path))
        if key not in seen and path.exists():
            seen.add(key)
            result.append(path)
    return result


def find_cuda_dll_directories():
    candidates = []
    for root in _site_package_roots():
        for relative in (
                Path("torch") / "lib",
                Path("nvidia") / "cublas" / "bin",
                Path("nvidia") / "cudnn" / "bin",
                Path("nvidia") / "cuda_runtime" / "bin",
                Path("nvidia") / "cuda_nvrtc" / "bin",
        ):
            path = root / relative
            if path.exists():
                candidates.append(path)

        nvidia_root = root / "nvidia"
        if nvidia_root.exists():
            for pattern in ("**/bin", "**/lib"):
                candidates.extend(path for path in nvidia_root.glob(pattern) if path.is_dir())

    seen = set()
    result = []
    for path in candidates:
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def add_cuda_dll_directories(verbose=False):
    global _CUDA_DLL_PATHS_ADDED
    if _CUDA_DLL_PATHS_ADDED:
        return [str(path) for path in find_cuda_dll_directories()]

    paths = find_cuda_dll_directories()
    if not paths:
        _CUDA_DLL_PATHS_ADDED = True
        return []

    current_path = os.environ.get("PATH", "")
    current_parts = {os.path.normcase(part) for part in current_path.split(os.pathsep) if part}
    new_parts = []
    for path in paths:
        path_str = str(path)
        if os.path.normcase(path_str) not in current_parts:
            new_parts.append(path_str)
        if hasattr(os, "add_dll_directory"):
            try:
                _CUDA_DLL_DIR_HANDLES.append(os.add_dll_directory(path_str))
            except OSError:
                pass

    if new_parts:
        os.environ["PATH"] = os.pathsep.join(new_parts + [current_path])
    _CUDA_DLL_PATHS_ADDED = True

    if verbose and paths:
        print("Added CUDA DLL search paths:")
        for path in paths:
            print(f"  {path}")
    return [str(path) for path in paths]


def has_cuda_dependency_dlls():
    names = {"cublasLt64_12.dll", "cudnn64_9.dll"}
    found = set()
    for path in find_cuda_dll_directories():
        for name in names:
            if (path / name).exists():
                found.add(name)
    return names.issubset(found), sorted(names - found)

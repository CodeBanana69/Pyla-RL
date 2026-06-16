"""Install and verify EasyOCR for brawler selection."""

from __future__ import annotations

import json
import subprocess
from typing import Sequence

EASYOCR_MANUAL_DEPS = [
    "scipy",
    "PyYAML",
    "scikit-image",
    "ninja",
    "pyclipper",
    "python-bidi",
    "Shapely",
]

TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"

FAST_PROBE_TIMEOUT = 60
SMOKE_TEST_TIMEOUT = 180

EASYOCR_REPAIR_HINT = (
    "Re-run setup.exe in the project folder, or install missing packages with:\n"
    f'  pip install torch torchvision --index-url {TORCH_CPU_INDEX}\n'
    f"  pip install --force-reinstall --no-deps easyocr\n"
    f"  pip install {' '.join(EASYOCR_MANUAL_DEPS)}"
)


def _probe_script(*, smoke_test: bool) -> str:
    smoke = "True" if smoke_test else "False"
    return (
        "import json, sys\n"
        f"smoke_test = {smoke}\n"
        "errors = []\n"
        "versions = {}\n"
        "models_ready = False\n"
        "for module_name, attr in (\n"
        "    ('easyocr', '__version__'),\n"
        "    ('scipy', '__version__'),\n"
        "    ('skimage', '__version__'),\n"
        "    ('torch', '__version__'),\n"
        "):\n"
        "    try:\n"
        "        module = __import__(module_name)\n"
        "        versions[module_name] = getattr(module, attr, 'ok')\n"
        "    except Exception as exc:\n"
        "        errors.append(f'{module_name}: {exc}')\n"
        "if not errors and smoke_test:\n"
        "    try:\n"
        "        import easyocr\n"
        "        import numpy as np\n"
        "        reader = easyocr.Reader(['en'], verbose=False, gpu=False)\n"
        "        reader.readtext(np.zeros((32, 128, 3), dtype=np.uint8))\n"
        "        models_ready = True\n"
        "    except Exception as exc:\n"
        "        errors.append(f'easyocr.Reader: {exc}')\n"
        "print(json.dumps({\n"
        "    'ok': not errors,\n"
        "    'executable': sys.executable,\n"
        "    'versions': versions,\n"
        "    'models_ready': models_ready,\n"
        "    'error': '; '.join(errors),\n"
        "}))\n"
    )


def probe_easyocr_runtime(
    python_command: Sequence[str] | str,
    *,
    smoke_test: bool = False,
) -> dict:
    if isinstance(python_command, str):
        python_command = [python_command]
    timeout = SMOKE_TEST_TIMEOUT if smoke_test else FAST_PROBE_TIMEOUT
    try:
        completed = subprocess.run(
            python_command + ["-c", _probe_script(smoke_test=smoke_test)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (completed.stdout or "").strip()
        if not output:
            stderr = (completed.stderr or "").strip()
            return {
                "ok": False,
                "executable": " ".join(python_command),
                "error": stderr or f"probe exited with code {completed.returncode}",
                "versions": {},
                "models_ready": False,
            }
        return json.loads(output.splitlines()[-1])
    except subprocess.TimeoutExpired:
        phase = "Reader smoke test" if smoke_test else "import probe"
        return {
            "ok": False,
            "executable": " ".join(python_command),
            "error": f"{phase} timed out after {timeout}s",
            "versions": {},
            "models_ready": False,
        }
    except Exception as exc:
        return {
            "ok": False,
            "executable": " ".join(python_command),
            "error": str(exc),
            "versions": {},
            "models_ready": False,
        }


def verify_easyocr_runtime(python_command: Sequence[str] | str) -> dict:
    result = probe_easyocr_runtime(python_command, smoke_test=True)
    if not result.get("ok"):
        raise RuntimeError(
            "EasyOCR is not ready for brawler selection "
            f"({result.get('executable')}): {result.get('error', 'unknown error')}. "
            f"{EASYOCR_REPAIR_HINT}"
        )
    return result


def install_easyocr_stack(python_command: Sequence[str] | str) -> None:
    if isinstance(python_command, str):
        python_command = [python_command]
    print("Installing EasyOCR stack (CPU torch + manual deps)...")
    subprocess.check_call(
        python_command
        + [
            "-m",
            "pip",
            "install",
            "torch",
            "torchvision",
            "--index-url",
            TORCH_CPU_INDEX,
        ]
    )
    subprocess.check_call(
        python_command
        + ["-m", "pip", "install", "--force-reinstall", "--no-deps", "easyocr"]
    )
    subprocess.check_call(python_command + ["-m", "pip", "install", *EASYOCR_MANUAL_DEPS])

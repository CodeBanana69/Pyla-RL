import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Install a tested ONNX vision model.")
    parser.add_argument("--source", required=True, help="Path to the exported .onnx model.")
    parser.add_argument("--target", default="models/mainInGameModel.onnx", help="Active model path.")
    args = parser.parse_args()

    source = (ROOT / args.source).resolve()
    target = (ROOT / args.target).resolve()
    if not source.exists():
        raise SystemExit(f"Source model does not exist: {source}")
    if source.suffix.lower() != ".onnx":
        raise SystemExit("Source model must be an .onnx file.")

    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_suffix(".onnx.bak")
    if target.exists() and not backup.exists():
        shutil.copy2(target, backup)
        print(f"Backed up old model: {backup}")

    shutil.copy2(source, target)
    print(f"Installed vision model: {target}")


if __name__ == "__main__":
    main()

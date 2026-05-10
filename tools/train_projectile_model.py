"""Train the dedicated projectile detector and export it to ONNX.

Thin wrapper around `tools/train_vision_model.py` that retargets the trainer at
`datasets/projectile_model/data.yaml` and writes the exported ONNX to
`models/projectileDetector.onnx`. Pass `--replace` to install it as the active
projectile detector (with a `.bak` backup of any existing one).
"""

from train_vision_model import main


if __name__ == "__main__":
    import sys

    if "--data" not in sys.argv:
        sys.argv.extend(["--data", "datasets/projectile_model/data.yaml"])
    if "--name" not in sys.argv:
        sys.argv.extend(["--name", "pylaai_projectile"])
    if "--project" not in sys.argv:
        sys.argv.extend(["--project", "runs/projectile_train"])
    if "--target" not in sys.argv:
        sys.argv.extend(["--target", "models/projectileDetector.onnx"])
    main()

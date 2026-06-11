from train_vision_model import main


if __name__ == "__main__":
    import sys

    if "--data" not in sys.argv:
        sys.argv.extend(["--data", "datasets/wall_model/data.yaml"])
    if "--name" not in sys.argv:
        sys.argv.extend(["--name", "pylaai_wall"])
    if "--project" not in sys.argv:
        sys.argv.extend(["--project", "runs/wall_train"])
    if "--target" not in sys.argv:
        sys.argv.extend(["--target", "models/tileDetector.onnx"])
    main()

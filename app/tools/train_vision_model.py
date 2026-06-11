import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Train and export a better PylaAi-XXZ vision model.")
    parser.add_argument("--data", default="datasets/vision_model/data.yaml", help="YOLO data.yaml path.")
    parser.add_argument("--base", default="yolov8n.pt", help="YOLO .pt base model or previous best.pt.")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", default="-1", help="Ultralytics batch value. -1 auto-selects.")
    parser.add_argument("--device", default="0", help="0 for GPU, cpu for CPU.")
    parser.add_argument("--name", default="pylaai_vision")
    parser.add_argument("--project", default="runs/vision_train")
    parser.add_argument("--replace", action="store_true", help="Replace models/mainInGameModel.onnx after export.")
    parser.add_argument("--target", default="models/mainInGameModel.onnx", help="Active ONNX path used with --replace.")
    args = parser.parse_args()

    data = (ROOT / args.data).resolve()
    if not data.exists():
        raise SystemExit(f"Dataset file does not exist: {data}")

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("Missing ultralytics. Run setup.exe or python setup.py install first.") from exc

    batch = int(args.batch) if str(args.batch).lstrip("-").isdigit() else args.batch
    model = YOLO(args.base)
    results = model.train(
        data=str(data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=batch,
        device=args.device,
        name=args.name,
        project=str(ROOT / args.project),
    )

    best_pt = Path(results.save_dir) / "weights" / "best.pt"
    if not best_pt.exists():
        raise SystemExit(f"Training finished but best.pt was not found: {best_pt}")

    trained = YOLO(str(best_pt))
    exported = Path(trained.export(format="onnx", imgsz=args.imgsz, opset=12, simplify=True))
    print(f"Exported ONNX: {exported}")

    if args.replace:
        target = (ROOT / args.target).resolve()
        backup = target.with_suffix(".onnx.bak")
        if target.exists() and not backup.exists():
            shutil.copy2(target, backup)
            print(f"Backed up old model: {backup}")
        shutil.copy2(exported, target)
        print(f"Replaced active model: {target}")
    else:
        print("Test this model first, then rerun with --replace if it is better.")


if __name__ == "__main__":
    main()

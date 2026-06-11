import argparse
import json
import random
import shutil
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLASSES = ["enemy", "teammate", "player"]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def find_images(source: Path):
    return sorted(
        path for path in source.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def unique_name(path: Path, used: set[str]) -> str:
    stem = "_".join(path.relative_to(path.parents[1]).with_suffix("").parts)
    name = f"{stem}{path.suffix.lower()}"
    counter = 1
    while name in used:
        name = f"{stem}_{counter}{path.suffix.lower()}"
        counter += 1
    used.add(name)
    return name


def write_data_yaml(output: Path, classes):
    lines = [
        f"path: {output.as_posix()}",
        "train: images/train",
        "val: images/val",
        "names:",
    ]
    for index, class_name in enumerate(classes):
        lines.append(f"  {index}: {class_name}")
    (output / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def labels_from_metadata(image: Path, classes):
    metadata_path = image.with_suffix(".json")
    if not metadata_path.exists():
        return None

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    detections = metadata.get("raw_tile_detection") or metadata.get("raw_detection") or {}
    if not isinstance(detections, dict):
        return None

    with Image.open(image) as img:
        width, height = img.size
    if width <= 0 or height <= 0:
        return None

    class_to_id = {class_name: index for index, class_name in enumerate(classes)}
    label_lines = []
    for class_name, boxes in detections.items():
        if class_name not in class_to_id or not boxes:
            continue
        class_id = class_to_id[class_name]
        for box in boxes:
            if len(box) < 4:
                continue
            x1, y1, x2, y2 = [float(value) for value in box[:4]]
            x1, x2 = sorted((max(0.0, min(width, x1)), max(0.0, min(width, x2))))
            y1, y2 = sorted((max(0.0, min(height, y1)), max(0.0, min(height, y2))))
            box_w = x2 - x1
            box_h = y2 - y1
            if box_w < 2 or box_h < 2:
                continue
            cx = (x1 + x2) * 0.5 / width
            cy = (y1 + y2) * 0.5 / height
            label_lines.append(
                f"{class_id} {cx:.6f} {cy:.6f} {box_w / width:.6f} {box_h / height:.6f}"
            )

    return "\n".join(label_lines) + ("\n" if label_lines else "")


def main():
    parser = argparse.ArgumentParser(
        description="Build a YOLO dataset skeleton from captured bad vision frames."
    )
    parser.add_argument("--source", default="debug_frames/vision", help="Captured frame folder.")
    parser.add_argument("--output", default="datasets/vision_model", help="YOLO dataset output folder.")
    parser.add_argument("--val-split", type=float, default=0.2, help="Validation fraction.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--classes",
        default=",".join(DEFAULT_CLASSES),
        help="Comma-separated YOLO class names in order.",
    )
    parser.add_argument(
        "--include-empty-labels",
        action="store_true",
        help="Create empty YOLO label files. Use only for unlabeled review/export, not final training.",
    )
    parser.add_argument(
        "--metadata-labels",
        action="store_true",
        help="Create YOLO labels from captured JSON metadata such as raw_tile_detection.",
    )
    args = parser.parse_args()

    classes = [name.strip() for name in args.classes.split(",") if name.strip()]
    if not classes:
        raise SystemExit("At least one class is required.")

    source = (ROOT / args.source).resolve()
    output = (ROOT / args.output).resolve()
    if not source.exists():
        raise SystemExit(f"Source folder does not exist: {source}")

    images = find_images(source)
    if not images:
        raise SystemExit(f"No captured images found in {source}")

    random.seed(args.seed)
    random.shuffle(images)
    val_count = max(1, int(len(images) * args.val_split)) if len(images) > 1 else 0
    val_images = set(images[:val_count])

    for split in ("train", "val"):
        (output / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "labels" / split).mkdir(parents=True, exist_ok=True)

    used_names = set()
    copied = {"train": 0, "val": 0}
    for image in images:
        split = "val" if image in val_images else "train"
        name = unique_name(image, used_names)
        target_image = output / "images" / split / name
        shutil.copy2(image, target_image)

        source_label = image.with_suffix(".txt")
        target_label = output / "labels" / split / f"{Path(name).stem}.txt"
        if source_label.exists():
            shutil.copy2(source_label, target_label)
        elif args.metadata_labels:
            labels = labels_from_metadata(image, classes)
            if labels is not None:
                target_label.write_text(labels, encoding="utf-8")
        elif args.include_empty_labels:
            target_label.write_text("", encoding="utf-8")

        copied[split] += 1

    write_data_yaml(output, classes)

    print(f"Dataset created: {output}")
    print(f"Images: {copied['train']} train, {copied['val']} val")
    print("Classes:")
    for index, class_name in enumerate(classes):
        print(f"  {index} {class_name}")
    if not args.include_empty_labels:
        print("Next: label the images in YOLO format before training.")


if __name__ == "__main__":
    main()

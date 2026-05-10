"""Convert a Roboflow YOLOv8 projectile export into a clean training dataset.

The Roboflow export at `brawl stars.yolov8/` ships with:
    - 752 image/label pairs in `train/`
    - a corrupted `data.yaml` (Roboflow's description leaked into `names:`)
    - 5 raw class IDs that we collapse to a single class `projectile`

This script normalises the export into `datasets/projectile_model/`:
    - 90/10 train/val split
    - every label line rewritten so the leading class id is 0
    - a clean `data.yaml` consumable by `tools/train_vision_model.py`
"""

import argparse
import random
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def find_image_label_pairs(images_dir: Path, labels_dir: Path):
    pairs = []
    for image in sorted(images_dir.iterdir()):
        if not image.is_file() or image.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        label = labels_dir / f"{image.stem}.txt"
        if label.exists():
            pairs.append((image, label))
    return pairs


def rewrite_label_to_single_class(label_path: Path) -> str:
    """Read a YOLO label file and return its content with all class ids -> 0."""
    out_lines = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            continue
        parts[0] = "0"
        out_lines.append(" ".join(parts))
    return "\n".join(out_lines) + ("\n" if out_lines else "")


def write_data_yaml(output: Path):
    yaml_text = (
        f"path: {output.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: projectile\n"
    )
    (output / "data.yaml").write_text(yaml_text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Build a clean single-class projectile YOLO dataset from a Roboflow export."
    )
    parser.add_argument(
        "--source",
        default="brawl stars.yolov8",
        help="Roboflow export root (must contain a `train/images` and `train/labels` folder).",
    )
    parser.add_argument(
        "--output",
        default="datasets/projectile_model",
        help="Destination YOLO dataset folder.",
    )
    parser.add_argument("--val-split", type=float, default=0.1, help="Validation fraction.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete the destination folder before rebuilding it.",
    )
    args = parser.parse_args()

    source = (ROOT / args.source).resolve()
    output = (ROOT / args.output).resolve()
    images_dir = source / "train" / "images"
    labels_dir = source / "train" / "labels"

    if not images_dir.is_dir() or not labels_dir.is_dir():
        raise SystemExit(
            f"Expected `{images_dir}` and `{labels_dir}` to exist. "
            "Did you unzip `brawl stars.yolov8.zip`?"
        )

    pairs = find_image_label_pairs(images_dir, labels_dir)
    if not pairs:
        raise SystemExit(f"No image/label pairs found in {source}.")

    if args.clean and output.exists():
        shutil.rmtree(output)

    random.seed(args.seed)
    random.shuffle(pairs)
    val_count = max(1, int(len(pairs) * args.val_split)) if len(pairs) > 1 else 0
    val_pairs = set(pairs[:val_count])

    for split in ("train", "val"):
        (output / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "labels" / split).mkdir(parents=True, exist_ok=True)

    counts = {"train": 0, "val": 0}
    skipped_labels = 0
    for image, label in pairs:
        split = "val" if (image, label) in val_pairs else "train"
        target_image = output / "images" / split / image.name
        target_label = output / "labels" / split / label.name

        shutil.copy2(image, target_image)
        rewritten = rewrite_label_to_single_class(label)
        if not rewritten:
            skipped_labels += 1
        target_label.write_text(rewritten, encoding="utf-8")
        counts[split] += 1

    write_data_yaml(output)

    print(f"Dataset built at: {output}")
    print(f"Images: {counts['train']} train, {counts['val']} val")
    print(f"Total pairs processed: {sum(counts.values())} (empty labels: {skipped_labels})")
    print("All raw class IDs collapsed to 0 (`projectile`).")
    print(f"Train next: python tools/train_projectile_model.py --replace")


if __name__ == "__main__":
    main()

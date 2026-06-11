from create_vision_dataset import main


if __name__ == "__main__":
    import sys

    if "--source" not in sys.argv:
        sys.argv.extend(["--source", "debug_frames/wall_vision"])
    if "--output" not in sys.argv:
        sys.argv.extend(["--output", "datasets/wall_model"])
    if "--classes" not in sys.argv:
        sys.argv.extend(["--classes", "wall,bush,close_bush"])
    if "--metadata-labels" not in sys.argv:
        sys.argv.append("--metadata-labels")
    if "--include-empty-labels" not in sys.argv:
        sys.argv.append("--include-empty-labels")
    main()

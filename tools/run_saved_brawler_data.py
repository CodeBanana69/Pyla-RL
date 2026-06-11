import json
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root / "app"))
from main import pyla_main


queue_file = Path("data/latest_brawler_data.json")
if not queue_file.exists():
    queue_file = Path("latest_brawler_data.json")
with open(queue_file, encoding="utf-8") as f:
    pyla_main(json.load(f))

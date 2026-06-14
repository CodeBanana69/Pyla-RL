import json
import time
from pathlib import Path

_SESSION_ID = "5a439b"
_LOG_PATH = Path(__file__).resolve().parents[1] / "debug-5a439b.log"


def agent_debug_log(hypothesis_id, location, message, data=None, run_id="pre-fix"):
    # region agent log
    try:
        payload = {
            "sessionId": _SESSION_ID,
            "timestamp": int(time.time() * 1000),
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "runId": run_id,
        }
        with open(_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass
    # endregion

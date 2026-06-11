import os
import re
import sys
from datetime import datetime

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
LOG_DIR = "logs"
TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"


class _TimestampedStream:
    def __init__(self, original, file):
        self._original = original
        self._file = file
        self._at_line_start = True

    def write(self, text):
        if not text:
            return 0
        self._original.write(text)

        stripped = ANSI_ESCAPE_RE.sub("", text)
        out = []
        for ch in stripped:
            if self._at_line_start and ch != "\n":
                out.append(f"[{datetime.now().strftime(TIMESTAMP_FMT)}] ")
                self._at_line_start = False
            out.append(ch)
            if ch == "\n":
                self._at_line_start = True
        self._file.write("".join(out))
        self._file.flush()
        return len(text)

    def flush(self):
        self._original.flush()
        self._file.flush()

    def __getattr__(self, name):
        return getattr(self._original, name)


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(
        LOG_DIR, f"pyla_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    )
    log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _TimestampedStream(sys.stdout, log_file)
    sys.stderr = _TimestampedStream(sys.stderr, log_file)
    return log_path


def setup_logging_if_enabled(config_path="./cfg/general_config.toml"):
    import toml
    if not os.path.exists(config_path):
        return None
    with open(config_path, "r") as f:
        enabled = toml.load(f).get("terminal_logging", "no")
    if str(enabled).lower() in ("yes", "true"):
        return setup_logging()
    return None

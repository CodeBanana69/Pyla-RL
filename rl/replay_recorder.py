"""Batch disk recorder for SAC offline training (.npz)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


_SCHEMA_VERSION = 1


@dataclass
class ReplayRecorderConfig:
    replay_dir: str = "data/rl_replay"
    batch_size_transitions: int = 1000
    flush_interval_seconds: float = 30.0
    disk_budget_mb: float = 2048.0
    compress: bool = True


class ReplayRecorder:
    """Accumulates transitions and writes compressed .npz atomically."""

    def __init__(
        self,
        *,
        cfg: Optional[ReplayRecorderConfig] = None,
        session_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.cfg = cfg or ReplayRecorderConfig()
        self.session_id = session_id or str(int(time.time()))
        self.meta = dict(metadata or {})
        self._obs: List[np.ndarray] = []
        self._next_obs: List[np.ndarray] = []
        self._actions: List[np.ndarray] = []
        self._rewards: List[float] = []
        self._dones: List[float] = []
        self._infos: List[Dict[str, Any]] = []
        self._last_flush_t = time.time()
        self._batch_idx = 0
        Path(self.cfg.replay_dir).mkdir(parents=True, exist_ok=True)
        self._write_sidecar()

    def _write_sidecar(self) -> None:
        path = Path(self.cfg.replay_dir) / f"{self.session_id}_meta.json"
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "session_id": self.session_id,
            "created": time.time(),
            "meta": self.meta,
        }
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def append(
        self,
        obs: np.ndarray,
        action: np.ndarray,
        reward: float,
        next_obs: np.ndarray,
        done: bool,
        info: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._obs.append(np.asarray(obs, dtype=np.float32).copy())
        self._next_obs.append(np.asarray(next_obs, dtype=np.float32).copy())
        self._actions.append(np.asarray(action, dtype=np.float32).copy())
        self._rewards.append(float(reward))
        self._dones.append(1.0 if done else 0.0)
        self._infos.append(dict(info or {}))

        n = len(self._obs)
        if n >= self.cfg.batch_size_transitions:
            self.flush()
        elif time.time() - self._last_flush_t >= self.cfg.flush_interval_seconds:
            self.flush()

    def flush(self) -> None:
        if not self._obs:
            return
        replay_dir = Path(self.cfg.replay_dir)
        replay_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        fname = f"{stamp}_{self.session_id}_b{self._batch_idx:06d}.npz"
        final = replay_dir / fname
        # Atomic-ish write: some Windows setups reject Path.replace() from *.npz.tmp; use a detached temp file in-dir.
        tmp_fd, tmp_path_str = tempfile.mkstemp(
            suffix=".partial.npz",
            prefix=".replay_",
            dir=str(replay_dir),
        )
        os.close(tmp_fd)
        tmp_path = Path(tmp_path_str)

        payload = dict(
            obs=np.stack(self._obs, axis=0),
            next_obs=np.stack(self._next_obs, axis=0),
            actions=np.stack(self._actions, axis=0),
            rewards=np.asarray(self._rewards, dtype=np.float32),
            dones=np.asarray(self._dones, dtype=np.float32),
            schema=np.array([_SCHEMA_VERSION], dtype=np.int32),
        )
        saver = np.savez_compressed if self.cfg.compress else np.savez
        try:
            saver(tmp_path_str, **payload)
            os.replace(tmp_path_str, str(final))
        finally:
            try:
                if tmp_path.is_file():
                    tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

        self._obs.clear()
        self._next_obs.clear()
        self._actions.clear()
        self._rewards.clear()
        self._dones.clear()
        self._infos.clear()
        self._batch_idx += 1
        self._last_flush_t = time.time()

        self._enforce_disk_budget()

    def _enforce_disk_budget(self) -> None:
        budget_bytes = float(self.cfg.disk_budget_mb) * (1024.0 ** 2)
        replay_dir = Path(self.cfg.replay_dir)
        if not replay_dir.is_dir():
            return
        files = sorted(replay_dir.glob("*.npz"), key=lambda p: p.stat().st_mtime)
        total = sum(f.stat().st_size for f in files)
        while files and total > budget_bytes:
            oldest = files.pop(0)
            sz = oldest.stat().st_size
            try:
                oldest.unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:
                break
            total -= sz

    def close(self) -> None:
        self.flush()


def load_replay_npzs(replay_dir: str) -> Dict[str, np.ndarray]:
    """Load and concatenate every ``*.npz`` in replay_dir."""

    replay_path = Path(replay_dir)
    if not replay_path.is_dir():
        raise FileNotFoundError(replay_dir)
    batches = sorted(replay_path.glob("*.npz"))
    if not batches:
        raise ValueError(f"No .npz files in {replay_dir}")

    chunks_o, chunks_no, chunks_a, chunks_r, chunks_d = [], [], [], [], []
    for p in batches:
        try:
            data = np.load(p, allow_pickle=False)
        except Exception:
            continue
        if "obs" not in data or "next_obs" not in data:
            continue
        chunks_o.append(data["obs"])
        chunks_no.append(data["next_obs"])
        chunks_a.append(data["actions"])
        chunks_r.append(data["rewards"])
        chunks_d.append(data["dones"])

    if not chunks_o:
        raise ValueError(f"No readable .npz replay batches in {replay_dir}")

    num = int(sum(int(a.shape[0]) for a in chunks_o))
    return {
        "obs": np.concatenate(chunks_o, axis=0),
        "next_obs": np.concatenate(chunks_no, axis=0),
        "actions": np.concatenate(chunks_a, axis=0),
        "rewards": np.concatenate(chunks_r, axis=0),
        "dones": np.concatenate(chunks_d, axis=0),
        "num_transitions": np.array([num], dtype=np.int64),
    }

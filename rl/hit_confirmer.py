"""Correlate predicted projectile intercept times with HP damage events."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

from rl.health_monitor import DamageEvent
from rl.projectile_tracker import ProjectileTracker


@dataclass
class ConfirmedHit:
    track_id: int
    expected_hit_time: float
    damage_time: float
    drop_pct: float


class HitConfirmer:
    """Match ``pending_intercepts`` ETA wall-clock times to ``DamageEvent`` times."""

    def __init__(self, history_seconds: float = 2.0) -> None:
        self.history_seconds = float(history_seconds)
        self._pending: Deque[Tuple[int, float]] = deque()
        self._damage: Deque[DamageEvent] = deque(maxlen=64)
        self._confirmations: Deque[Tuple[float, int]] = deque(maxlen=128)

    def reset(self) -> None:
        self._pending.clear()
        self._damage.clear()
        self._confirmations.clear()

    def record_damage(self, ev: Optional[DamageEvent]) -> None:
        if ev is not None:
            self._damage.append(ev)

    def record_pending_intercepts(
        self,
        items: List[Tuple[int, float]],
        now: float,
    ) -> None:
        """``items`` are (track_id, eta_seconds); wall-clock hit time = now + eta."""
        ids = {int(tid) for tid, _ in items}
        if ids:
            self._pending = deque(
                [(t, th) for (t, th) in self._pending if int(t) not in ids]
            )
        for tid, eta in items:
            self._pending.append((int(tid), float(now) + float(eta)))
        self._prune_old(now)

    def _prune_old(self, now: float) -> None:
        cut = now - self.history_seconds
        while self._pending and self._pending[0][1] < cut:
            self._pending.popleft()
        while self._damage and self._damage[0].time < cut:
            self._damage.popleft()
        while self._confirmations and self._confirmations[0][0] < cut:
            self._confirmations.popleft()

    def confirm(
        self,
        tracker: ProjectileTracker,
        now: float,
        tolerance_seconds: float,
    ) -> Optional[ConfirmedHit]:
        """Pair damage events with pending intercepts (smallest |t_hit - t_dmg|)."""
        self._prune_old(now)
        tol = max(1e-6, float(tolerance_seconds))

        best: Optional[ConfirmedHit] = None
        best_dt = float("inf")

        for ev in self._damage:
            for tid, t_hit in self._pending:
                dt = abs(float(t_hit) - float(ev.time))
                if dt <= tol and dt < best_dt:
                    best_dt = dt
                    best = ConfirmedHit(
                        track_id=int(tid),
                        expected_hit_time=float(t_hit),
                        damage_time=float(ev.time),
                        drop_pct=float(ev.drop_pct),
                    )
        if best is not None:
            for tr in tracker.tracks:
                if int(tr.track_id) == int(best.track_id):
                    tr.confidence_confirmed = True
                    break
            self._confirmations.append((float(now), int(best.track_id)))
        return best

    def is_recent_confirmed_hit(self, now: float, lookback_seconds: float) -> bool:
        self._prune_old(now)
        lb = float(lookback_seconds)
        for t_conf, _tid in reversed(self._confirmations):
            if now - t_conf <= lb:
                return True
        return False

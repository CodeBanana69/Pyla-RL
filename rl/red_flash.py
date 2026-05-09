"""Full-frame red dominance spike detector (damage vignette)."""

from __future__ import annotations

from typing import Optional

import numpy as np


class RedFlashDetector:
    """Flags frames where mean R dominates G+B (damage screen tint)."""

    def __init__(
        self,
        *,
        threshold: float = 1.40,
        baseline_alpha: float = 0.1,
        baseline_min: float = 0.6,
        baseline_max: float = 2.5,
    ) -> None:
        self.threshold = float(threshold)
        self.baseline_alpha = float(baseline_alpha)
        self.baseline_min = float(baseline_min)
        self.baseline_max = float(baseline_max)
        self._baseline: Optional[float] = None

    def reset(self) -> None:
        self._baseline = None

    def update(self, frame_rgb: Optional[np.ndarray]) -> bool:
        """Return True if this frame looks like a red damage flash."""
        if frame_rgb is None or frame_rgb.size == 0:
            return False
        if frame_rgb.ndim < 3 or frame_rgb.shape[2] < 3:
            return False
        r = float(np.mean(frame_rgb[:, :, 0]))
        g = float(np.mean(frame_rgb[:, :, 1]))
        b = float(np.mean(frame_rgb[:, :, 2]))
        red_dom = r / max(1e-6, 0.5 * (g + b))

        if self._baseline is None:
            self._baseline = red_dom
            return False

        flash = red_dom > self._baseline * self.threshold
        if not flash:
            a = self.baseline_alpha
            self._baseline = (1.0 - a) * self._baseline + a * red_dom
            self._baseline = max(self.baseline_min, min(self.baseline_max, self._baseline))
        return bool(flash)

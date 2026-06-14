"""Provide a minimal OpenCV stub when cv2 is missing or only a namespace package."""

from __future__ import annotations

import sys
import types


def cv2_is_usable() -> bool:
    try:
        import cv2
    except ImportError:
        return False
    return hasattr(cv2, "IMREAD_COLOR") and callable(getattr(cv2, "cvtColor", None))


def install_cv2_stub() -> None:
    import numpy as np

    def cvtColor(img, code, dst=None, dstCn=None):
        return img

    def inRange(src, lower, upper):
        return np.zeros(src.shape[:2], dtype=np.uint8)

    def morphologyEx(src, op, kernel):
        return src

    def imdecode(buf, flags):
        return None

    def imencode(ext, img, params=None):
        return False, np.array([], dtype=np.uint8)

    def matchTemplate(*args, **kwargs):
        return np.zeros((1, 1), dtype=np.float32)

    def minMaxLoc(mat):
        return 0.0, 0.0, (0, 0), (0, 0)

    cv2 = types.SimpleNamespace(
        IMREAD_COLOR=1,
        COLOR_RGB2HSV=40,
        COLOR_RGB2BGR=4,
        COLOR_BGR2RGB=4,
        COLOR_RGB2GRAY=7,
        COLOR_BGR2GRAY=6,
        MORPH_CLOSE=3,
        MORPH_OPEN=2,
        MORPH_RECT=0,
        RETR_EXTERNAL=0,
        CHAIN_APPROX_SIMPLE=2,
        TM_CCOEFF_NORMED=5,
        CC_STAT_AREA=4,
        cvtColor=cvtColor,
        inRange=inRange,
        morphologyEx=morphologyEx,
        getStructuringElement=lambda shape, ksize: None,
        findContours=lambda *args, **kwargs: ([], None),
        countNonZero=lambda arr: int(np.count_nonzero(arr)),
        contourArea=lambda contour: 0.0,
        boundingRect=lambda contour: (0, 0, 0, 0),
        clipLine=lambda *args: (True, (0, 0), (1, 1)),
        connectedComponentsWithStats=lambda *args, **kwargs: (0, None, None, None),
        imdecode=imdecode,
        imencode=imencode,
        matchTemplate=matchTemplate,
        minMaxLoc=minMaxLoc,
        rectangle=lambda *args, **kwargs: None,
        circle=lambda *args, **kwargs: None,
        imwrite=lambda *args, **kwargs: True,
        __version__="test-stub",
    )
    sys.modules["cv2"] = cv2


def ensure_cv2_for_tests() -> None:
    if cv2_is_usable():
        return
    install_cv2_stub()


ensure_cv2_for_tests()

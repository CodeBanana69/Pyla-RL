"""Visual debug window backends for PylaAi-XXZ."""

import queue
import sys
import threading

import cv2
import numpy as np

_opencv_highgui_available = None
_opencv_highgui_warned = False

OPENCV_REPAIR_CMD = (
    "pip uninstall -y opencv-python-headless && pip install --no-deps opencv-python==4.8.0.76"
)


def reset_opencv_highgui_cache():
    global _opencv_highgui_available
    _opencv_highgui_available = None


def opencv_highgui_available():
    global _opencv_highgui_available
    if _opencv_highgui_available is not None:
        return _opencv_highgui_available
    try:
        cv2.namedWindow("__pyla_gui_check__", cv2.WINDOW_NORMAL)
        cv2.destroyWindow("__pyla_gui_check__")
        _opencv_highgui_available = True
    except cv2.error:
        _opencv_highgui_available = False
    return _opencv_highgui_available


def visual_debug_backend_name():
    if opencv_highgui_available():
        return "opencv"
    if sys.platform == "win32":
        return "win32"
    return "unavailable"


def warn_missing_opencv_highgui_once():
    global _opencv_highgui_warned
    if _opencv_highgui_warned:
        return
    _opencv_highgui_warned = True
    print(
        "Visual debug: OpenCV GUI is unavailable (opencv-python-headless is installed). "
        f"Using fallback window. Fix: {OPENCV_REPAIR_CMD}"
    )


def log_visual_debug_startup():
    backend = visual_debug_backend_name()
    opencv_status = "ok" if opencv_highgui_available() else "headless"
    print(f"[VisualDebug] enabled; backend={backend}; OpenCV GUI: {opencv_status}")
    if backend == "unavailable":
        print(f"[VisualDebug] No display backend available. Fix: {OPENCV_REPAIR_CMD}")


def show_visual_debug_frame(img):
    if opencv_highgui_available():
        cv2.imshow("PylaAi-XXZ Visual Debug", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        cv2.waitKey(1)
        return
    warn_missing_opencv_highgui_once()
    if sys.platform == "win32":
        Win32VisualDebugWindow.instance().show(img)
        return
    print(f"[VisualDebug] No display backend on this platform. Fix: {OPENCV_REPAIR_CMD}")


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32

    WS_OVERLAPPEDWINDOW = 0x00CF0000
    CW_USEDEFAULT = 0x80000000
    SW_SHOW = 5
    WM_DESTROY = 0x0002
    WM_ERASEBKGND = 0x0014
    PM_REMOVE = 0x0001
    BI_RGB = 0
    DIB_RGB_COLORS = 0
    SRCCOPY = 0x00CC0020
    IDC_ARROW = 32512
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    ERROR_CLASS_ALREADY_EXISTS = 1410

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", BITMAPINFOHEADER),
        ]

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class Win32VisualDebugWindow:
        """Native Win32 fallback when OpenCV HighGUI is unavailable."""

        _lock = threading.Lock()
        _instance = None
        _class_name = "PylaAiVisualDebugWindow"

        def __init__(self):
            self._frame_queue = queue.Queue(maxsize=1)
            self._ready = threading.Event()
            self._stop = False
            self._hwnd = None
            self._wnd_proc = WNDPROC(self._window_proc)
            self._thread = threading.Thread(
                target=self._run,
                name="PylaWin32VisualDebug",
                daemon=True,
            )
            self._thread.start()
            if not self._ready.wait(timeout=5.0):
                print("[VisualDebug] Win32 window did not start within 5s.")

        @classmethod
        def instance(cls):
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                return cls._instance

        def show(self, rgb_image):
            if self._hwnd is None:
                return
            while True:
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    break
            try:
                self._frame_queue.put_nowait(np.ascontiguousarray(rgb_image))
            except queue.Full:
                pass

        def _window_proc(self, hwnd, msg, wparam, lparam):
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            if msg == WM_ERASEBKGND:
                return 1
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        def _run(self):
            try:
                self._message_loop()
            except Exception as exc:
                print(f"[VisualDebug] Win32 window failed: {exc}")

        def _message_loop(self):
            hinstance = kernel32.GetModuleHandleW(None)

            wc = WNDCLASSW()
            wc.lpfnWndProc = self._wnd_proc
            wc.hInstance = hinstance
            wc.lpszClassName = self._class_name
            wc.hCursor = user32.LoadCursorW(None, IDC_ARROW)
            wc.hbrBackground = gdi32.GetStockObject(5)

            if not user32.RegisterClassW(ctypes.byref(wc)):
                if kernel32.GetLastError() != ERROR_CLASS_ALREADY_EXISTS:
                    raise OSError(f"RegisterClassW failed with error {kernel32.GetLastError()}")

            hwnd = user32.CreateWindowExW(
                0,
                self._class_name,
                "PylaAi-XXZ Visual Debug",
                WS_OVERLAPPEDWINDOW,
                CW_USEDEFAULT,
                CW_USEDEFAULT,
                960,
                640,
                None,
                None,
                hinstance,
                None,
            )
            if not hwnd:
                raise OSError(f"CreateWindowExW failed with error {kernel32.GetLastError()}")

            self._hwnd = hwnd
            user32.ShowWindow(hwnd, SW_SHOW)
            user32.UpdateWindow(hwnd)
            self._ready.set()

            msg = wintypes.MSG()
            while not self._stop:
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_DESTROY:
                        return
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))

                try:
                    img = self._frame_queue.get(timeout=0.033)
                except queue.Empty:
                    continue
                self._blit_frame(hwnd, img)

        def _blit_frame(self, hwnd, rgb_image):
            h, w = rgb_image.shape[:2]
            user32.SetWindowPos(hwnd, None, 0, 0, w + 16, h + 39, SWP_NOMOVE | SWP_NOZORDER)

            hdc = user32.GetDC(hwnd)
            if not hdc:
                return
            try:
                bgr = np.ascontiguousarray(rgb_image[:, :, ::-1])
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = w
                bmi.bmiHeader.biHeight = -h
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 24
                bmi.bmiHeader.biCompression = BI_RGB
                gdi32.StretchDIBits(
                    hdc,
                    0,
                    0,
                    w,
                    h,
                    0,
                    0,
                    w,
                    h,
                    bgr.ctypes.data,
                    ctypes.byref(bmi),
                    DIB_RGB_COLORS,
                    SRCCOPY,
                )
            finally:
                user32.ReleaseDC(hwnd, hdc)

else:

    class Win32VisualDebugWindow:
        @classmethod
        def instance(cls):
            raise RuntimeError("Win32VisualDebugWindow is only available on Windows")

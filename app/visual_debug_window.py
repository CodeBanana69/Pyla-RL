"""Visual debug window backends for PylaAi-XXZ."""

import queue
import sys
import threading

import cv2
import numpy as np

_opencv_highgui_available = None
_opencv_highgui_warned = False
_opencv_window_ready = False
_cached_primary_monitor_rect = None
_letterbox_canvas_cache = {}

VISUAL_DEBUG_WINDOW_NAME = "PylaAi-XXZ Visual Debug"

OPENCV_REPAIR_CMD = (
    "pip uninstall -y opencv-python-headless && pip install --no-deps opencv-python==4.8.0.76"
)


def reset_opencv_highgui_cache():
    global _opencv_highgui_available, _opencv_window_ready, _cached_primary_monitor_rect
    _opencv_highgui_available = None
    _opencv_window_ready = False
    _cached_primary_monitor_rect = None


def _primary_monitor_rect():
    """Return (left, top, width, height) for the primary monitor work area."""
    global _cached_primary_monitor_rect
    if _cached_primary_monitor_rect is not None:
        return _cached_primary_monitor_rect
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    rect = RECT()
    if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
        _cached_primary_monitor_rect = (
            int(rect.left),
            int(rect.top),
            int(rect.right - rect.left),
            int(rect.bottom - rect.top),
        )
        return _cached_primary_monitor_rect
    _cached_primary_monitor_rect = (
        0,
        0,
        int(user32.GetSystemMetrics(0)),
        int(user32.GetSystemMetrics(1)),
    )
    return _cached_primary_monitor_rect


def _display_target_size(image_width, image_height):
    rect = _primary_monitor_rect()
    if rect:
        return rect[2], rect[3]
    return max(1, int(image_width)), max(1, int(image_height))


def _letterbox_canvas(target_w, target_h):
    key = (target_w, target_h)
    canvas = _letterbox_canvas_cache.get(key)
    if canvas is None:
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        _letterbox_canvas_cache[key] = canvas
    canvas.fill(0)
    return canvas


def _fit_image_to_rect(rgb_image, target_w, target_h, allow_upscale=False):
    """Fit image into target rect with aspect ratio preserved; letterbox on black canvas."""
    target_w = max(1, int(target_w))
    target_h = max(1, int(target_h))
    if rgb_image is None or rgb_image.size == 0:
        return np.zeros((target_h, target_w, 3), dtype=np.uint8)

    source_h, source_w = rgb_image.shape[:2]
    if source_w <= 0 or source_h <= 0:
        return np.zeros((target_h, target_w, 3), dtype=np.uint8)

    scale = min(target_w / source_w, target_h / source_h)
    if not allow_upscale:
        scale = min(1.0, scale)
    fitted_w = max(1, int(round(source_w * scale)))
    fitted_h = max(1, int(round(source_h * scale)))
    if fitted_w == source_w and fitted_h == source_h:
        resized = rgb_image
    else:
        resized = cv2.resize(rgb_image, (fitted_w, fitted_h), interpolation=cv2.INTER_LINEAR)

    if fitted_w == target_w and fitted_h == target_h:
        return resized

    canvas = _letterbox_canvas(target_w, target_h)
    x0 = (target_w - fitted_w) // 2
    y0 = (target_h - fitted_h) // 2
    canvas[y0 : y0 + fitted_h, x0 : x0 + fitted_w] = resized
    return canvas


def _ensure_opencv_debug_window(target_w, target_h):
    global _opencv_window_ready
    if _opencv_window_ready:
        return
    cv2.namedWindow(VISUAL_DEBUG_WINDOW_NAME, cv2.WINDOW_NORMAL)
    rect = _primary_monitor_rect()
    if rect:
        left, top, width, height = rect
        cv2.moveWindow(VISUAL_DEBUG_WINDOW_NAME, left, top)
        cv2.resizeWindow(VISUAL_DEBUG_WINDOW_NAME, width, height)
    else:
        cv2.resizeWindow(VISUAL_DEBUG_WINDOW_NAME, target_w, target_h)
    _opencv_window_ready = True


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
        target_w, target_h = _display_target_size(img.shape[1], img.shape[0])
        _ensure_opencv_debug_window(target_w, target_h)
        cv2.imshow(VISUAL_DEBUG_WINDOW_NAME, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
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
    SW_SHOW = 5
    WM_DESTROY = 0x0002
    WM_ERASEBKGND = 0x0014
    PM_REMOVE = 0x0001
    BI_RGB = 0
    DIB_RGB_COLORS = 0
    SRCCOPY = 0x00CC0020
    IDC_ARROW = 32512
    ERROR_CLASS_ALREADY_EXISTS = 1410

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

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

            monitor = _primary_monitor_rect()
            if monitor:
                win_x, win_y, client_w, client_h = monitor
            else:
                win_x, win_y, client_w, client_h = 0, 0, 960, 640

            window_rect = RECT(win_x, win_y, win_x + client_w, win_y + client_h)
            user32.AdjustWindowRect(ctypes.byref(window_rect), WS_OVERLAPPEDWINDOW, False)
            outer_w = window_rect.right - window_rect.left
            outer_h = window_rect.bottom - window_rect.top

            hwnd = user32.CreateWindowExW(
                0,
                self._class_name,
                VISUAL_DEBUG_WINDOW_NAME,
                WS_OVERLAPPEDWINDOW,
                window_rect.left,
                window_rect.top,
                outer_w,
                outer_h,
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
            client = RECT()
            user32.GetClientRect(hwnd, ctypes.byref(client))
            dest_w = client.right - client.left
            dest_h = client.bottom - client.top
            if dest_w <= 0 or dest_h <= 0:
                return

            source_h, source_w = rgb_image.shape[:2]
            if source_w > dest_w or source_h > dest_h:
                rgb_image = _fit_image_to_rect(rgb_image, dest_w, dest_h, allow_upscale=False)
                source_h, source_w = rgb_image.shape[:2]

            dest_x = max(0, (dest_w - source_w) // 2)
            dest_y = max(0, (dest_h - source_h) // 2)

            hdc = user32.GetDC(hwnd)
            if not hdc:
                return
            try:
                brush = gdi32.CreateSolidBrush(0x000000)
                if brush:
                    fill = RECT(0, 0, dest_w, dest_h)
                    user32.FillRect(hdc, ctypes.byref(fill), brush)
                    gdi32.DeleteObject(brush)
                bgr = np.ascontiguousarray(rgb_image[:, :, ::-1])
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = source_w
                bmi.bmiHeader.biHeight = -source_h
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 24
                bmi.bmiHeader.biCompression = BI_RGB
                gdi32.StretchDIBits(
                    hdc,
                    dest_x,
                    dest_y,
                    source_w,
                    source_h,
                    0,
                    0,
                    source_w,
                    source_h,
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

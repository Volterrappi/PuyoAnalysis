"""Capture only the visible client area of the dedicated YouTube WebView window.

No stream downloads or protected-frame extraction. The player must be visible.
"""
import sys
from contextlib import contextmanager


@contextmanager
def cursor_away_from_player(hwnd):
    """Temporarily move the cursor off the video, then restore its position.

    Hover controls in YouTube are hidden after the pointer leaves the iframe.
    Only the cursor is moved; no video playback state is changed.
    """
    if sys.platform != "win32":
        yield
        return
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    previous = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(previous)):
        yield
        return
    try:
        # Move to the screen corner, but only if the cursor is currently over
        # the player. Avoid moving the user cursor needlessly.
        left, top, right, bottom = client_bounds(hwnd)
        if left <= previous.x < right and top <= previous.y < bottom:
            bounds = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(bounds))
            destination = (max(0, bounds.left - 12), max(0, bounds.top - 12))
            # If the window starts at (0,0), move to the opposite corner.
            if left <= destination[0] < right and top <= destination[1] < bottom:
                destination = (right + 12, bottom + 12)
            user32.SetCursorPos(*destination)
        yield
    finally:
        user32.SetCursorPos(previous.x, previous.y)


PLAYER_TITLE = 'YouTube | ぷよぷよ振り返り'


def find_player_window(title=PLAYER_TITLE):
    if sys.platform != 'win32':
        raise RuntimeError('YouTubeウィンドウのキャプチャはWindows専用です')
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    handles = []
    cb_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @cb_type
    def visit(hwnd, unused):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value == title:
            handles.append(hwnd)
        return True

    user32.EnumWindows(visit, 0)
    if not handles:
        raise RuntimeError('YouTube再生ウィンドウが見つかりません。再生画面を開いてください。')
    return handles[0]


def client_bounds(hwnd):
    """Return client rectangle in physical desktop pixels (left, top, right, bottom)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    class POINT(ctypes.Structure):
        _fields_ = [('x', wintypes.LONG), ('y', wintypes.LONG)]

    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError('YouTubeウィンドウのサイズを取得できません')
    point = POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise RuntimeError('YouTubeウィンドウの位置を取得できません')
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width < 200 or height < 200:
        raise RuntimeError('YouTubeウィンドウが小さすぎます。最大化して再試行してください。')
    return (point.x, point.y, point.x + width, point.y + height)


def capture_player(hwnd=None, embedded=False):
    """Grab the on-screen WebView client area, not the full desktop."""
    import ctypes
    import time
    from PIL import ImageGrab
    hwnd = hwnd or find_player_window()
    user32 = ctypes.windll.user32
    if not embedded and user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if not embedded:
        user32.SetForegroundWindow(hwnd)
    with cursor_away_from_player(hwnd):
        # Give YouTube hover controls time to fade away before grabbing.
        time.sleep(1.5)
        return ImageGrab.grab(bbox=client_bounds(hwnd), all_screens=True)

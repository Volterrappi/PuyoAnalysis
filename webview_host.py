"""Best-effort Windows WebView2 window hosting inside a Tk native frame.

This keeps the official YouTube iframe inside the Edge WebView2-backed pywebview
window. Windows window-parenting is still experimental; fallback is standalone.
"""
import os
import sys

TITLE = 'YouTube | ぷよぷよ振り返り'
ORIGINAL_STYLES = {}

def original_style_for(hwnd):
    return ORIGINAL_STYLES.get(hwnd)



def attach_to_host(host_hwnd, title=TITLE):
    """Attach the *current process* player window to an existing Tk HWND.

    Returns (player_hwnd, attached). Called after pywebview signals shown,
    avoiding the parent process racing the window creation.
    """
    if sys.platform != 'win32' or not host_hwnd:
        return (0, False)
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    user32.SetWindowLongW.restype = wintypes.LONG
    user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    user32.SetParent.restype = wintypes.HWND
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    matches = []
    cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    @cb
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != os.getpid():
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            title_buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buffer, length + 1)
            if title_buffer.value == title:
                matches.append(hwnd)
        return True
    user32.EnumWindows(visit, 0)
    if not matches or not user32.IsWindow(host_hwnd):
        return (0, False)
    hwnd = matches[0]
    old = user32.GetWindowLongW(hwnd, -16)
    ORIGINAL_STYLES[hwnd] = old
    # WS_CHILD, strip popup/title/resizing flags.
    new = (old | 0x40000000) & ~(0x80000000 | 0x00C00000 | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000)
    user32.SetWindowLongW(hwnd, -16, new)
    ctypes.set_last_error(0)
    user32.SetParent(hwnd, host_hwnd)
    # Verify the resulting parent instead of relying on last_error (Win32 does
    # not always propagate it through ctypes.windll).
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    if user32.GetParent(hwnd) != host_hwnd:
        user32.SetWindowLongW(hwnd, -16, old)
        return (hwnd, False)
    user32.SetWindowPos(hwnd, 0, 0, 0, 640, 360, 0x0024)  # FRAMECHANGED | NOZORDER
    return (hwnd, True)

"""Optional Windows-only docking of a pywebview window into a Tk frame.

This uses Win32 SetParent on a separate process. It is deliberately optional:
users can undock to the previously tested separate-window mode.
"""
import sys


def available():
    return sys.platform == 'win32'


class Dock:
    def __init__(self, host, pid):
        self.host = host
        self.pid = pid
        self.hwnd = None
        self.original_style = None
        self.original_parent = None
        self._job = None

    def attach(self):
        if not available():
            return False
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        matches = []
        @CALLBACK
        def enum(hwnd, _):
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == self.pid and u.IsWindowVisible(hwnd):
                n = u.GetWindowTextLengthW(hwnd)
                if n:
                    title = ctypes.create_unicode_buffer(n + 1)
                    u.GetWindowTextW(hwnd, title, n + 1)
                    if title.value == 'YouTube | ぷよぷよ振り返り':
                        matches.append(hwnd)
            return True
        u.EnumWindows(enum, 0)
        if not matches:
            return False
        hwnd = matches[0]
        GWL_STYLE = -16
        WS_CHILD = 0x40000000
        WS_POPUP = 0x80000000
        WS_CAPTION = 0x00C00000
        WS_THICKFRAME = 0x00040000
        WS_SYSMENU = 0x00080000
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        # On 64-bit Windows, GetWindowLongW is sufficient for the 32-bit style.
        u.GetWindowLongW.restype = wintypes.LONG
        old = u.GetWindowLongW(hwnd, GWL_STYLE)
        new = (old | WS_CHILD) & ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
        u.SetWindowLongW(hwnd, GWL_STYLE, new)
        ctypes.set_last_error(0)
        u.SetParent(hwnd, self.host.winfo_id())
        if ctypes.get_last_error():
            u.SetWindowLongW(hwnd, GWL_STYLE, old)
            return False
        self.hwnd = hwnd
        self.original_style = old
        self.host.bind('<Configure>', self.resize, add='+')
        self.resize()
        return True

    def adopt(self, hwnd, original_style=None):
        """Track a child window already attached by the WebView2 process."""
        self.hwnd = hwnd
        self.original_style = original_style
        self.host.bind('<Configure>', self.resize, add='+')

    def attach_handle(self, hwnd):
        """Reattach the known HWND after detaching; do not search by title."""
        if not available() or not hwnd:
            return False
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.IsWindow.argtypes = [wintypes.HWND]
        u.IsWindow.restype = wintypes.BOOL
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = wintypes.LONG
        u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
        u.SetWindowLongW.restype = wintypes.LONG
        u.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        u.SetParent.restype = wintypes.HWND
        u.GetParent.argtypes = [wintypes.HWND]
        u.GetParent.restype = wintypes.HWND
        if not u.IsWindow(hwnd):
            return False
        old = u.GetWindowLongW(hwnd, -16)
        child_style = (old | 0x40000000) & ~(0x80000000 | 0x00C00000 | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000)
        u.SetWindowLongW(hwnd, -16, child_style)
        host_hwnd = self.host.winfo_id()
        u.SetParent(hwnd, host_hwnd)
        if u.GetParent(hwnd) != host_hwnd:
            u.SetWindowLongW(hwnd, -16, old)
            return False
        self.hwnd = hwnd
        self.original_style = old
        u.SetWindowPos(hwnd, 0, 0, 0, max(1,self.host.winfo_width()), max(1,self.host.winfo_height()), 0x0024)
        self.host.bind('<Configure>', self.resize, add='+')
        return True

    def resize(self, event=None):
        if not self.hwnd:
            return
        import ctypes
        u = ctypes.windll.user32
        if not u.IsWindow(self.hwnd):
            self.hwnd = None
            return
        w = max(1, self.host.winfo_width())
        h = max(1, self.host.winfo_height())
        u.SetWindowPos(self.hwnd, 0, 0, 0, w, h, 0x0014)  # NOZORDER | NOACTIVATE

    def detach(self):
        """Restore a real top-level window, including caption and system buttons."""
        if not self.hwnd or not available():
            return
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        hwnd = self.hwnd
        self.hwnd = None
        if not u.IsWindow(hwnd):
            return
        # Style must be restored even if the child process originally docked
        # itself (adopt() then has no locally saved pre-docking style).
        WS_CHILD = 0x40000000
        WS_POPUP = 0x80000000
        WS_CAPTION = 0x00C00000
        WS_THICKFRAME = 0x00040000
        WS_SYSMENU = 0x00080000
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        WS_OVERLAPPEDWINDOW = (WS_CAPTION | WS_THICKFRAME | WS_SYSMENU |
                               WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = wintypes.LONG
        u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
        u.SetWindowLongW.restype = wintypes.LONG
        u.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        u.SetParent.restype = wintypes.HWND
        current = u.GetWindowLongW(hwnd, -16)
        if self.original_style is not None:
            restored = int(self.original_style)
        else:
            restored = (current & ~(WS_CHILD | WS_POPUP)) | WS_OVERLAPPEDWINDOW
        # Make it a top-level window first, then restore all non-client styles.
        u.SetParent(hwnd, None)
        u.SetWindowLongW(hwnd, -16, restored)
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        SWP_SHOWWINDOW = 0x0040
        u.SetWindowPos(hwnd, 0, 120, 120, 1060, 750,
                       SWP_NOZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW)
        u.ShowWindow(hwnd, 5)

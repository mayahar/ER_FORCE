from __future__ import annotations

import ctypes
from ctypes import wintypes


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


MONITORINFOF_PRIMARY = 1
MONITORS: list[dict] = []


def _monitor_callback(hmonitor, _hdc, _rect, _data) -> int:
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
        return 1

    rect = info.rcMonitor
    MONITORS.append(
        {
            "index": len(MONITORS),
            "device": info.szDevice,
            "primary": bool(info.dwFlags & MONITORINFOF_PRIMARY),
            "left": rect.left,
            "top": rect.top,
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top,
        }
    )
    return 1


def list_displays() -> list[dict]:
    MONITORS.clear()
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.POINTER(RECT),
        ctypes.c_longlong,
    )
    ctypes.windll.user32.EnumDisplayMonitors(0, 0, callback_type(_monitor_callback), 0)
    return list(MONITORS)


def main() -> int:
    monitors = list_displays()
    if not monitors:
        print("No displays detected.")
        return 1

    print("Windows displays for Tobii display-area mapping:")
    for monitor in monitors:
        role = "primary" if monitor["primary"] else "secondary"
        print(
            f"  [{monitor['index']}] {monitor['device']} ({role}) "
            f"{monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']})"
        )

    primary = next((m for m in monitors if m["primary"]), monitors[0])
    print("")
    print("FlightGear fullscreen should use the same monitor you select in Tobii Pro Eye Tracker Manager.")
    print(
        f"Recommended mapping target: monitor [{primary['index']}] "
        f"{primary['width']}x{primary['height']} ({primary['device']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

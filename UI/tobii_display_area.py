"""Configure Tobii active display area to match the Qt screen used for calibration/game."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication, QScreen

from tobii_research import DisplayArea
from tobii_research import CAPABILITY_CAN_SET_DISPLAY_AREA


def screen_physical_size_mm(screen: QScreen) -> tuple[float, float]:
    geom = screen.geometry()
    dpi = float(screen.physicalDotsPerInch())
    if dpi <= 1.0:
        dpi = float(screen.logicalDotsPerInch())
    if dpi <= 1.0:
        dpi = 96.0
    width_mm = max(1.0, geom.width() / dpi * 25.4)
    height_mm = max(1.0, geom.height() / dpi * 25.4)
    return width_mm, height_mm


def _display_area_from_existing(existing: DisplayArea, width_mm: float, height_mm: float) -> DisplayArea:
    """Keep ETM position/orientation, update size to match current monitor."""
    tl = existing.top_left
    tr = existing.top_right
    bl = existing.bottom_left

    # Preserve horizontal axis direction and Z plane from tracker setup.
    ux = tr[0] - tl[0]
    uy = tr[1] - tl[1]
    uz = tr[2] - tl[2]
    u_len = (ux * ux + uy * uy + uz * uz) ** 0.5
    if u_len < 1.0:
        ux, uy, uz, u_len = width_mm, 0.0, 0.0, width_mm
    ux, uy, uz = ux / u_len * width_mm, uy / u_len * width_mm, uz / u_len * width_mm

    vx = bl[0] - tl[0]
    vy = bl[1] - tl[1]
    vz = bl[2] - tl[2]
    v_len = (vx * vx + vy * vy + vz * vz) ** 0.5
    if v_len < 1.0:
        vx, vy, vz, v_len = 0.0, -height_mm, 0.0, height_mm
    vx, vy, vz = vx / v_len * height_mm, vy / v_len * height_mm, vz / v_len * height_mm

    return DisplayArea(
        {
            "top_left": tl,
            "top_right": (tl[0] + ux, tl[1] + uy, tl[2] + uz),
            "bottom_left": (tl[0] + vx, tl[1] + vy, tl[2] + vz),
        }
    )


def _default_display_area_below_tracker(width_mm: float, height_mm: float) -> DisplayArea:
    """UCS: Y points up, so bottom of screen is below top (smaller Y)."""
    half_w = width_mm / 2.0
    return DisplayArea(
        {
            "top_left": (-half_w, 0.0, 0.0),
            "top_right": (half_w, 0.0, 0.0),
            "bottom_left": (-half_w, -height_mm, 0.0),
        }
    )


def apply_display_area_for_screen(eyetracker, screen: QScreen | None) -> tuple[bool, str]:
    """Map Tobii gaze (ADCS 0–1) to the monitor used for calibration/game."""
    if screen is None:
        return False, "no screen for display-area mapping"

    capabilities = getattr(eyetracker, "device_capabilities", ())
    if CAPABILITY_CAN_SET_DISPLAY_AREA not in capabilities:
        return False, "eye tracker does not support set_display_area"

    width_mm, height_mm = screen_physical_size_mm(screen)
    geom = screen.geometry()

    try:
        existing = eyetracker.get_display_area()
        if existing.width > 50.0 and existing.height > 50.0:
            display_area = _display_area_from_existing(existing, width_mm, height_mm)
            mode = "ETM geometry, resized to screen"
        else:
            display_area = _default_display_area_below_tracker(width_mm, height_mm)
            mode = "default below-tracker geometry"
    except Exception:
        display_area = _default_display_area_below_tracker(width_mm, height_mm)
        mode = "default below-tracker geometry (no prior area)"

    eyetracker.set_display_area(display_area)
    return (
        True,
        f"{mode}: {width_mm:.0f}x{height_mm:.0f} mm, "
        f"screen {geom.width()}x{geom.height()} at ({geom.x()}, {geom.y()})",
    )

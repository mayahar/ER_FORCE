"""Fullscreen Tobii calibration: head position → 5-point dots → fixation preview."""

from __future__ import annotations

import math
from pathlib import Path

import tobii_research as tr
from PySide6.QtCore import Qt, QTimer, Signal, QEventLoop, QRectF
from PySide6.QtGui import (
    QFont,
    QGuiApplication,
    QPainter,
    QColor,
    QPen,
    QPixmap,
    QImage,
)
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from tobii_research import (
    CALIBRATION_STATUS_FAILURE,
    CALIBRATION_STATUS_SUCCESS,
    CALIBRATION_STATUS_SUCCESS_LEFT_EYE,
    CALIBRATION_STATUS_SUCCESS_RIGHT_EYE,
    VALIDITY_VALID_AND_USED,
    ScreenBasedCalibration,
)

# Same order as Tobii SDK calibration example (center, then corners).
DEFAULT_CALIBRATION_POINTS = (
    (0.5, 0.5),
    (0.1, 0.1),
    (0.1, 0.9),
    (0.9, 0.1),
    (0.9, 0.9),
)

DOT_LOOK_MS = 2000
DOT_COLLECT_DELAY_MS = 80
DOT_EXPLODE_MS = 550
DOT_GAP_MS = 400
COLLECT_PASSES_PER_POINT = 1
DOT_COLLECT_RETRIES = 3
DOT_EXPLODE_PARTICLES = 18

LEFT_EYE_COLOR = QColor("#42a5f5")
RIGHT_EYE_COLOR = QColor("#66bb6a")

SUCCESS_STATUSES = {
    CALIBRATION_STATUS_SUCCESS,
    CALIBRATION_STATUS_SUCCESS_LEFT_EYE,
    CALIBRATION_STATUS_SUCCESS_RIGHT_EYE,
}

HEAD_HOLD_SECONDS = 4.0
POSITION_POLL_MS = 50
HEAD_POSITION_SMOOTH_ALPHA = 0.12
HEAD_BAD_STREAK_BEFORE_DECAY = 5
HEAD_MISSING_GRACE_TICKS = 8
HEAD_HOLD_DECAY_PER_SEC = 0.5
HEAD_DISPLAY_XY_ALPHA = 0.10
HEAD_DISPLAY_Z_ALPHA = 0.10

# Tobii user-position ideal is near (0.5, 0.5, ~0.55) when head is well placed.
HEAD_X_INNER = (0.44, 0.56)
HEAD_Y_INNER = (0.42, 0.58)
HEAD_Z_INNER = (0.48, 0.64)
HEAD_X_OUTER = (0.36, 0.64)
HEAD_Y_OUTER = (0.34, 0.66)
HEAD_Z_OUTER = (0.42, 0.70)
HEAD_Z_TARGET = 0.56


def _parse_position_guide(
    data,
) -> tuple[float | None, float | None, float | None, bool, str]:
    """Average valid left/right user position; return (x, y, z, ok, distance_hint)."""
    if isinstance(data, dict):
        left = data.get("left_user_position")
        right = data.get("right_user_position")
        left_ok = bool(data.get("left_user_position_validity"))
        right_ok = bool(data.get("right_user_position_validity"))
    else:
        left = data.left_eye.user_position if data.left_eye.validity else None
        right = data.right_eye.user_position if data.right_eye.validity else None
        left_ok = data.left_eye.validity
        right_ok = data.right_eye.validity

    points = []
    if left_ok and left:
        points.append(left)
    if right_ok and right:
        points.append(right)
    if not points:
        return None, None, None, False, ""

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points if len(p) > 2]
    x = sum(xs) / len(xs)
    y = sum(ys) / len(ys)
    z = sum(zs) / len(zs) if zs else 0.55

    return x, y, z, False, ""


def _in_box(
    x: float, y: float, z: float, xr: tuple[float, float], yr: tuple[float, float], zr: tuple[float, float]
) -> bool:
    return xr[0] <= x <= xr[1] and yr[0] <= y <= yr[1] and zr[0] <= z <= zr[1]


def _distance_hint_for_z(z: float) -> str:
    if z > HEAD_Z_INNER[0]:
        return "forward"
    if z < HEAD_Z_INNER[1]:
        return "back"
    return ""


def _movement_hint_for_position(x: float, y: float, z: float) -> str:
    distance_hint = _distance_hint_for_z(z)
    if distance_hint:
        return distance_hint
    if x > HEAD_X_INNER[0]:
        return "right"
    if x < HEAD_X_INNER[1]:
        return "left"
    if y > HEAD_Y_INNER[0]:
        return "up"
    if y < HEAD_Y_INNER[1]:
        return "down"
    return "center"


class HeadPositionSmoother:
    """EMA + hysteresis so the guide stays stable and the hold bar does not jump."""

    def __init__(self) -> None:
        self._x: float | None = None
        self._y: float | None = None
        self._z: float | None = None
        self._hold_seconds = 0.0
        self._bad_streak = 0
        self._missing_streak = 0
        self._ok_latched = False

    @property
    def hold_seconds(self) -> float:
        return self._hold_seconds

    def reset(self) -> None:
        self._x = None
        self._y = None
        self._z = None
        self._hold_seconds = 0.0
        self._bad_streak = 0
        self._missing_streak = 0
        self._ok_latched = False

    def _update_ok_latch(self, x: float, y: float, z: float) -> bool:
        if self._ok_latched:
            if _in_box(x, y, z, HEAD_X_OUTER, HEAD_Y_OUTER, HEAD_Z_OUTER):
                return True
            self._ok_latched = False
            return False
        if _in_box(x, y, z, HEAD_X_INNER, HEAD_Y_INNER, HEAD_Z_INNER):
            self._ok_latched = True
            return True
        return False

    def update(
        self, raw_x: float | None, raw_y: float | None, raw_z: float | None, dt: float
    ) -> tuple[float | None, float | None, float | None, bool, str]:
        if raw_x is None or raw_y is None or raw_z is None:
            self._missing_streak += 1
            self._bad_streak += 1
            if self._missing_streak >= HEAD_MISSING_GRACE_TICKS:
                self._decay_hold(dt)
            if self._x is None:
                return None, None, None, False, ""
            ok = self._update_ok_latch(self._x, self._y, self._z)
            hint = "" if ok else _movement_hint_for_position(self._x, self._y, self._z)
            return self._x, self._y, self._z, ok, hint

        self._missing_streak = 0
        alpha = HEAD_POSITION_SMOOTH_ALPHA
        if self._x is None:
            self._x, self._y, self._z = raw_x, raw_y, raw_z
        else:
            self._x = alpha * raw_x + (1.0 - alpha) * self._x
            self._y = alpha * raw_y + (1.0 - alpha) * self._y
            self._z = alpha * raw_z + (1.0 - alpha) * self._z

        ok = self._update_ok_latch(self._x, self._y, self._z)
        if ok:
            self._bad_streak = 0
            self._hold_seconds = min(HEAD_HOLD_SECONDS, self._hold_seconds + dt)
        else:
            self._bad_streak += 1
            if self._bad_streak >= HEAD_BAD_STREAK_BEFORE_DECAY:
                self._decay_hold(dt)

        hint = "" if ok else _movement_hint_for_position(self._x, self._y, self._z)
        return self._x, self._y, self._z, ok, hint

    def _decay_hold(self, dt: float) -> None:
        self._hold_seconds = max(0.0, self._hold_seconds - dt * HEAD_HOLD_DECAY_PER_SEC)


def _draw_head_figure(
    painter: QPainter,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    color: QColor,
    *,
    glow: bool = True,
    line_width: int = 3,
    fill_alpha: int = 0,
) -> None:
    """Simple oval guide for head position."""
    head_rect = QRectF(cx - rx, cy - ry, rx * 2, ry * 2)

    if glow:
        for extra, alpha in ((12, 20), (8, 40), (4, 65)):
            glow_color = QColor(color)
            glow_color.setAlpha(alpha)
            painter.setPen(
                QPen(glow_color, line_width + extra, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(head_rect)

    painter.setPen(QPen(color, line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    if fill_alpha > 0:
        fill = QColor(color)
        fill.setAlpha(fill_alpha)
        painter.setBrush(fill)
    else:
        painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(head_rect)


class HeadPositionCanvas(QWidget):
    """Oval guide: fit your head inside; turns green when ready."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user_ok = False
        self._distance_hint = ""
        self._hold_ratio = 0.0
        self._display_x: float | None = None
        self._display_y: float | None = None
        self._display_z: float | None = None

    def reset_display(self) -> None:
        self._display_x = None
        self._display_y = None
        self._display_z = None

    def _smooth_display(self, attr: str, value: float, alpha: float) -> None:
        current = getattr(self, attr)
        if current is None:
            setattr(self, attr, value)
        else:
            setattr(self, attr, alpha * value + (1.0 - alpha) * current)

    def _guide_colors(self) -> tuple[QColor, QColor]:
        if self._user_ok:
            return QColor("#66bb6a"), QColor("#a5d6a7")
        if self._distance_hint:
            return QColor("#ffb74d"), QColor("#ffe0b2")
        return QColor("#5eb8ff"), QColor("#90caf9")

    def _instruction_text(self) -> str:
        if self._user_ok:
            return "להישאר יציב/ה - כמעט מוכנים."
        instructions = {
            "forward": "להתקרב מעט למסך.",
            "back": "להתרחק מעט מהמסך.",
            "left": "לזוז מעט שמאלה.",
            "right": "לזוז מעט ימינה.",
            "up": "לעלות מעט למעלה.",
            "down": "לרדת מעט למטה.",
            "center": "להתמקם במרכז האליפסה.",
        }
        return instructions.get(
            self._distance_hint,
            "להתאים את הראש לאליפסה עד שהיא הופכת לירוקה.",
        )

    def update_position(
        self,
        x: float | None,
        y: float | None,
        z: float | None,
        ok: bool,
        distance_hint: str = "",
        hold_ratio: float = 0.0,
    ) -> None:
        self._user_ok = ok
        self._distance_hint = distance_hint
        self._hold_ratio = max(0.0, min(1.0, hold_ratio))
        if x is not None:
            self._smooth_display("_display_x", x, HEAD_DISPLAY_XY_ALPHA)
        if y is not None:
            self._smooth_display("_display_y", y, HEAD_DISPLAY_XY_ALPHA)
        if z is not None:
            self._smooth_display("_display_z", z, HEAD_DISPLAY_Z_ALPHA)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#1c2333"))

        w, h = self.width(), self.height()
        panel_size = int(min(w, h) * 0.52)
        panel_x = (w - panel_size) // 2
        panel_y = int(h * 0.22)
        panel_rect = QRectF(panel_x, panel_y, panel_size, panel_size)

        title_font = QFont("Segoe UI", 20, QFont.Weight.DemiBold)
        sub_font = QFont("Segoe UI", 13)

        painter.setFont(title_font)
        painter.setPen(QColor("#b0bec5"))
        painter.drawText(0, int(h * 0.07), w, 40, Qt.AlignmentFlag.AlignHCenter, "Position and settings")
        painter.setFont(sub_font)
        painter.setPen(QColor("#90a4ae"))
        hint = self._instruction_text()
        painter.drawText(0, int(h * 0.11), w, 36, Qt.AlignmentFlag.AlignHCenter, hint)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#3a2828"))
        painter.drawRoundedRect(panel_rect, 4, 4)

        cx = panel_rect.center().x()
        cy = panel_rect.center().y()
        target_rx = panel_size * 0.22
        target_ry = panel_size * 0.30

        main_color, live_color = self._guide_colors()

        _draw_head_figure(
            painter, cx, cy, target_rx, target_ry, main_color, glow=True, line_width=3
        )

        if (
            self._display_x is not None
            and self._display_y is not None
            and self._display_z is not None
        ):
            z_scale = self._display_z / HEAD_Z_TARGET
            z_scale = max(0.55, min(1.5, z_scale))
            live_rx = target_rx * z_scale
            live_ry = target_ry * z_scale
            offset_x = (self._display_x - 0.5) * target_rx * 1.9
            offset_y = (0.5 - self._display_y) * target_ry * 1.6
            live_cx = cx + offset_x
            live_cy = cy + offset_y

            live_fill = QColor(live_color)
            live_fill.setAlpha(55)
            _draw_head_figure(
                painter,
                live_cx,
                live_cy,
                live_rx,
                live_ry,
                live_color,
                glow=False,
                line_width=2,
                fill_alpha=55,
            )

        bar_w = panel_size * 0.36
        bar_h = 5
        bar_gap = 10
        bar_y = panel_rect.bottom() - 28
        bar_x1 = cx - bar_w - bar_gap / 2
        bar_x2 = cx + bar_gap / 2
        for bar_x in (bar_x1, bar_x2):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#546e7a"))
            painter.drawRoundedRect(int(bar_x), int(bar_y), int(bar_w), bar_h, 2, 2)
            fill_w = bar_w * self._hold_ratio
            if fill_w > 1:
                painter.setBrush(main_color if self._user_ok else QColor("#5eb8ff"))
                painter.drawRoundedRect(int(bar_x), int(bar_y), int(fill_w), bar_h, 2, 2)


class CalibrationDotCanvas(QWidget):
    """Red calibration target with dwell pulse and smooth explosion after collect."""

    look_finished = Signal()
    explosion_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._norm_x = 0.5
        self._norm_y = 0.5
        self._phase = "hidden"  # hidden | looking | collecting | exploding
        self._pulse_t = 0.0
        self._explode_t = 0.0
        self._particles: list[tuple[float, float]] = []

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_animation)

        self._look_timer = QTimer(self)
        self._look_timer.setSingleShot(True)
        self._look_timer.timeout.connect(self._on_look_finished)

    def start_point(self, norm_x: float, norm_y: float) -> None:
        self._look_timer.stop()
        self._anim_timer.stop()
        self._norm_x = norm_x
        self._norm_y = norm_y
        self._phase = "looking"
        self._pulse_t = 0.0
        self._explode_t = 0.0
        self._look_timer.start(DOT_LOOK_MS)
        self._anim_timer.start()
        self.update()

    @property
    def phase(self) -> str:
        return self._phase

    def _on_look_finished(self) -> None:
        if self._phase != "looking":
            return
        self._phase = "collecting"
        self._look_timer.stop()
        self.look_finished.emit()

    def begin_explosion(self) -> None:
        if self._phase not in ("looking", "collecting"):
            return
        self._look_timer.stop()
        self._begin_explosion()

    def hide_point(self) -> None:
        self._look_timer.stop()
        self._anim_timer.stop()
        self._phase = "hidden"
        self.update()

    def _begin_explosion(self) -> None:
        self._phase = "exploding"
        self._explode_t = 0.0
        self._particles = []
        for i in range(DOT_EXPLODE_PARTICLES):
            angle = (2.0 * math.pi * i / DOT_EXPLODE_PARTICLES) + (i * 0.17)
            speed = 0.75 + (i % 5) * 0.08
            self._particles.append((angle, speed))
        self.update()

    def _tick_animation(self) -> None:
        if self._phase == "looking":
            self._pulse_t += 0.07
            self.update()
            return
        if self._phase == "exploding":
            self._explode_t += 16.0 / DOT_EXPLODE_MS
            if self._explode_t >= 1.0:
                self._phase = "hidden"
                self._anim_timer.stop()
                self.update()
                self.explosion_finished.emit()
                return
            self.update()

    @staticmethod
    def _ease_out_cubic(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return 1.0 - (1.0 - t) ** 3

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101010"))
        if self._phase == "hidden":
            return

        base_radius = max(18, min(self.width(), self.height()) // 40)
        cx = int(self._norm_x * self.width())
        cy = int(self._norm_y * self.height())
        painter.setRenderHint(QPainter.Antialiasing)

        if self._phase in ("looking", "collecting"):
            pulse = 1.0 + (0.12 if self._phase == "collecting" else 0.07) * math.sin(
                self._pulse_t
            )
            radius = int(base_radius * pulse)
            glow = QColor(229, 57, 53, 55)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(cx - radius - 8, cy - radius - 8, (radius + 8) * 2, (radius + 8) * 2)
            painter.setPen(QPen(QColor("#ffffff"), 3))
            painter.setBrush(QColor("#e53935"))
            painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
            inner = max(4, radius // 4)
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(cx - inner, cy - inner, inner * 2, inner * 2)
            return

        ease = self._ease_out_cubic(self._explode_t)
        shrink = max(2, int(base_radius * (1.0 - ease * 0.92)))
        core_alpha = int(255 * (1.0 - ease))
        if core_alpha > 0:
            core = QColor(229, 57, 53, core_alpha)
            painter.setPen(QPen(QColor(255, 255, 255, core_alpha), 2))
            painter.setBrush(core)
            painter.drawEllipse(cx - shrink, cy - shrink, shrink * 2, shrink * 2)

        ring_alpha = int(200 * (1.0 - ease))
        if ring_alpha > 0:
            ring_r = base_radius + ease * base_radius * 2.8
            painter.setPen(QPen(QColor(255, 255, 255, ring_alpha), max(1, int(3 * (1.0 - ease)))))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                int(cx - ring_r), int(cy - ring_r), int(ring_r * 2), int(ring_r * 2)
            )

        max_dist = base_radius * (2.2 + ease * 5.5)
        for angle, speed in self._particles:
            dist = max_dist * speed * ease
            px = cx + math.cos(angle) * dist
            py = cy + math.sin(angle) * dist
            size = max(2, int(base_radius * 0.22 * (1.0 - ease * 0.65)))
            alpha = int(230 * (1.0 - ease))
            if alpha <= 0:
                continue
            color = QColor(255, 120, 100, alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(int(px - size), int(py - size), size * 2, size * 2)


def _eye_gaze_samples(samples, eye_attr: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for sample in samples:
        eye = getattr(sample, eye_attr)
        if eye.validity == VALIDITY_VALID_AND_USED:
            px, py = eye.position_on_display_area
            points.append((float(px), float(py)))
    return points


def _mean_gaze(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return sum(xs) / len(xs), sum(ys) / len(ys)


class FixationMapCanvas(QWidget):
    """Calibration map: red = target; blue/green = all gaze samples per eye + mean."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._targets: list[tuple[float, float]] = []
        self._left_samples: list[list[tuple[float, float]]] = []
        self._right_samples: list[list[tuple[float, float]]] = []
        self._mean_left: list[tuple[float, float] | None] = []
        self._mean_right: list[tuple[float, float] | None] = []
        self._mean_error_px = 0.0

    def set_calibration_result(self, result, plot_size: tuple[int, int] = (400, 250)) -> None:
        self._targets = []
        self._left_samples = []
        self._right_samples = []
        self._mean_left = []
        self._mean_right = []
        self._mean_error_px = 0.0
        if result is None:
            self.update()
            return

        errors_norm: list[float] = []
        for point in getattr(result, "calibration_points", ()) or ():
            tx, ty = point.position_on_display_area
            target = (float(tx), float(ty))
            self._targets.append(target)

            samples = point.calibration_samples
            left_pts = _eye_gaze_samples(samples, "left_eye")
            right_pts = _eye_gaze_samples(samples, "right_eye")
            left_mean = _mean_gaze(left_pts)
            right_mean = _mean_gaze(right_pts)
            self._left_samples.append(left_pts)
            self._right_samples.append(right_pts)
            self._mean_left.append(left_mean)
            self._mean_right.append(right_mean)

            for mean in (left_mean, right_mean):
                if mean is not None:
                    errors_norm.append(
                        ((mean[0] - target[0]) ** 2 + (mean[1] - target[1]) ** 2) ** 0.5
                    )

        if errors_norm:
            avg_norm = sum(errors_norm) / len(errors_norm)
            self._mean_error_px = avg_norm * min(plot_size) * 0.85

        self.update()

    def render_pixmap(self, width: int = 320, height: int = 200) -> QPixmap:
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor("#1a1a1a"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_map(painter, width, height)
        painter.end()
        return QPixmap.fromImage(image)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))
        self._paint_map(painter, self.width(), self.height())

    def _paint_map(self, painter: QPainter, width: int, height: int) -> None:
        margin = 20
        plot = QRectF(margin, margin, width - 2 * margin, height - 2 * margin)

        painter.setPen(QPen(QColor("#455a64"), 1))
        painter.drawRect(plot)

        for idx, (tx, ty) in enumerate(self._targets):
            tx_px = plot.left() + tx * plot.width()
            ty_px = plot.top() + ty * plot.height()
            target_px = (tx_px, ty_px)

            left_pts = self._left_samples[idx] if idx < len(self._left_samples) else []
            right_pts = self._right_samples[idx] if idx < len(self._right_samples) else []
            left_mean = self._mean_left[idx] if idx < len(self._mean_left) else None
            right_mean = self._mean_right[idx] if idx < len(self._mean_right) else None

            self._draw_eye_cluster(
                painter, plot, target_px, left_pts, left_mean, LEFT_EYE_COLOR
            )
            self._draw_eye_cluster(
                painter, plot, target_px, right_pts, right_mean, RIGHT_EYE_COLOR
            )

        self._draw_legend(painter, width, height)

    def _draw_eye_cluster(
        self,
        painter: QPainter,
        plot: QRectF,
        target_px: tuple[float, float],
        samples: list[tuple[float, float]],
        mean: tuple[float, float] | None,
        color: QColor,
    ) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        sample_color = QColor(color)
        sample_color.setAlpha(150)
        painter.setBrush(sample_color)
        for gx, gy in samples:
            gx_px = plot.left() + gx * plot.width()
            gy_px = plot.top() + gy * plot.height()
            painter.drawEllipse(int(gx_px) - 3, int(gy_px) - 3, 6, 6)

        if mean is None:
            return
        tx_px, ty_px = target_px
        gx, gy = mean
        gx_px = plot.left() + gx * plot.width()
        gy_px = plot.top() + gy * plot.height()

        line_color = QColor(color)
        line_color.setAlpha(200)
        painter.setPen(QPen(line_color, 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(tx_px), int(ty_px), int(gx_px), int(gy_px))

        mean_color = QColor(color)
        mean_color.setAlpha(240)
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.setBrush(mean_color)
        painter.drawEllipse(int(gx_px) - 8, int(gy_px) - 8, 16, 16)

    def _draw_legend(self, painter: QPainter, width: int, height: int) -> None:
        x = 28
        y = height - 22
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)

        for label, color in (("L", LEFT_EYE_COLOR), ("R", RIGHT_EYE_COLOR)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(x, y - 6, 10, 10)
            painter.setPen(QPen(QColor("#b0bec5")))
            painter.drawText(x + 14, y + 4, label)
            x += 36


class EyeCalibrationDialog(QDialog):
    finished_calibration = Signal(bool, str)

    def __init__(self, eyetracker, parent=None, screen=None, save_dir: Path | None = None):
        super().__init__(parent)
        self.eyetracker = eyetracker
        self.target_screen = screen or QGuiApplication.primaryScreen()
        self.save_dir = save_dir
        self._points = list(DEFAULT_CALIBRATION_POINTS)
        self._point_index = 0
        self._calibration = None
        self._calibration_result = None
        self._success = False
        self._message = ""
        self._position_subscribed = False
        self._hold_seconds = 0.0
        self._latest_guide = None
        self.preview_pixmap: QPixmap | None = None
        self._pending_collect: tuple[float, float] | None = None
        self._collect_pass = 0
        self._head_smoother = HeadPositionSmoother()
        self._last_status_key = ""
        self._display_area_applied = False
        self._dot_busy = False
        self._dot_token = 0
        self._awaiting_explosion = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget(self)
        self.head_canvas = HeadPositionCanvas(self)
        self.dot_canvas = CalibrationDotCanvas(self)
        self.preview_canvas = FixationMapCanvas(self)
        self.stack.addWidget(self.head_canvas)
        self.stack.addWidget(self.dot_canvas)
        self.stack.addWidget(self.preview_canvas)
        layout.addWidget(self.stack, stretch=1)

        self.status_label = QLabel("", self)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(
            "color: white; background-color: rgba(0,0,0,160); padding: 12px; font-size: 16px;"
        )
        self.status_label.setFont(QFont("Segoe UI", 14))
        layout.addWidget(self.status_label)

        self._position_timer = QTimer(self)
        self._position_timer.setInterval(POSITION_POLL_MS)
        self._position_timer.timeout.connect(self._tick_head_position)

        self.dot_canvas.look_finished.connect(self._on_dot_look_finished)
        self.dot_canvas.explosion_finished.connect(self._on_dot_explosion_finished)

        if self.target_screen is not None:
            self.setGeometry(self.target_screen.geometry())

    def begin(self) -> None:
        self.status_label.hide()
        self._start_head_position_phase()

    def _set_status(self, text: str) -> None:
        if not self.status_label.isVisible():
            return
        self.status_label.setText(text)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def _subscribe_position_guide(self) -> bool:
        try:
            self.eyetracker.subscribe_to(
                tr.EYETRACKER_USER_POSITION_GUIDE,
                self._on_position_guide,
                as_dictionary=True,
            )
            self._position_subscribed = True
            return True
        except Exception as exc:
            self._finish(False, f"לא ניתן להפעיל מדריך מיקום ראש: {exc}")
            return False

    def _unsubscribe_position_guide(self) -> None:
        if not self._position_subscribed:
            return
        try:
            self.eyetracker.unsubscribe_from(
                tr.EYETRACKER_USER_POSITION_GUIDE,
                self._on_position_guide,
            )
        except Exception:
            pass
        self._position_subscribed = False

    def _on_position_guide(self, data) -> None:
        self._latest_guide = data

    def _apply_display_area(self) -> None:
        if self._display_area_applied:
            return
        from .tobii_display_area import apply_display_area_for_screen

        try:
            apply_display_area_for_screen(self.eyetracker, self.target_screen)
            self._display_area_applied = True
        except Exception:
            pass

    def _start_head_position_phase(self) -> None:
        self.stack.setCurrentWidget(self.head_canvas)
        self.head_canvas.reset_display()
        self._hold_seconds = 0.0
        self._head_smoother.reset()
        self._last_status_key = ""
        self._apply_display_area()
        if not self._subscribe_position_guide():
            return
        self._position_timer.start()

    def _tick_head_position(self) -> None:
        dt = POSITION_POLL_MS / 1000.0
        data = self._latest_guide
        if data is None:
            x, y, z, ok, distance_hint = self._head_smoother.update(None, None, None, dt)
        else:
            raw_x, raw_y, raw_z, _raw_ok, _ = _parse_position_guide(data)
            x, y, z, ok, distance_hint = self._head_smoother.update(
                raw_x, raw_y, raw_z, dt
            )

        self._hold_seconds = self._head_smoother.hold_seconds
        ratio = self._hold_seconds / HEAD_HOLD_SECONDS
        self.head_canvas.update_position(
            x, y, z, ok, distance_hint, hold_ratio=ratio
        )

        remaining = max(0.0, HEAD_HOLD_SECONDS - self._hold_seconds)
        if ok and self._hold_seconds >= HEAD_HOLD_SECONDS:
            self._position_timer.stop()
            self._unsubscribe_position_guide()
            QTimer.singleShot(400, self._start_dot_calibration)
            return

        if ok:
            status_key = f"ok:{int(remaining * 10)}"
            if status_key != self._last_status_key:
                self._last_status_key = status_key
        elif distance_hint == "forward":
            if self._last_status_key != "forward":
                self._last_status_key = "forward"
        elif distance_hint == "back":
            if self._last_status_key != "back":
                self._last_status_key = "back"
        elif self._last_status_key != "center":
            self._last_status_key = "center"

    def _start_dot_calibration(self) -> None:
        self.stack.setCurrentWidget(self.dot_canvas)
        self.status_label.hide()
        self._apply_display_area()

        try:
            self._calibration = ScreenBasedCalibration(self.eyetracker)
            self._calibration.enter_calibration_mode()
        except Exception as exc:
            self._finish(False, f"לא ניתן להתחיל כיול נקודות: {exc}")
            return

        self._point_index = 0
        self._collect_pass = 0
        QTimer.singleShot(500, self._collect_next_point)

    def _collect_next_point(self) -> None:
        if self._calibration is None:
            self._finish(False, "כיול בוטל.")
            return

        if self._point_index >= len(self._points):
            self._pending_collect = None
            self._finalize_calibration()
            return

        self._dot_busy = False
        self._awaiting_explosion = False
        self._dot_token += 1

        norm_x, norm_y = self._points[self._point_index]
        self._pending_collect = (norm_x, norm_y)
        self._collect_pass = 0
        self.dot_canvas.start_point(norm_x, norm_y)

    def _on_dot_look_finished(self) -> None:
        if self._dot_busy or self._calibration is None or self._pending_collect is None:
            return
        if self.dot_canvas.phase != "collecting":
            return
        QTimer.singleShot(DOT_COLLECT_DELAY_MS, self._run_dot_collect)

    def _run_dot_collect(self) -> None:
        if self._dot_busy or self._calibration is None or self._pending_collect is None:
            return
        if self.dot_canvas.phase != "collecting":
            return

        self._dot_busy = True
        token = self._dot_token
        norm_x, norm_y = self._pending_collect
        step = self._point_index + 1

        app = QApplication.instance()
        if app is not None:
            app.processEvents()

        status = CALIBRATION_STATUS_FAILURE
        try:
            for _ in range(DOT_COLLECT_RETRIES):
                if token != self._dot_token:
                    return
                status = self._calibration.collect_data(norm_x, norm_y)
                if status != CALIBRATION_STATUS_FAILURE:
                    break
        except Exception as exc:
            self._abort_calibration()
            self._finish(False, f"איסוף נתוני כיול נכשל: {exc}")
            return
        finally:
            self._dot_busy = False

        if token != self._dot_token:
            return

        if status == CALIBRATION_STATUS_FAILURE:
            self._dot_token += 1
            self.dot_canvas.start_point(norm_x, norm_y)
            return

        self._collect_pass += 1
        self._awaiting_explosion = True
        self.dot_canvas.begin_explosion()

    def _on_dot_explosion_finished(self) -> None:
        if self._calibration is None or not self._awaiting_explosion:
            return
        if self._dot_busy:
            QTimer.singleShot(50, self._on_dot_explosion_finished)
            return

        self._awaiting_explosion = False

        if self._collect_pass < COLLECT_PASSES_PER_POINT:
            QTimer.singleShot(DOT_GAP_MS, self._repeat_current_point)
            return

        self._point_index += 1
        self._collect_pass = 0
        QTimer.singleShot(DOT_GAP_MS, self._collect_next_point)

    def _repeat_current_point(self) -> None:
        if self._pending_collect is None or self._dot_busy:
            return
        norm_x, norm_y = self._pending_collect
        self._dot_token += 1
        self.dot_canvas.start_point(norm_x, norm_y)

    def _finalize_calibration(self) -> None:
        self.dot_canvas.hide_point()

        try:
            self._calibration_result = self._calibration.compute_and_apply()
        except Exception as exc:
            self._abort_calibration()
            self._finish(False, f"חישוב כיול נכשל: {exc}")
            return
        finally:
            self._abort_calibration()

        if self._calibration_result.status not in SUCCESS_STATUSES:
            self._finish(False, "כיול לא עבר. נסה שוב.")
            return

        self._show_fixation_preview()

    def _show_fixation_preview(self) -> None:
        plot_size = (
            max(640, self.width() - 48),
            max(400, self.height() - 100),
        )
        self.preview_canvas.set_calibration_result(
            self._calibration_result,
            plot_size=plot_size,
        )
        self.preview_pixmap = self.preview_canvas.render_pixmap(*plot_size)
        if self.save_dir is not None:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            preview_path = self.save_dir / "calibration_fixation_map.png"
            self.preview_pixmap.save(str(preview_path))

        self.stack.setCurrentWidget(self.preview_canvas)
        err = self.preview_canvas._mean_error_px
        message = "כיול העיניים הושלם בהצלחה."
        if err >= 70:
            message = (
                "כיול הושלם, אך הדיוק נמוך — מומלץ לכייל שוב "
                "(אותו מסך כמו המשחק)."
            )
        message = "הקליברציה הסתיימה בהצלחה, המשחק יופעל כעת."
        self.status_label.show()
        self.status_label.setText(message)
        QTimer.singleShot(3200, lambda: self._finish(True, message))

    def _abort_calibration(self) -> None:
        if self._calibration is None:
            return
        try:
            self._calibration.leave_calibration_mode()
        except Exception:
            pass

    def _finish(self, success: bool, message: str) -> None:
        self._position_timer.stop()
        self._unsubscribe_position_guide()
        self._success = success
        self._message = message
        delay = 1200 if success else 2200
        QTimer.singleShot(delay, self._close_dialog)

    def _close_dialog(self) -> None:
        self.finished_calibration.emit(self._success, self._message)
        if self._success:
            self.accept()
        else:
            self.reject()
        self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._position_timer.stop()
            self._unsubscribe_position_guide()
            self._abort_calibration()
            self._finish(False, "כיול בוטל.")
            return
        super().keyPressEvent(event)


def run_eye_calibration(
    eyetracker,
    parent=None,
    screen=None,
    save_dir: Path | None = None,
) -> tuple[bool, str, QPixmap | None]:
    dialog = EyeCalibrationDialog(
        eyetracker,
        parent=parent,
        screen=screen,
        save_dir=save_dir,
    )
    outcome = {"success": False, "message": "", "preview": None}

    def _on_done(success: bool, message: str) -> None:
        outcome["success"] = success
        outcome["message"] = message
        outcome["preview"] = dialog.preview_pixmap

    dialog.finished_calibration.connect(_on_done)
    dialog.showFullScreen()
    dialog.raise_()
    dialog.activateWindow()
    QTimer.singleShot(200, dialog.begin)

    loop = QEventLoop()
    dialog.finished.connect(loop.quit)
    loop.exec()
    return outcome["success"], outcome["message"], outcome["preview"]

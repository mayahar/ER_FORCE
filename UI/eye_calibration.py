"""Fullscreen Tobii calibration: head position → 5-point dots → fixation preview."""

from __future__ import annotations

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

DEFAULT_CALIBRATION_POINTS = (
    (0.5, 0.5),
    (0.1, 0.1),
    (0.9, 0.1),
    (0.9, 0.9),
    (0.1, 0.9),
)

SUCCESS_STATUSES = {
    CALIBRATION_STATUS_SUCCESS,
    CALIBRATION_STATUS_SUCCESS_LEFT_EYE,
    CALIBRATION_STATUS_SUCCESS_RIGHT_EYE,
}

HEAD_HOLD_SECONDS = 5.0
POSITION_POLL_MS = 100

# Tobii normalized user-position sweet spot (approx. Eye Tracker Manager defaults).
HEAD_X_RANGE = (0.38, 0.62)
HEAD_Y_RANGE = (0.32, 0.68)
HEAD_Z_RANGE = (0.42, 0.72)


def _parse_position_guide(data) -> tuple[float | None, float | None, float | None, bool]:
    """Average valid left/right user position; return (x, y, z, ok)."""
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
        return None, None, None, False

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points if len(p) > 2]
    x = sum(xs) / len(xs)
    y = sum(ys) / len(ys)
    z = sum(zs) / len(zs) if zs else 0.55

    ok = (
        HEAD_X_RANGE[0] <= x <= HEAD_X_RANGE[1]
        and HEAD_Y_RANGE[0] <= y <= HEAD_Y_RANGE[1]
        and HEAD_Z_RANGE[0] <= z <= HEAD_Z_RANGE[1]
    )
    return x, y, z, ok


class HeadPositionCanvas(QWidget):
    """Head silhouette + live position dot (Tobii user-position guide style)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user_x: float | None = None
        self._user_y: float | None = None
        self._user_ok = False
        self._hold_ratio = 0.0

    def update_position(self, data, hold_ratio: float = 0.0) -> None:
        x, y, _z, ok = _parse_position_guide(data)
        self._user_x = x
        self._user_y = y
        self._user_ok = ok
        self._hold_ratio = max(0.0, min(1.0, hold_ratio))
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d1117"))

        w, h = self.width(), self.height()
        cx, cy = w // 2, int(h * 0.42)
        head_rx = int(min(w, h) * 0.14)
        head_ry = int(head_rx * 1.25)

        # Target zone (where the head should be).
        zone_color = QColor("#43a047") if self._user_ok else QColor("#546e7a")
        painter.setPen(QPen(zone_color, 3, Qt.PenStyle.DashLine))
        painter.setBrush(QColor(67, 160, 71, 35) if self._user_ok else QColor(84, 110, 122, 25))
        painter.drawEllipse(cx - head_rx, cy - head_ry, head_rx * 2, head_ry * 2)

        # Head outline drawing.
        painter.setPen(QPen(QColor("#90a4ae"), 4))
        painter.setBrush(QColor("#263238"))
        painter.drawEllipse(cx - head_rx, cy - head_ry, head_rx * 2, head_ry * 2)

        # Neck + shoulders.
        shoulder_w = int(head_rx * 2.2)
        painter.setBrush(QColor("#263238"))
        painter.drawRoundedRect(
            cx - shoulder_w // 2,
            cy + head_ry - 10,
            shoulder_w,
            int(head_ry * 1.1),
            24,
            24,
        )

        # Eyes hint on silhouette.
        eye_y = cy - int(head_ry * 0.15)
        painter.setBrush(QColor("#eceff1"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(cx - head_rx // 2, eye_y, head_rx // 3, head_ry // 5)
        painter.drawEllipse(cx + head_rx // 6, eye_y, head_rx // 3, head_ry // 5)

        # Live head position dot (mapped from Tobii x/y).
        if self._user_x is not None and self._user_y is not None:
            map_margin_x = int(w * 0.22)
            map_margin_y = int(h * 0.12)
            map_w = w - 2 * map_margin_x
            map_h = int(h * 0.55)
            dot_x = map_margin_x + int(self._user_x * map_w)
            dot_y = map_margin_y + int((1.0 - self._user_y) * map_h)
            dot_color = QColor("#66bb6a") if self._user_ok else QColor("#ef5350")
            painter.setBrush(dot_color)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawEllipse(dot_x - 14, dot_y - 14, 28, 28)

        # Hold progress bar at bottom.
        bar_y = h - 48
        bar_x = int(w * 0.15)
        bar_w = int(w * 0.7)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#37474f"))
        painter.drawRoundedRect(bar_x, bar_y, bar_w, 16, 8, 8)
        fill_w = int(bar_w * self._hold_ratio)
        if fill_w > 0:
            painter.setBrush(QColor("#66bb6a") if self._user_ok else QColor("#ffa726"))
            painter.drawRoundedRect(bar_x, bar_y, fill_w, 16, 8, 8)


class CalibrationDotCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._norm_x = 0.5
        self._norm_y = 0.5
        self._visible = False

    def show_point(self, norm_x: float, norm_y: float) -> None:
        self._norm_x = norm_x
        self._norm_y = norm_y
        self._visible = True
        self.update()

    def hide_point(self) -> None:
        self._visible = False
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101010"))
        if not self._visible:
            return

        radius = max(18, min(self.width(), self.height()) // 40)
        x = int(self._norm_x * self.width())
        y = int(self._norm_y * self.height())

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#ffffff"), 3))
        painter.setBrush(QColor("#e53935"))
        painter.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)
        painter.setBrush(QColor("#ffffff"))
        inner = max(4, radius // 4)
        painter.drawEllipse(x - inner, y - inner, inner * 2, inner * 2)


class FixationMapCanvas(QWidget):
    """Small gaze/fixation map from calibration samples."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._targets: list[tuple[float, float]] = []
        self._gaze_points: list[tuple[float, float]] = []

    def set_calibration_result(self, result) -> None:
        self._targets = []
        self._gaze_points = []
        if result is None:
            self.update()
            return

        for point in getattr(result, "calibration_points", ()) or ():
            tx, ty = point.position_on_display_area
            self._targets.append((float(tx), float(ty)))
            for sample in point.calibration_samples:
                for eye in (sample.left_eye, sample.right_eye):
                    if eye.validity == VALIDITY_VALID_AND_USED:
                        px, py = eye.position_on_display_area
                        self._gaze_points.append((float(px), float(py)))
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

        for gx, gy in self._gaze_points:
            x = plot.left() + gx * plot.width()
            y = plot.top() + gy * plot.height()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(100, 181, 246, 180))
            painter.drawEllipse(int(x) - 4, int(y) - 4, 8, 8)

        for tx, ty in self._targets:
            x = plot.left() + tx * plot.width()
            y = plot.top() + ty * plot.height()
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor("#e53935"))
            painter.drawEllipse(int(x) - 10, int(y) - 10, 20, 20)


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

        if self.target_screen is not None:
            self.setGeometry(self.target_screen.geometry())

    def begin(self) -> None:
        self._start_head_position_phase()

    def _set_status(self, text: str) -> None:
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

    def _start_head_position_phase(self) -> None:
        self.stack.setCurrentWidget(self.head_canvas)
        self._hold_seconds = 0.0
        self._set_status(
            "מקם את הראש בתוך הצורה הירוקה.\n"
            "Position your head inside the green outline."
        )
        if not self._subscribe_position_guide():
            return
        self._position_timer.start()

    def _tick_head_position(self) -> None:
        data = self._latest_guide
        if data is None:
            self.head_canvas.update_position(
                {"left_user_position_validity": 0, "right_user_position_validity": 0},
                hold_ratio=self._hold_seconds / HEAD_HOLD_SECONDS,
            )
            self._hold_seconds = 0.0
            return

        _x, _y, _z, ok = _parse_position_guide(data)
        if ok:
            self._hold_seconds += POSITION_POLL_MS / 1000.0
        else:
            self._hold_seconds = 0.0

        ratio = self._hold_seconds / HEAD_HOLD_SECONDS
        self.head_canvas.update_position(data, hold_ratio=ratio)

        remaining = max(0.0, HEAD_HOLD_SECONDS - self._hold_seconds)
        if ok and self._hold_seconds >= HEAD_HOLD_SECONDS:
            self._position_timer.stop()
            self._unsubscribe_position_guide()
            self._set_status("מיקום ראש תקין — מתחיל כיול נקודות...\nStarting dot calibration...")
            QTimer.singleShot(600, self._start_dot_calibration)
            return

        if ok:
            self._set_status(
                f"מיקום טוב — החזק עוד {remaining:.1f} שניות.\n"
                f"Good position — hold for {remaining:.1f}s more."
            )
        else:
            self._set_status(
                "התקרב/התרחק והזז את הראש למרכז הצורה.\n"
                "Move your head to center it in the outline."
            )

    def _start_dot_calibration(self) -> None:
        self.stack.setCurrentWidget(self.dot_canvas)
        try:
            self._calibration = ScreenBasedCalibration(self.eyetracker)
            self._calibration.enter_calibration_mode()
        except Exception as exc:
            self._finish(False, f"לא ניתן להתחיל כיול נקודות: {exc}")
            return

        self._point_index = 0
        self._set_status(
            "הסתכל על הנקודה האדומה.\nLook at the red dot."
        )
        QTimer.singleShot(700, self._collect_next_point)

    def _collect_next_point(self) -> None:
        if self._calibration is None:
            self._finish(False, "כיול בוטל.")
            return

        if self._point_index >= len(self._points):
            self._finalize_calibration()
            return

        norm_x, norm_y = self._points[self._point_index]
        step = self._point_index + 1
        total = len(self._points)
        self._set_status(
            f"נקודה {step}/{total} — הסתכל על הנקודה.\n"
            f"Point {step}/{total} — look at the dot."
        )
        self.dot_canvas.show_point(norm_x, norm_y)

        try:
            status = self._calibration.collect_data(norm_x, norm_y)
        except Exception as exc:
            self._abort_calibration()
            self._finish(False, f"איסוף נתוני כיול נכשל: {exc}")
            return

        if status == CALIBRATION_STATUS_FAILURE:
            self._abort_calibration()
            self._finish(
                False,
                f"נקודה {step} נכשלה. הסתכל ישירות על הנקודה.",
            )
            return

        self._point_index += 1
        QTimer.singleShot(900, self._collect_next_point)

    def _finalize_calibration(self) -> None:
        self.dot_canvas.hide_point()
        self._set_status("מחשב כיול...\nComputing calibration...")

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
        self.preview_canvas.set_calibration_result(self._calibration_result)
        self.preview_pixmap = self.preview_canvas.render_pixmap(400, 250)
        if self.save_dir is not None:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            preview_path = self.save_dir / "calibration_fixation_map.png"
            self.preview_pixmap.save(str(preview_path))

        self.stack.setCurrentWidget(self.preview_canvas)
        self._set_status(
            "מפת מבט — נקודות כחולות: מבט בפועל, אדום: יעדי כיול.\n"
            "Gaze map — blue: looks, red: calibration targets."
        )
        QTimer.singleShot(2800, lambda: self._finish(True, "כיול העיניים הושלם בהצלחה."))

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

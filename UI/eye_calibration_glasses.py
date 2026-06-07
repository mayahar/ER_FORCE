"""Fullscreen Tobii Pro Glasses 3 single-point display calibration."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap, QScreen
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout

try:
    from ui.eye_tracking_runtime import _request
except Exception:
    _request = None


CALIBRATION_ENDPOINTS = (
    ("/rest/calibrate!calibrate", [True]),
    ("/rest/calibrate!run", []),
)
CALIBRATION_ATTEMPTS = 4
CALIBRATION_START_DELAY_MS = 4200
MARKER_SETTLE_SECONDS = 0.35
SUCCESS_FEEDBACK_MS = 900
INSTRUCTION_MAX_WIDTH = 760
INSTRUCTION_MAX_HEIGHT = 150
INSTRUCTION_TOP_MARGIN = 16


class EyeCalibrationDialog(QDialog):
    finished_calibration = Signal(bool, str)

    def __init__(self, runtime, parent=None, screen=None, save_dir: Path | None = None):
        super().__init__(parent)
        self.runtime = runtime
        self.screen = screen if screen is not None else QGuiApplication.primaryScreen()
        self.preview_pixmap = None
        self._calibration_succeeded = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("background-color: #FFFFFF;")

        # שינוי: סידור אנכי עם מרווח עליון קבוע כדי שהטקסט יישאר למעלה ולא יפריע לסמן
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.setContentsMargins(0, INSTRUCTION_TOP_MARGIN, 0, 0)
        layout.setSpacing(0)

        self.instruction_label = QLabel(
            "הנחיית כיול חשובה\n\nלהסתכל עכשיו על מרכז הנקודה השחורה.\nלהחזיק מבט יציב ולא להזיז את הראש.",
            self,
        )
        # שינוי צבע הטקסט לשחור/אפור כהה כי הרקע הוא לבן (#FFFFFF)! טקסט לבן על רקע לבן לא ייקרא טוב.
        self.instruction_label.setStyleSheet(
            "color: #111111; background-color: #FFF3B0; border: 5px solid #111111; "
            "border-radius: 8px; padding: 10px 22px; font-size: 18pt; "
            "font-family: Arial; font-weight: bold;"
        )
        self.instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setMaximumWidth(INSTRUCTION_MAX_WIDTH)
        self.instruction_label.setMaximumHeight(INSTRUCTION_MAX_HEIGHT)
        layout.addWidget(self.instruction_label)

        self.target_image_path = str(Path(__file__).resolve().parent / "image_325509.png")
        self.target_pixmap = QPixmap(self.target_image_path)
        if self.target_pixmap.isNull():
            print(f"Warning: calibration target image was not found: {self.target_image_path}")

        QTimer.singleShot(CALIBRATION_START_DELAY_MS, self.perform_glasses_calibration)

    def _log(self, message: str) -> None:
        logger = getattr(self.runtime, "_log", None)
        if callable(logger):
            logger(f"כיול: {message}")
        else:
            print(f"[Eye calibration] {message}")

    def calculate_target_size_px(self) -> int:
        if self.screen is None:
            return 180

        dpi = self.screen.logicalDotsPerInch()
        if dpi <= 1.0:
            dpi = 96.0
        return int((45.0 / 25.4) * dpi)

    def perform_glasses_calibration(self) -> None:
        self._log("מתחיל כיול")
        success, message = self._calibrate_glasses()
        self.runtime.calibration_attempted = True
        if success:
            self._log(f"הכיול הצליח: {message}")
            self.runtime.calibration_passed = True
            self.runtime.calibration_message = message
            self._calibration_succeeded = True
            self.instruction_label.setText("הכיול הצליח. עוברים למשחק...")
            self.instruction_label.setStyleSheet(
                "color: #16833B; font-size: 18pt; font-family: Arial; font-weight: bold;"
            )
            self.update()
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
            QTimer.singleShot(
                SUCCESS_FEEDBACK_MS,
                lambda: self._finish_success(message),
            )
            return

        self._log(f"הכיול נכשל: {message}")
        self.runtime.calibration_passed = False
        self.runtime.calibration_message = message
        self.instruction_label.setText(message)
        self.instruction_label.setMaximumHeight(260)
        self.instruction_label.setStyleSheet(
            "color: #FF2222; font-size: 16pt; font-family: Arial; font-weight: bold;"
        )
        QTimer.singleShot(2500, lambda: self.finished_calibration.emit(False, message))
        QTimer.singleShot(2550, self.reject)

    def _finish_success(self, message: str) -> None:
        self.finished_calibration.emit(True, message)
        self.accept()

    def _calibrate_glasses(self) -> tuple[bool, str]:
        if _request is None:
            return False, "הכיול נכשל: לא ניתן לגשת למודול התקשורת של המשקפיים."

        ensure_tracker = getattr(self.runtime, "ensure_tracker", None)
        if callable(ensure_tracker) and not ensure_tracker():
            detail = getattr(self.runtime, "last_error", "")
            return False, f"הכיול לא התחיל כי אין תקשורת יציבה עם המשקפיים. {detail}"

        errors: list[str] = []
        for attempt in range(1, CALIBRATION_ATTEMPTS + 1):
            self.instruction_label.setText(
                f"להמשיך להסתכל על מרכז הנקודה השחורה\nבלי לזוז\nניסיון {attempt}/{CALIBRATION_ATTEMPTS}"
            )
            app = QApplication.instance()
            if app is not None:
                app.processEvents()

            active_host = getattr(self.runtime, "active_host", None)
            emit_response, emit_host, emit_error = _request(
                "POST",
                "/rest/calibrate!emit-markers",
                json_body=[],
                timeout=3.0,
                preferred_host=active_host,
            )
            if emit_response is None:
                errors.append(f"/rest/calibrate!emit-markers: {emit_error}")
                self._log(errors[-1])
                self._log("emit-markers failed; continuing with calibration attempt")
                time.sleep(0.5)
            elif emit_host and hasattr(self.runtime, "active_host"):
                self.runtime.active_host = emit_host

            time.sleep(MARKER_SETTLE_SECONDS)

            for calibrate_path, body in CALIBRATION_ENDPOINTS:
                active_host = getattr(self.runtime, "active_host", None)
                self._log(f"מנסה {calibrate_path}, ניסיון {attempt}/{CALIBRATION_ATTEMPTS}")
                response, host, error = _request(
                    "POST",
                    calibrate_path,
                    json_body=body,
                    timeout=5.0,
                    preferred_host=active_host,
                )
                if response is None:
                    errors.append(f"{calibrate_path}: {error}")
                    self._log(errors[-1])
                    continue
                if host and hasattr(self.runtime, "active_host"):
                    self.runtime.active_host = host

                if response.status_code < 200 or response.status_code >= 300:
                    errors.append(
                        f"{calibrate_path}: HTTP {response.status_code} {response.text[:120]}"
                    )
                    self._log(errors[-1])
                    continue

                status = self._response_payload(response)
                self._log(f"{calibrate_path} החזיר סטטוס: {status!r}")
                if self._is_calibrated_status(status):
                    return True, "הכיול הושלם בהצלחה!"

                errors.append(f"{calibrate_path}: calibration status was {status!r}")
                if status is False:
                    break

        details = "; ".join(errors[-3:])
        false_status_seen = any("calibration status was False" in err for err in errors)
        connection_lost = any(
            marker in err
            for err in errors
            for marker in ("NameResolutionError", "ConnectTimeoutError", "Max retries exceeded")
        )
        if connection_lost:
            return (
                False,
                "הכיול נכשל כי התקשורת למשקפיים נותקה או לא יציבה בזמן הכיול. "
                "בדקי שהמשקפיים עדיין מחוברות לאותה רשת/כבל, שהן לא נכנסו למצב שינה, "
                "ואם צריך הגדירי TOBII_GLASSES_HOST לכתובת שעובדת באופן יציב. "
                f"פרטים: {details}"
            )
        if false_status_seen:
            return (
                False,
                "הכיול נכשל כי המשקפיים לא זיהו את סמן הכיול או שהמבט לא היה יציב. "
                "כווני את מצלמת המשקפיים למרכז הסמן, ודאי שהסמן לא קטן מדי או מסנוור, ונסי שוב."
            )
        if details:
            return False, f"הכיול נכשל. ודאי שהמשקפיים מחוברים ומכוונים לסמן. פרטים: {details}"
        return False, "הכיול נכשל. ודאי שהמשקפיים מחוברים ומכוונים לסמן."

    @staticmethod
    def _response_payload(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text.strip()

    @staticmethod
    def _is_calibrated_status(status: Any) -> bool:
        if status is True or status in ("success", "calibrated"):
            return True
        if isinstance(status, dict):
            values = {str(value).lower() for value in status.values()}
            return "calibrated" in values or "success" in values or "true" in values
        return False

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if self._calibration_succeeded:
            painter.fillRect(self.rect(), QColor("#FFFFFF"))
            center_x = self.width() // 2
            center_y = self.height() // 2
            radius = max(72, min(self.width(), self.height()) // 9)
            painter.setBrush(QColor("#E8F5E9"))
            painter.setPen(QPen(QColor("#16833B"), 10))
            painter.drawEllipse(
                center_x - radius,
                center_y - radius,
                radius * 2,
                radius * 2,
            )
            painter.setPen(
                QPen(
                    QColor("#16833B"),
                    16,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(
                center_x - radius // 2,
                center_y,
                center_x - radius // 8,
                center_y + radius // 3,
            )
            painter.drawLine(
                center_x - radius // 8,
                center_y + radius // 3,
                center_x + radius // 2,
                center_y - radius // 3,
            )
            return

        # שינוי: מירכוז מושלם של הסמן (בלי ה-+60) כדי שיהיה רחוק מהטקסט העליון
        center_x = self.width() / 2
        center_y = self.height() / 2
        target_size = self.calculate_target_size_px()
        half_size = target_size / 2

        if not self.target_pixmap.isNull():
            target_rect = QRectF(
                center_x - half_size,
                center_y - half_size,
                target_size,
                target_size,
            )
            painter.drawPixmap(target_rect, self.target_pixmap, QRectF(self.target_pixmap.rect()))
            return

        # ציור חלופי למקרה שהתמונה חסרה (תוקנו גם חלק מהצבעים לניגודיות טובה על רקע לבן)
        painter.setPen(QPen(QColor("#000000"), 4))
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawEllipse(center_x - half_size, center_y - half_size, target_size, target_size)
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#0000FF"), 2))
        painter.drawEllipse(center_x - 20, center_y - 20, 40, 40)
        painter.setBrush(QColor("#FF3333"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center_x - 4, center_y - 4, 8, 8)


def _resolve_calibration_screen(parent, screen) -> QScreen:
    if screen is not None:
        return screen
    if parent is not None and hasattr(parent, "screen") and parent.screen() is not None:
        return parent.screen()
    return QGuiApplication.primaryScreen()


def _present_fullscreen_dialog(dialog: QDialog, screen: QScreen) -> None:
    dialog.setGeometry(screen.geometry())
    dialog.showFullScreen()
    dialog.raise_()
    dialog.activateWindow()
    dialog.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def run_eye_calibration(
    runtime,
    parent=None,
    screen=None,
    save_dir: Path | None = None,
    **kwargs,
) -> tuple[bool, str, QPixmap | None]:
    kwargs.pop("controller", None)

    screen = _resolve_calibration_screen(parent, screen)
    dialog = EyeCalibrationDialog(runtime, parent=None, screen=screen, save_dir=save_dir)
    outcome = {"success": False, "message": "", "preview": None}

    def _on_done(success: bool, message: str) -> None:
        outcome["success"] = success
        outcome["message"] = message

    dialog.finished_calibration.connect(_on_done)

    main_window = parent.window() if parent is not None and hasattr(parent, "window") else None
    _present_fullscreen_dialog(dialog, screen)

    if main_window is not None:
        main_window.hide()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    dialog.exec()

    if main_window is not None:
        main_window.show()
        main_window.raise_()
        main_window.activateWindow()

    return outcome["success"], outcome["message"], None

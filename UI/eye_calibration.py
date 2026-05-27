"""Fullscreen Tobii Pro Glasses 3 single-point display calibration using official Target Image."""

from __future__ import annotations
import time
from pathlib import Path
import requests

from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QSize
from PySide6.QtGui import QFont, QGuiApplication, QPainter, QColor, QPen, QPixmap, QScreen
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget, QApplication

GLASSES_IP = "TG03B-0123456789.local"

class EyeCalibrationDialog(QDialog):
    finished_calibration = Signal(bool, str)

    def __init__(self, runtime, parent=None, screen=None, save_dir: Path | None = None):
        super().__init__(parent)
        self.runtime = runtime
        self.screen = screen if screen is not None else QGuiApplication.primaryScreen()
        self.preview_pixmap = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        
        # רקע אפור כהה ייעודי (מונע סינוור ושומר על אישונים יציבים בזמן הכיול)
        self.setStyleSheet("background-color: #232323;")

        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # כיתוב הנחיה לנבדק
        self.instruction_label = QLabel("אנא הבט ישירות ובאופן יציב אל מרכז סמן הכיול...", self)
        self.instruction_label.setStyleSheet("color: #FFFFFF; font-size: 18pt; font-family: Arial; font-weight: bold;")
        self.instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.instruction_label)

        # טעינת קובץ תמונת ה-Target שהעלית
        # ודאי שקובץ התמונה נמצא באותה תיקייה או עדכני את הנתיב בהתאם
        self.target_image_path = str(Path(__file__).resolve().parent / "image_325509.png")
        self.target_pixmap = QPixmap(self.target_image_path)
        
        if self.target_pixmap.isNull():
            print(f"אזהרה: לא ניתן היה לטעון את תמונת הסמן מהנתיב: {self.target_image_path}. המערכת תשתמש בסמן חלופי.")

        # הפעלת תהליך הכיול מול המשקפיים שנייה אחת לאחר עליית המסך
        QTimer.singleShot(1000, self.perform_glasses_calibration)

    def calculate_target_size_px(self) -> int:
        """
        מחשב את גודל התמונה בפיקסלים כדי שתתאים בדיוק ל-45 מ"מ (4.5 ס"מ) פיזיים על המסך,
        בהתאם לצפיפות הפיקסלים (DPI) של המסך הנוכחי. מתאים למרחק ישיבה של 50-70 ס"מ.
        """
        if self.screen is None:
            return 180 # ברירת מחדל למסכי 96 DPI סטנדרטיים
        
        # קבלת ה-DPI הלוגי/פיזי של המסך
        dpi = self.screen.logicalDotsPerInch()
        if dpi <= 1.0:
            dpi = 96.0
            
        # 45 מ"מ מומרים לאינצ'ים (45 / 25.4) ומכופלים ב-DPI כדי לקבל פיקסלים
        target_size_px = int((45.0 / 25.4) * dpi)
        return target_size_px

    def perform_glasses_calibration(self):
        """פנייה לשרת המשקפיים לביצוע הכיול המיידי"""
        try:
            # 1. פקודת כיול - המשקפיים מחפשים את הדפוס הגיאומטרי שמופיע כעת במסך
            res = requests.post(f"http://{GLASSES_IP}/rest/calibrator!calibrate", json=[], timeout=5.0)
            
            if res.status_code == 200:
                status = res.json()
                if status == "calibrated":
                    # 2. אישור ושמירה של הכיול בהצלחה
                    requests.post(f"http://{GLASSES_IP}/rest/calibrator!accept", json=[], timeout=3.0)
                    self.runtime.calibration_passed = True
                    self.runtime.calibration_message = "הכיול הושלם בהצלחה!"
                    self.finished_calibration.emit(True, "הכיול הושלם בהצלחה!")
                    self.accept()
                    return
            
            # טיפול במצב שבו המשקפיים לא זיהו את הסמן (למשל מצמוץ או תזוזה חדה)
            self.instruction_label.setText("הכיול נכשל. אנא ודא שהמשקפיים מופנים למרכז הסמן ונסה שוב.")
            self.instruction_label.setStyleSheet("color: #FF5555; font-size: 18pt; font-family: Arial; font-weight: bold;")
            QTimer.singleShot(2500, lambda: self.finished_calibration.emit(False, "הכיול נכשל"))
            QTimer.singleShot(2550, self.reject)
            
        except Exception as e:
            self.finished_calibration.emit(False, f"שגיאת תקשורת מול המשקפיים: {str(e)}")
            self.reject()

    def paintEvent(self, event):
        """רנדור תמונת ה-Target במרכז המסך בגודל הפיזי המותאם"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        width = self.width()
        height = self.height()
        center_x = width / 2
        center_y = height / 2 + 60  # ממורכז אנכית עם מרווח קל מתחת לטקסט

        # חישוב הגודל הנדרש בפיקסלים ל-4.5 ס"מ
        target_size = self.calculate_target_size_px()
        half_size = target_size / 2

        if not self.target_pixmap.isNull():
            # ציור התמונה הרשמית שהעלית שעברה התאמה מדויקת לגודל הפיזי במסך
            target_rect = QRectF(center_x - half_size, center_y - half_size, target_size, target_size)
            painter.drawPixmap(target_rect, self.target_pixmap, QRectF(self.target_pixmap.rect()))
        else:
            # Fallback גיאומטרי למקרה שהתמונה לא נמצאה בדיסק (כדי למנוע קריסה מוחלטת)
            painter.setPen(QPen(QColor("#FFFFFF"), 4))
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.drawEllipse(center_x - half_size, center_y - half_size, target_size, target_size)
            painter.setBrush(QColor("#000000"))
            painter.setPen(QPen(QColor("#00FFFF"), 2))
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


def run_eye_calibration(runtime, parent=None, screen=None, save_dir: Path | None = None) -> tuple[bool, str, QPixmap | None]:
    screen = _resolve_calibration_screen(parent, screen)
    dialog = EyeCalibrationDialog(runtime, parent=None, screen=screen, save_dir=save_dir)
    outcome = {"success": False, "message": "", "preview": None}

    def _on_done(success: bool, message: str) -> None:
        outcome["success"] = success
        outcome["message"] = message

    dialog.finished_calibration.connect(_on_done)
    
    main_window = None
    if parent is not None and hasattr(parent, "window"):
        main_window = parent.window()

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
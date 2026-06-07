import contextlib
import os
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from voice.calibrate import CALIBRATION_FILE, run_calibration


class _SignalWriter:
    def __init__(self, emit_line):
        self._emit_line = emit_line
        self._buffer = ""

    def write(self, text):
        self._buffer += str(text)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit_line(line)

    def flush(self):
        if self._buffer:
            self._emit_line(self._buffer)
            self._buffer = ""


class CalibrationWorker(QThread):
    log_line = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def run(self):
        writer = _SignalWriter(self.log_line.emit)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                run_calibration()
            writer.flush()
            calib_path = Path.cwd() / CALIBRATION_FILE
            self.finished_ok.emit(str(calib_path))
        except Exception as exc:
            writer.flush()
            self.failed.emit(str(exc))


class MicrophoneCalibrationWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.setWindowTitle("ERR Force - Microphone Calibration")
        self.setMinimumSize(760, 560)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("קליברציית מיקרופון")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignRight)
        layout.addWidget(title)

        intro = QLabel(
            "הקליברציה מודדת את רמת הרעש בחדר ואת עוצמת הדיבור של המשתתף. "
            "לפני התחלה ודאו שהמיקרופון מחובר ונבחר במערכת ההפעלה, שהחדר שקט, "
            "ושהמשתתף יושב כמו בתחילת הניסוי."
        )
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignRight)
        layout.addWidget(intro)

        steps = QLabel(
            "מה יקרה אחרי לחיצה על התחלה:\n"
            "1. שקט מוחלט למשך כמה שניות.\n"
            "2. אמירת אההה בקול חלש וברור.\n"
            "3. אמירת אההה בקול רגיל ויציב.\n\n"
            "אין צורך להקליד שום דבר. ההוראות והספירה לאחור יופיעו בחלון."
        )
        steps.setWordWrap(True)
        steps.setAlignment(Qt.AlignRight)
        layout.addWidget(steps)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("יומן הקליברציה יופיע כאן...")
        self.log.setLayoutDirection(Qt.LeftToRight)
        layout.addWidget(self.log, stretch=1)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.start_button = QPushButton("התחלת קליברציה")
        self.start_button.clicked.connect(self.start_calibration)
        button_row.addWidget(self.start_button)

        self.open_folder_button = QPushButton("פתיחת תיקיית ההתקנה")
        self.open_folder_button.clicked.connect(self.open_install_folder)
        button_row.addWidget(self.open_folder_button)

        self.close_button = QPushButton("סגירה")
        self.close_button.clicked.connect(self.close)
        button_row.addWidget(self.close_button)

        layout.addLayout(button_row)
        self.setCentralWidget(root)

    def append_log(self, line):
        if line.strip():
            self.log.append(line)

    def start_calibration(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.log.clear()
        self.append_log("Starting microphone calibration...")
        self.start_button.setEnabled(False)
        self.worker = CalibrationWorker()
        self.worker.log_line.connect(self.append_log)
        self.worker.finished_ok.connect(self.on_success)
        self.worker.failed.connect(self.on_failure)
        self.worker.start()

    def on_success(self, calib_path):
        self.start_button.setEnabled(True)
        self.append_log("")
        self.append_log(f"Calibration file saved: {calib_path}")
        QMessageBox.information(
            self,
            "הקליברציה הסתיימה",
            "קליברציית המיקרופון הסתיימה ונשמרה בהצלחה.",
        )

    def on_failure(self, error):
        self.start_button.setEnabled(True)
        self.append_log("")
        self.append_log(f"ERROR: {error}")
        QMessageBox.critical(
            self,
            "הקליברציה נכשלה",
            "לא ניתן היה להשלים את קליברציית המיקרופון.\n\n"
            "בדקו שהמיקרופון מחובר, מזוהה ב-Windows ואינו בשימוש על ידי תוכנה אחרת.",
        )

    def open_install_folder(self):
        os.startfile(str(Path.cwd()))


def main():
    app = QApplication(sys.argv)
    window = MicrophoneCalibrationWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

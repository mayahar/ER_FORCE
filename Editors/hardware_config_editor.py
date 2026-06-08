import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.hardware_config import load_hardware_config, save_hardware_config


class HardwareConfigEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ERR Force - Hardware Configuration")
        self.resize(620, 440)
        self.setLayoutDirection(Qt.RightToLeft)

        self.mode_group = QButtonGroup(self)
        self.bar_group = QButtonGroup(self)
        self.glasses_group = QButtonGroup(self)
        self.results_group = QButtonGroup(self)
        self.mode_buttons = {}
        self.bar_buttons = {}
        self.glasses_buttons = {}
        self.results_buttons = {}

        self.config = load_hardware_config()
        self._build_ui()
        self._load_to_ui()
        self._sync_visibility()

    def _build_ui(self):
        main = QWidget()
        self.setCentralWidget(main)
        layout = QVBoxLayout(main)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("<h2>בחירת תצורת עוקב עיניים</h2>")
        title.setAlignment(Qt.AlignRight)
        layout.addWidget(title)

        mode_box = QGroupBox("סוג מערכת")
        mode_layout = QHBoxLayout(mode_box)
        for value, text in (
            ("combined", "משולב"),
            ("bar", "פס"),
            ("glasses", "משקפיים"),
        ):
            button = QRadioButton(text)
            button.toggled.connect(self._sync_visibility)
            self.mode_group.addButton(button)
            self.mode_buttons[value] = button
            mode_layout.addWidget(button)
        mode_layout.addStretch()
        layout.addWidget(mode_box)

        self.glasses_box = QGroupBox("קליברציה למשקפיים")
        glasses_layout = QVBoxLayout(self.glasses_box)
        for value, text in ((True, "עם קליברציה"), (False, "בלי קליברציה")):
            button = QRadioButton(text)
            self.glasses_group.addButton(button)
            self.glasses_buttons[value] = button
            glasses_layout.addWidget(button, alignment=Qt.AlignRight)
        layout.addWidget(self.glasses_box)

        self.bar_box = QGroupBox("קליברציה לפס")
        bar_layout = QVBoxLayout(self.bar_box)
        for value, text in (
            ("with_head", "קליברציה עם ראש"),
            ("without_head", "קליברציה בלי ראש"),
            ("none", "בלי קליברציה"),
        ):
            button = QRadioButton(text)
            self.bar_group.addButton(button)
            self.bar_buttons[value] = button
            bar_layout.addWidget(button, alignment=Qt.AlignRight)
        layout.addWidget(self.bar_box)

        self.results_box = QGroupBox("מקור מדדי העיניים בציון הסופי במצב משולב")
        results_layout = QHBoxLayout(self.results_box)
        for value, text in (("glasses", "משקפיים"), ("bar", "פס")):
            button = QRadioButton(text)
            self.results_group.addButton(button)
            self.results_buttons[value] = button
            results_layout.addWidget(button)
        results_layout.addStretch()
        layout.addWidget(self.results_box)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("color: #444;")
        layout.addWidget(self.summary)

        button_row = QHBoxLayout()
        save_button = QPushButton("שמור")
        save_button.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 10px;")
        save_button.clicked.connect(self._save)
        reload_button = QPushButton("טען מחדש")
        reload_button.clicked.connect(self._reload)
        button_row.addWidget(save_button)
        button_row.addWidget(reload_button)
        button_row.addStretch()
        layout.addLayout(button_row)
        layout.addStretch()

    def _load_to_ui(self):
        self.mode_buttons.get(self.config.get("eye_tracker_mode"), self.mode_buttons["combined"]).setChecked(True)
        self.bar_buttons.get(self.config.get("bar_calibration_mode"), self.bar_buttons["without_head"]).setChecked(True)
        self.glasses_buttons[bool(self.config.get("glasses_calibration_enabled", True))].setChecked(True)
        self.results_buttons.get(
            self.config.get("combined_eye_results_source"),
            self.results_buttons["glasses"],
        ).setChecked(True)

    @staticmethod
    def _checked_key(buttons, fallback):
        for key, button in buttons.items():
            if button.isChecked():
                return key
        return fallback

    def _sync_visibility(self):
        mode = self._checked_key(self.mode_buttons, "combined")
        self.glasses_box.setVisible(mode in {"glasses", "combined"})
        self.bar_box.setVisible(mode in {"bar", "combined"})
        self.results_box.setVisible(mode == "combined")

        if mode == "glasses":
            summary = "בהרצה הבאה יופעלו משקפיים בלבד."
        elif mode == "bar":
            summary = "בהרצה הבאה יופעל פס בלבד."
        else:
            summary = "בהרצה הבאה יופעל מצב משולב: משקפיים ופס."
        self.summary.setText(summary)

    def _reload(self):
        self.config = load_hardware_config()
        self._load_to_ui()
        self._sync_visibility()

    def _save(self):
        config = {
            "eye_tracker_mode": self._checked_key(self.mode_buttons, "combined"),
            "bar_calibration_mode": self._checked_key(self.bar_buttons, "without_head"),
            "glasses_calibration_enabled": bool(self._checked_key(self.glasses_buttons, True)),
            "combined_eye_results_source": self._checked_key(self.results_buttons, "glasses"),
        }
        try:
            save_hardware_config(config)
        except Exception as exc:
            QMessageBox.critical(self, "שגיאה", f"שמירת ההגדרות נכשלה:\n{exc}")
            return
        self.config = load_hardware_config()
        QMessageBox.information(self, "נשמר", "הגדרות החומרה נשמרו בהצלחה.")


def main():
    app = QApplication(sys.argv)
    editor = HardwareConfigEditor()
    editor.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

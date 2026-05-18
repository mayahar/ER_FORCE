import copy
import sys
import time

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyleOptionSlider,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.controller import Controller
from core.research_repository import (
    get_current_research_day,
    get_research_participant,
    get_research_participant_ids,
    is_research_enabled,
)
from core.subject_repository import (
    create_or_update_subject_profile,
    create_subject,
    get_all_subject_ids,
    subject_exists,
    update_subject_baseline,
)
from score.eye_features import apply_controller_eye_features

from .eye_tracking_runtime import EyeTrackingRuntime
from .game_runtime import (
    create_voice_session,
    finalize_voice_session,
    is_pid_running,
    start_flightgear_session,
    terminate_session_process,
)
from .results_export import build_result_export_rows, export_result_csv, save_report_once
from .theme import APP_STYLESHEET, BACKGROUND, NEGATIVE, POSITIVE, SURFACE, TEXT


MODALITY_ORDER = ["game", "eye", "voice"]
MODALITY_LABELS = {"game": "משחק", "eye": "עיניים", "voice": "קול"}


def get_score_color(score):
    if score <= 15:
        return "#00ff3c"
    if score <= 35:
        return "#A4FC00"
    if score <= 60:
        return "#ffd700"
    if score <= 80:
        return "#ea8101"
    return "#ab0000"


def fix_hebrew(text):
    return "\n".join(line[::-1] for line in str(text).split("\n"))


EXISTING_USER_MODE = "בדיקת עייפות למשתתף קיים"
NEW_USER_MODE = "הוספת משתתף חדש"
SEX_OPTIONS = {"גבר": "male", "אישה": "female", "אחר": "other"}


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)


def title(text):
    label = QLabel(text)
    label.setObjectName("title")
    label.setAlignment(Qt.AlignCenter)
    return label


def message(text, object_name="subtitle"):
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignCenter)
    return label


def panel(object_name="panel"):
    frame = QFrame()
    frame.setObjectName(object_name)
    frame.setFrameShape(QFrame.StyledPanel)
    return frame


def add_labeled(parent_layout, label_text, widget):
    row_layout = QHBoxLayout()
    
    label = QLabel(label_text)
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    label.setMinimumWidth(90)
    
    # הוספת הוידג'ט קודם ואז הלייבל כדי שויזואלית הלייבל יהיה מימין
    row_layout.addWidget(widget, 1)
    row_layout.addWidget(label)
    parent_layout.addLayout(row_layout)


class SliderTickRuler(QWidget):
    def __init__(self, slider):
        super().__init__()
        self.slider = slider
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedHeight(34)

    def paintEvent(self, event):
        super().paintEvent(event)
        minimum = self.slider.minimum()
        maximum = self.slider.maximum()
        if maximum <= minimum:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor(255, 255, 255, 230))

        option = QStyleOptionSlider()
        self.slider.initStyleOption(option)
        handle_rect = self.slider.style().subControlRect(
            QStyle.CC_Slider,
            option,
            QStyle.SC_SliderHandle,
            self.slider,
        )
        handle_width = max(1, handle_rect.width())
        span = max(0, self.width() - handle_width)

        for value in range(minimum, maximum + 1):
            position = QStyle.sliderPositionFromValue(minimum, maximum, value, span)
            x = round(position + handle_width / 2)
            tick_height = 12 if value in (minimum, maximum) else 9
            painter.drawLine(x, 0, x, tick_height)
            painter.drawText(x - 20, 15, 40, 18, Qt.AlignHCenter | Qt.AlignTop, str(value))


def slider_tick_ruler(slider):
    return SliderTickRuler(slider)


def slider_row(label_text, minimum, maximum, value):
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 5, 0, 15)
    layout.setSpacing(4)

    label = QLabel(f"{label_text}: {value}")
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet("font-size: 15px; font-weight: bold; color: white;")

    slider = QSlider(Qt.Horizontal)
    slider.setRange(minimum, maximum)
    slider.setValue(value)
    
    slider.setTickPosition(QSlider.NoTicks)
    slider.setTickInterval(1)
    
    slider.setStyleSheet("""
        QSlider {
            min-height: 50px;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #444;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #66aaff;
            border: 2px solid white;
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 9px;
        }
    """)
    
    slider.valueChanged.connect(lambda v: label.setText(f"{label_text}: {v}"))

    layout.addWidget(label)
    layout.addWidget(slider)
    layout.addWidget(slider_tick_ruler(slider))
    
    return container, slider


def feature_display_name(feature):
    return str(feature).replace("_", "\n").title()


class BaseScreen(QWidget):
    def __init__(self, app_window):
        super().__init__()
        self.app = app_window
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(32, 26, 32, 26)
        self.root.setSpacing(16)

    def activate(self):
        pass

    def set_error(self, text):
        if hasattr(self, "error_label"):
            self.error_label.setText(text or "")


class EnterIdScreen(BaseScreen):
    def __init__(self, app_window):
        super().__init__(app_window)
        self.mode_group = QButtonGroup(self)
        self.subject_combo = QComboBox()
        self.subject_combo.setLayoutDirection(Qt.RightToLeft)
        
        self.subject_input = QLineEdit()
        self.subject_input.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.subject_input.setLayoutDirection(Qt.RightToLeft)
        
        self.name_input = QLineEdit()
        self.name_input.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.name_input.setLayoutDirection(Qt.RightToLeft)
        
        self.sex_combo = QComboBox()
        self.sex_combo.setLayoutDirection(Qt.RightToLeft)
        
        self.age_input = QSpinBox()
        self.age_input.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.age_input.setLayoutDirection(Qt.RightToLeft)
        
        self.dynamic_panel = panel()
        self.dynamic_layout = QVBoxLayout(self.dynamic_panel)
        self.error_label = message("", "errorText")

        # עיגון ומרכוס של האלמנטים במסך הבית למראה הייטקיסטי ומקצועי שלא נמתח
        self.root.addWidget(title("התחלת מפגש חדש"))
        
        center_wrapper = QHBoxLayout()
        center_wrapper.addStretch()
        self.dynamic_panel.setMinimumWidth(450)
        self.dynamic_panel.setMaximumWidth(550)
        center_wrapper.addWidget(self.dynamic_panel)
        center_wrapper.addStretch()
        
        self.root.addLayout(center_wrapper)
        self.root.addWidget(self.error_label)
        self.root.addStretch()

    def activate(self):
        clear_layout(self.dynamic_layout)
        self.error_label.clear()

        if is_research_enabled():
            self._build_research_mode()
        else:
            self._build_manual_mode()

    def _build_research_mode(self):
        research_day = get_current_research_day()
        participant_ids = get_research_participant_ids()

        self.dynamic_layout.addWidget(message("מתים מעייפות"))
        if not research_day:
            self.dynamic_layout.addWidget(message("הסדנה עוד לא התחילה.", "errorText"))
            return
        if not participant_ids:
            self.dynamic_layout.addWidget(message("לא הוכנסו משתתפים לסדנה, פנה לגף פיזיולוגיה תעופתית.", "errorText"))
            return

        self.subject_combo = QComboBox()
        self.subject_combo.setLayoutDirection(Qt.RightToLeft)
        self.subject_combo.addItems([str(pid) for pid in participant_ids])
        add_labeled(self.dynamic_layout, "מספר אישי", self.subject_combo)
        self.dynamic_layout.addWidget(
            message(
                f"יום הסדנה: {research_day['day_number']} | "
                f"{research_day.get('condition', 'research')}"
            )
        )

        continue_button = QPushButton("המשך")
        continue_button.clicked.connect(lambda: self._continue_research(research_day))
        self.dynamic_layout.addWidget(continue_button, alignment=Qt.AlignLeft)

    def _build_manual_mode(self):
        available_ids = get_all_subject_ids()

        mode_box = QGroupBox("בחר מצב הפעלה")
        mode_box.setAlignment(Qt.AlignRight)
        mode_layout = QHBoxLayout(mode_box)
        
        existing_button = QRadioButton(EXISTING_USER_MODE)
        new_button = QRadioButton(NEW_USER_MODE)
        existing_button.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(existing_button)
        self.mode_group.addButton(new_button)
        
        # מוסיפים קודם את כפתור "חדש" ואז "קיים" כדי שמימין לשמאל "קיים" יופיע ראשון
        mode_layout.addStretch()
        mode_layout.addWidget(new_button)
        mode_layout.addWidget(existing_button)
        self.dynamic_layout.addWidget(mode_box)

        self.subject_input = QLineEdit()
        self.subject_input.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.subject_input.setLayoutDirection(Qt.RightToLeft)
        self.subject_input.setPlaceholderText("אנא הזן מספר אישי")
        add_labeled(self.dynamic_layout, "מספר אישי", self.subject_input)

        self.name_input = QLineEdit()
        self.name_input.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.name_input.setLayoutDirection(Qt.RightToLeft)
        self.name_input.setPlaceholderText("הקלד שם מלא")
        
        self.sex_combo = QComboBox()
        self.sex_combo.setLayoutDirection(Qt.RightToLeft)
        self.sex_combo.addItems(list(SEX_OPTIONS.keys()))
        
        self.age_input = QSpinBox()
        self.age_input.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.age_input.setLayoutDirection(Qt.RightToLeft)
        self.age_input.setRange(1, 120)
        self.age_input.setValue(18)

        profile_box = QGroupBox("פרופיל משתתף חדש")
        profile_box.setAlignment(Qt.AlignRight)
        
        profile_layout = QGridLayout(profile_box)
        
        name_label = QLabel("שם מלא")
        name_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sex_label = QLabel("מין")
        sex_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        age_label = QLabel("גיל")
        age_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        # סידור העמודות ב-Grid: עמודה 1 הלייבל (ימין), עמודה 0 תיבת הקלט (שמאל)
        profile_layout.addWidget(name_label, 0, 1)
        profile_layout.addWidget(self.name_input, 0, 0)
        profile_layout.addWidget(sex_label, 1, 1)
        profile_layout.addWidget(self.sex_combo, 1, 0)
        profile_layout.addWidget(age_label, 2, 1)
        profile_layout.addWidget(self.age_input, 2, 0)
        
        profile_layout.setColumnStretch(0, 1)
        profile_layout.setColumnStretch(1, 0)
        
        name_label = QLabel("שם מלא")
        name_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sex_label = QLabel("מין")
        sex_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        age_label = QLabel("גיל")
        age_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        profile_layout.addWidget(self.name_input, 0, 0)
        profile_layout.addWidget(name_label, 0, 1)
        profile_layout.addWidget(self.sex_combo, 1, 0)
        profile_layout.addWidget(sex_label, 1, 1)
        profile_layout.addWidget(self.age_input, 2, 0)
        profile_layout.addWidget(age_label, 2, 1)
        
        profile_layout.setColumnStretch(0, 1)
        profile_layout.setColumnStretch(1, 0)
        
        profile_box.setVisible(False)
        self.dynamic_layout.addWidget(profile_box)

        def toggle_profile():
            profile_box.setVisible(new_button.isChecked())

        existing_button.toggled.connect(toggle_profile)
        new_button.toggled.connect(toggle_profile)

        continue_button = QPushButton("המשך")
        continue_button.clicked.connect(lambda: self._continue_manual(new_button.isChecked(), available_ids))
        self.dynamic_layout.addWidget(continue_button, alignment=Qt.AlignLeft)

    def _continue_manual(self, is_new_user, available_ids):
        subject_id = self.subject_input.text().strip()
        if not subject_id:
            self.set_error("אנא הזן מספר אישי.")
            return

        if not is_new_user and not subject_exists(subject_id):
            self.set_error(f"הנבדק שמספרו האישי הוא: {subject_id} לא מופיע במערכת, מספרים אישיים זמינים: {', '.join(map(str, available_ids))}")
            return

        if is_new_user:
            if subject_exists(subject_id):
                self.set_error("הנבדק כבר קיים במערכת.")
                return
            if not self.name_input.text().strip():
                self.set_error("אנא הזן שם מלא.")
                return
            try:
                create_subject(
                    subject_id,
                    name=self.name_input.text().strip(),
                    sex=SEX_OPTIONS[self.sex_combo.currentText()],
                    age=self.age_input.value(),
                )
            except (ValueError, TypeError):
                self.set_error("נתונים לא תקינים. אנא בדוק את הקלטים ונסה שוב.")
                return

        if self.app.controller.load_subject(subject_id):
            self.app.state = {
                "screen": "new_user_sleep_gate" if is_new_user else "questionnaire",
                "session_id": subject_id,
                "baseline_capture": is_new_user,
            }
            self.app.result = None
            self.app.navigate(self.app.state["screen"])


class QuestionnaireScreen(BaseScreen):
    def __init__(self, app_window):
        super().__init__(app_window)
        self.error_label = message("", "errorText")
        self.fatigue_slider = None
        self.sleep_last_slider = None
        self.sleep_previous_slider = None
        self.root.addWidget(title("שאלון עייפות"))
        self.form_panel = panel()
        self.form_layout = QVBoxLayout(self.form_panel)
        self.root.addWidget(self.form_panel)
        self.root.addWidget(self.error_label)
        self.root.addStretch()

    def activate(self):
        clear_layout(self.form_layout)
        research_context = self.app.state.get("research_context")
        
        fatigue_row, self.fatigue_slider = slider_row("עד כמה אתה עייף כעת?", 0, 10, 5)
        self.form_layout.addWidget(fatigue_row)

        if research_context:
            self.sleep_last_slider = None
            self.sleep_previous_slider = None
            self.form_layout.addWidget(
                message(
                    f"יום הסדנה {research_context['day_number']}: "
                    f"שעות שינה אתמול={research_context.get('sleep_last')}, "
                    f"שעות שינה שלשום={research_context.get('sleep_previous')}"
                )
            )
        else:
            sleep_last_row, self.sleep_last_slider = slider_row("כמה שעות ישנת אתמול?", 0, 8, 6)
            sleep_previous_row, self.sleep_previous_slider = slider_row("כמה שעות ישנת שלשום?", 0, 8, 6)
            self.form_layout.addWidget(sleep_last_row)
            self.form_layout.addWidget(sleep_previous_row)

        continue_button = QPushButton("המשך")
        continue_button.clicked.connect(self._continue)
        self.form_layout.addWidget(continue_button, alignment=Qt.AlignLeft)

    def _continue(self):
        research_context = self.app.state.get("research_context")
        if research_context:
            sleep_last = research_context.get("sleep_last", 0)
            sleep_previous = research_context.get("sleep_previous", 0)
        else:
            sleep_last = self.sleep_last_slider.value()
            sleep_previous = self.sleep_previous_slider.value()

        questionnaire = {
            "fatigue_self": self.fatigue_slider.value(),
            "sleep_last": sleep_last,
            "sleep_previous": sleep_previous,
        }

        if research_context:
            questionnaire.update(
                {
                    "research_day": research_context["day_number"],
                    "research_condition": research_context["condition"],
                    "study_id": research_context["study_id"],
                }
            )

        self.app.controller.dispatch("QUESTIONNAIRE_DONE", questionnaire)
        self.app.navigate("game")


class NewUserSleepGateScreen(BaseScreen):
    def __init__(self, app_window):
        super().__init__(app_window)
        self.error_label = message("", "errorText")
        self.sleep_last_slider = None
        self.sleep_previous_slider = None
        self.root.addWidget(title("בדיקת הכנה למשתתף חדש"))
        self.form_panel = panel()
        self.form_layout = QVBoxLayout(self.form_panel)
        self.root.addWidget(self.form_panel)
        self.root.addWidget(self.error_label)
        self.root.addStretch()

    def activate(self):
        clear_layout(self.form_layout)
        self.error_label.clear()
        
        sleep_last_row, self.sleep_last_slider = slider_row("כמה שעות ישנת אתמול?", 0, 8, 7)
        sleep_previous_row, self.sleep_previous_slider = slider_row("כמה שעות ישנת שלשום?", 0, 8, 7)
        self.form_layout.addWidget(sleep_last_row)
        self.form_layout.addWidget(sleep_previous_row)
        
        continue_button = QPushButton("המשך")
        continue_button.clicked.connect(self._continue)
        self.form_layout.addWidget(continue_button, alignment=Qt.AlignLeft)


class GameScreen(BaseScreen):
    def __init__(self, app_window):
        super().__init__(app_window)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        
        self.audio_only = QCheckBox("הרצת בדיקת קול בלבד (ללא הפעלת המשחק)")
<<<<<<< HEAD
        self.audio_only.setLayoutDirection(Qt.RightToLeft)
        
=======
        self.calibrate_button = QPushButton("כיול עיניים (Tobii)")
>>>>>>> 525a31ceace7d1b06a9de12f623313514b9cd11f
        self.start_button = QPushButton("התחל משחק")
        self.stop_button = QPushButton("סיים משחק")
        self.calibration_status = message(
            "לפני המשחק: מיקום ראש (5 שניות) → כיול 5 נקודות → תצוגת מבט."
        )
        self.calibration_preview_label = QLabel()
        self.calibration_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.calibration_preview_label.setVisible(False)
        self.status_label = message("המשחק מוכן")
        self.eye_label = message("")
        self.voice_label = message("")
        self.error_label = message("", "errorText")
        self.started_at = None

        self.root.addWidget(title("הפעלת משחק"))
        info_panel = panel()
        info_layout = QVBoxLayout(info_panel)
        info_layout.addWidget(
            message(
                "המשחק יופעל במצב מסך מלא. במהלך הטעינה תופעל הנחיה קולית להשמעת קול כחלק ממדידת העייפות."
            )
        )
        info_layout.addWidget(message(
            "בתחילת ההטסה אף המטוס מוטה מטה, נדרש למשוך את הסטיק באופן מיידי על מנת להמנע מהתרסקות.", "warningText"
            )
        )
        self.root.addWidget(info_panel)
        self.root.addWidget(self.audio_only)
        self.root.addWidget(self.calibration_status)
        self.root.addWidget(self.calibration_preview_label)

        cal_row = QHBoxLayout()
        cal_row.addWidget(self.calibrate_button)
        cal_row.addStretch()
        self.root.addLayout(cal_row)

        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        self.root.addLayout(buttons)
        self.root.addWidget(self.status_label)
        self.root.addWidget(self.eye_label)
        self.root.addWidget(self.voice_label)
        self.root.addWidget(self.error_label)
        self.root.addStretch()

        self.start_button.clicked.connect(self.start_session)
        self.stop_button.clicked.connect(self.stop_session)
        self.calibrate_button.clicked.connect(self.run_calibration)

    def activate(self):
        self.error_label.clear()
        self.app.eye_runtime.reset_calibration()
        self.calibration_preview_label.clear()
        self.calibration_preview_label.setVisible(False)
        connected, err = self.app.eye_runtime.ensure_tracker()
        if connected:
            self.calibration_status.setText(
                f"מחובר: {self.app.eye_runtime.tracker_label}\n"
                "לחץ «כיול עיניים» ואז «התחל משחק»."
            )
        else:
            self.calibration_status.setText(
                f"{err}\nניתן להמשיך בלי מעקב עיניים."
            )
        self._sync_buttons()
        if self.app.fg_pid or self.app.voice_only_running:
            self.timer.start()
        else:
            self.timer.stop()
            self.status_label.setText("Ready")
            self.eye_label.clear()
            self.voice_label.clear()

    def _start_eye_tracking(self) -> bool:
        apply_controller_eye_features(self.app.controller, None)
        started, error = self.app.eye_runtime.start()
        if error:
            self.app.eye_runtime.last_error = error
        return started

    def _stop_eye_tracking(self) -> None:
        _features, error = self.app.eye_runtime.stop(self.app.controller)
        if error:
            self.app.eye_runtime.last_error = error

    def _finish_session(self) -> None:
        self._stop_eye_tracking()
        finalize_voice_session(self.app.controller, self.app.voice_session)
        self.app.voice_session = None
        if self.app.fg_pid:
            terminate_session_process(self.app.fg_pid)
        self.app.fg_pid = 0
        self.app.voice_only_running = False
        self.app.fg_started_at = None
        self.app.result = None
        self.timer.stop()
        self.app.navigate("result")

    def run_calibration(self):
        self.error_label.clear()
        screen = self.window().screen() if self.window() else QGuiApplication.primaryScreen()
        success, message = self.app.eye_runtime.run_calibration(
            parent=self.window(),
            screen=screen,
            controller=self.app.controller,
        )
        if success:
            self.calibration_status.setText(
                f"כיול עבר ✓ ({self.app.eye_runtime.tracker_label})"
            )
            preview_path = self.app.eye_runtime.calibration_preview_path
            if preview_path:
                pixmap = QPixmap(preview_path)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        400,
                        250,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.calibration_preview_label.setPixmap(scaled)
                    self.calibration_preview_label.setVisible(True)
        else:
            self.calibration_status.setText(message)
            self.calibration_preview_label.clear()
            self.calibration_preview_label.setVisible(False)
            self.set_error(message)
        self._sync_buttons()

    def start_session(self):
        self.error_label.clear()
        runtime = self.app.eye_runtime
        if runtime.tracker_connected and not runtime.calibration_passed:
            self.set_error("יש לבצע כיול עיניים לפני תחילת המשחק.")
            return

        self.app.eye_runtime.reset()
        apply_controller_eye_features(self.app.controller, None)
        self._start_eye_tracking()

        if self.audio_only.isChecked():
            try:
                self.app.voice_session = create_voice_session(self.app.controller)
            except Exception as exc:
                self.set_error(f"Failed to start voice session: {exc}")
                return
            self.app.voice_only_running = True
            self.app.fg_started_at = time.time()
            self.timer.start()
            self._sync_buttons()
            return

        pid, error = start_flightgear_session(self.app.controller)
        if error:
            self.set_error(error)
            return

        try:
            self.app.voice_session = create_voice_session(self.app.controller)
        except Exception as exc:
            terminate_session_process(pid)
            self.set_error(f"FlightGear started, but voice session failed: {exc}")
            return

        self.app.fg_pid = pid
        self.app.fg_started_at = time.time()
        self.app.fg_finished_handled = False
        self.timer.start()
        self._sync_buttons()

    def stop_session(self):
        self._finish_session()

    def _tick(self):
        if self.app.voice_session is not None:
            elapsed = time.time() - float(self.app.fg_started_at or time.time())
            try:
                self.app.voice_session.update(elapsed)
            except Exception as exc:
                self.set_error(f"Voice session update failed: {exc}")

        fg_running = is_pid_running(self.app.fg_pid)
        if self.app.fg_pid and not fg_running:
            elapsed = time.time() - float(self.app.fg_started_at or time.time())
            if elapsed < 8.0:
                self._stop_eye_tracking()
                finalize_voice_session(self.app.controller, self.app.voice_session)
                self.app.voice_session = None
                self.app.fg_pid = 0
                self.app.fg_started_at = None
                self.app.voice_only_running = False
                self.timer.stop()
                self.set_error(
                    "FlightGear closed too quickly. Check the FlightGear path and run "
                    "logging_fg_start_ver5.py from a terminal for details."
                )
            else:
                self._finish_session()
                return

        runtime = int(time.time() - self.app.fg_started_at) if self.app.fg_started_at else 0
        mode = "Audio only" if self.app.voice_only_running else "Game running"
        self.status_label.setText(f"{mode} | {runtime} seconds")

        if self.app.eye_runtime.active:
            sample_count = 0
            if self.app.eye_runtime.recorder is not None:
                sample_count = len(self.app.eye_runtime.recorder.get_collected_data())
            self.eye_label.setText(
                f"Eye recording active ({sample_count} samples; timestamps saved in ms)"
            )
        elif self.app.eye_runtime.export_paths:
            paths = self.app.eye_runtime.export_paths
            self.eye_label.setText(
                "Eye data saved in session/eye:\n"
                f"  raw CSV: {paths.get('csv', '')}\n"
                f"  raw JSON: {paths.get('json', '')}\n"
                f"  features: {paths.get('features_json', '')}\n"
                f"  events: {paths.get('events_json', '')}"
            )
        elif self.app.eye_runtime.last_error:
            self.eye_label.setText(f"Eye: {self.app.eye_runtime.last_error}")
        else:
            self.eye_label.clear()

        voice_session = self.app.voice_session
        if voice_session is not None:
            completed_count = len(voice_session.completed_events)
            pending_count = len(voice_session.pending_events)
            prompt = voice_session.current_prompt or "No scheduled prompt yet."
            self.voice_label.setText(
                f"Voice: {prompt}\nCompleted events: {completed_count} | Pending: {pending_count}"
            )
        self._sync_buttons()

    def _sync_buttons(self):
        running = bool(self.app.voice_only_running or is_pid_running(self.app.fg_pid))
        runtime = self.app.eye_runtime
        needs_calibration = runtime.tracker_connected and not runtime.calibration_passed
        self.start_button.setDisabled(running or needs_calibration)
        self.calibrate_button.setDisabled(running)
        self.stop_button.setVisible(running)
        self.audio_only.setDisabled(running)


class ResultsScreen(BaseScreen):
    def __init__(self, app_window):
        super().__init__(app_window)
        self.saved_path = None
        self.root.addWidget(title("תוצאות"))
        self.content = QVBoxLayout()
        self.root.addLayout(self.content)

    def activate(self):
        clear_layout(self.content)

        if self.app.controller.subject is None:
            self.content.addWidget(message("No subject loaded.", "errorText"))
            return

        if self.app.state.get("baseline_capture"):
            self._handle_baseline_capture()
            return

        if not self.app.result:
            self.app.controller.run_multimodal_game()
            self.app.controller.compute_fatigue()
            self.app.result = copy.deepcopy(self.app.controller.get_result())
            research_context = self.app.state.get("research_context")
            if research_context:
                self.app.result["research"] = copy.deepcopy(research_context)

        self._render_result(self.app.result)

    def _handle_baseline_capture(self):
        self.app.controller.run_multimodal_game()
        baseline = copy.deepcopy(self.app.controller.features)
        subject_id = self.app.controller.subject.get("id")
        updated_subject = update_subject_baseline(subject_id, baseline)
        self.app.controller.subject = copy.deepcopy(updated_subject)
        self.app.controller.compute_fatigue()

        baseline_result = copy.deepcopy(self.app.controller.get_result())
        research_context = self.app.state.get("research_context")
        if research_context:
            baseline_result["research"] = copy.deepcopy(research_context)
            save_report_once(
                subject_id,
                export_result_csv(baseline_result),
                result=baseline_result,
                controller=self.app.controller,
            )

        self.app.result = None
        self.app.state["baseline_capture"] = False
        self.app.navigate("baseline_saved")

    def _render_result(self, result):
        if not result:
            self.content.addWidget(message("אין תוצאות להצגה.", "errorText"))
            return

        subject_id = result.get("subject_id", "UNKNOWN")
        score = result.get("score")
        
        # כותרת דוח קבועה
        self.content.addWidget(message(f"דוח תוצאות עבור משתתף: {subject_id}"))

        # יצירת מנגנון לשוניות (Tabs) למניעת גלילה במסך התוצאות
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.RightToLeft)
        
        # 1. לשונית ציון סופי (עם טקסט מוקטן וממורכז לבקשתך)
        tab_score = QWidget()
        score_layout = QVBoxLayout(tab_score)
        score_layout.setContentsMargins(16, 16, 16, 16)
        
        score_panel = panel()
        score_panel_layout = QVBoxLayout(score_panel)
        score_panel_layout.setContentsMargins(24, 24, 24, 28)
        
        score_label = QLabel("ציון עייפות סופי")
        score_label.setAlignment(Qt.AlignCenter)
        score_label.setStyleSheet("font-size: 20px; font-weight: 800; color: #bfd7ff;")
        
        # שינוי לבקשתך: הקטנת הטקסט של הציון מ-132px ל-76px
        score_value = QLabel(f"{score:.2f}" if isinstance(score, (int, float)) else "Unavailable")
        score_value.setAlignment(Qt.AlignCenter)
        
        if isinstance(score, (int, float)):
            score_color = get_score_color(score)
            score_panel.setStyleSheet(f"QFrame#panel {{ border: 3px solid {score_color}; border-radius: 8px; background: {SURFACE}; }}")
            score_value.setStyleSheet(f"color: {score_color}; font-size: 76px; font-weight: 900;")
        else:
            score_value.setStyleSheet("font-size: 54px; font-weight: 900;")
            
        score_panel_layout.addWidget(score_label)
        score_panel_layout.addWidget(score_value)
        score_layout.addWidget(score_panel)

        quality_warning = result.get("quality_warning")
        measurement_warnings = result.get("measurement_warnings") or []
        if quality_warning:
            warning_text = quality_warning
            details = [f"{w.get('label')}: {w.get('detail')}" for w in measurement_warnings if w.get("detail")]
            if details:
                warning_text += "\n" + "\n".join(details)
            score_layout.addWidget(message(warning_text, "warningText"))
            
        score_layout.addStretch()
        self.tabs.addTab(tab_score, "ציון סופי")

        # הפקת נתוני הגרף והטבלה
        export_rows, graph_rows = build_result_export_rows(result)
        ordered_rows = self._ordered_graph_rows(graph_rows)

        if ordered_rows:
            # 2. לשונית גרף אנליזה
            tab_chart = QWidget()
            chart_layout = QVBoxLayout(tab_chart)
            chart_layout.addWidget(self._build_chart(ordered_rows))
            self.tabs.addTab(tab_chart, "גרף מדדים")

            # 3. לשונית טבלת נתונים
            tab_table = QWidget()
            table_layout = QVBoxLayout(tab_table)
            table_layout.addWidget(self._build_table(ordered_rows, export_rows))
            self.tabs.addTab(tab_table, "טבלת מדדים")
        else:
            self.tabs.addTab(message("No graph data available."), "מדדים")

        self.content.addWidget(self.tabs)

        # שמירת דוח אוטומטית ברקע
        csv_text = pd.DataFrame(export_rows).to_csv(index=False)
        path = save_report_once(subject_id, csv_text, result=result, controller=self.app.controller)
        if path:
            self.saved_path = path

        # כפתור ניווט תחתון קבוע
        new_button = QPushButton("התחל מפגש חדש")
        new_button.setMaximumWidth(200)
        new_button.clicked.connect(self._new_session)
        self.content.addWidget(new_button, alignment=Qt.AlignLeft)

    def _ordered_graph_rows(self, graph_rows):
        ordered_rows = []
        for modality in MODALITY_ORDER:
            for row in graph_rows:
                if row.get("modality") == modality:
                    ordered_rows.append(row)
        return ordered_rows

    def _build_chart(self, ordered_rows):
        figure = Figure(figsize=(11, 4.8), facecolor=BACKGROUND)
        axis = figure.add_subplot(111)
        axis.set_facecolor(BACKGROUND)

        x_positions = []
        labels = []
        values = []
        group_boundaries = [0]
        current_x = 0

        for modality in MODALITY_ORDER:
            rows = [row for row in ordered_rows if row.get("modality") == modality]
            for row in rows:
                x_positions.append(current_x)
                labels.append(feature_display_name(row["feature"]))
                values.append(row["value"])
                current_x += 1
            group_boundaries.append(current_x)

        colors = [NEGATIVE if value > 0 else POSITIVE for value in values]

        axis.bar(x_positions, values, color=colors, width=0.6, zorder=3)
        axis.axhline(0, color=TEXT, linewidth=1, zorder=4)
        axis.set_xticks([])

        for x, label in zip(x_positions, labels):
            axis.text(
                x,
                -0.16,
                label,
                ha="center",
                va="top",
                fontsize=10,
                color=TEXT,
                transform=axis.get_xaxis_transform(),
            )

        for i, modality in enumerate(MODALITY_ORDER):
            start = group_boundaries[i]
            end = group_boundaries[i + 1]
            if start == end:
                continue

            mid = (start + end - 1) / 2
            axis.text(
                mid,
                -0.055,
                fix_hebrew(MODALITY_LABELS[modality]),
                ha="center",
                va="top",
                fontsize=12,
                fontweight="bold",
                color=TEXT,
                transform=axis.get_xaxis_transform(),
            )

            if i > 0:
                axis.axvline(start - 0.5, color=TEXT, linewidth=0.8, alpha=0.5, zorder=1)

        axis.set_ylabel("")
        axis.text(
            -0.09,
            0.9,
            fix_hebrew("עלייה ברמת\nהעייפות"),
            transform=axis.transAxes,
            ha="center",
            va="center",
            color=TEXT,
            fontsize=11,
            bbox={"facecolor": "none", "edgecolor": TEXT, "pad": 5},
        )
        axis.text(
            -0.09,
            0.1,
            fix_hebrew("שיפור בביצועים"),
            transform=axis.transAxes,
            ha="center",
            va="center",
            color=TEXT,
            fontsize=11,
            bbox={"facecolor": "none", "edgecolor": TEXT, "pad": 5},
        )
        axis.annotate(
            "",
            xy=(-0.09, 0.82),
            xytext=(-0.09, 0.18),
            xycoords=axis.transAxes,
            arrowprops={"arrowstyle": "<->", "color": TEXT, "lw": 1.5},
        )

        axis.tick_params(axis="y", colors=TEXT)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.spines["bottom"].set_visible(False)
        axis.spines["left"].set_color(TEXT)
        figure.subplots_adjust(left=0.16, right=0.98, bottom=0.32, top=0.96)

        canvas = FigureCanvas(figure)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        canvas.setMinimumHeight(380)
        return canvas

    def _build_table(self, ordered_rows, export_rows):
        row_lookup = {
            (row.get("modality"), row.get("feature")): row
            for row in export_rows
        }
        feature_rows = [
            row_lookup.get((row.get("modality"), row.get("feature")), row)
            for row in ordered_rows
        ]
        headers = [""] + [feature_display_name(row.get("feature")) for row in feature_rows]
        table_rows = [
            ("מצב ערנות", "baseline"),
            ("מצב נוכחי", "current"),
            ("תרומה לציון", "weighted_contribution"),
        ]

        table = QTableWidget(len(table_rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setLayoutDirection(Qt.RightToLeft)
        
        for row_idx, (label, key) in enumerate(table_rows):
            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row_idx, 0, label_item)
            for col_idx, row in enumerate(feature_rows, start=1):
                value = row.get(key)
                if isinstance(value, float):
                    value = f"{value:.3f}"
                elif value is None:
                    value = "-"
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row_idx, col_idx, item)

        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table.setMinimumHeight(180)
        return table

    def _new_session(self):
        self.app.state = {"screen": "enter_id"}
        self.app.result = None
        self.app.navigate("enter_id")


class BaselineSavedScreen(BaseScreen):
    def __init__(self, app_window):
        super().__init__(app_window)
        self.root.addWidget(title("Baseline Saved"))
        self.root.addWidget(
            message(
                "The participant baseline was saved. The next run for this participant "
                "will compare current measurements against this baseline."
            )
        )
        button = QPushButton("Back to Start")
        button.clicked.connect(lambda: self._back())
        self.root.addWidget(button, alignment=Qt.AlignCenter)
        self.root.addStretch()

    def _back(self):
        self.app.state = {"screen": "enter_id"}
        self.app.result = None
        self.app.navigate("enter_id")


class FatigueApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ER Force Fatigue App")
        self.resize(1180, 820)
        self.setStyleSheet(APP_STYLESHEET)

        self.controller = Controller()
        self.state = {"screen": "enter_id"}
        self.result = None
        self.fg_pid = 0
        self.fg_started_at = None
        self.fg_finished_handled = False
        self.voice_only_running = False
        self.voice_session = None
        self.eye_runtime = EyeTrackingRuntime()

        self.stack = QStackedWidget()
        
        # הסרת ה-QScrollArea ממסך התוצאות ומסך הבית למניעת גלילה כפולה ולא נחוצה
        self.setCentralWidget(self.stack)

        self.screens = {
            "enter_id": EnterIdScreen(self),
            "questionnaire": QuestionnaireScreen(self),
            "new_user_sleep_gate": NewUserSleepGateScreen(self),
            "game": GameScreen(self),
            "result": ResultsScreen(self),
            "baseline_saved": BaselineSavedScreen(self),
        }
        for screen in self.screens.values():
            self.stack.addWidget(screen)

        self.navigate("enter_id")

    def navigate(self, screen_name):
        self.state["screen"] = screen_name
        screen = self.screens[screen_name]
        self.stack.setCurrentWidget(screen)
        screen.activate()


def main():
    from eye_tracking_analysis.stdout_safe import install_safe_stdio

    install_safe_stdio()
    app = QApplication(sys.argv)
    app.setApplicationName("ER Force")
    window = FatigueApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
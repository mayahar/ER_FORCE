import copy
import sys
import time

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
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
    QVBoxLayout,
    QWidget,
)

from core.mock_controller import Controller
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
from ui.game_runtime import (
    create_voice_session,
    finalize_voice_session,
    is_pid_running,
    start_flightgear_session,
    terminate_session_process,
)
from ui.results_export import build_result_export_rows, export_result_csv, save_report_once
from ui.theme import APP_STYLESHEET, BACKGROUND, NEGATIVE, POSITIVE, SURFACE, TEXT


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
    label = QLabel(label_text)
    parent_layout.addWidget(label)
    parent_layout.addWidget(widget)


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

    # 1. לייבל לבן עם הערך צמוד לפרומפט
    label = QLabel(f"{label_text}: {value}")
    label.setStyleSheet("font-size: 14px; font-weight: bold; color: white;")

    slider = QSlider(Qt.Horizontal)
    slider.setRange(minimum, maximum)
    slider.setValue(value)
    
    # 2. הגדרות טכניות לשנתות (שיהיו קיימות ברקע)
    slider.setTickPosition(QSlider.NoTicks)
    slider.setTickInterval(1)
    
    # 3. עיצוב מתקדם (CSS) - יצירת שנתות ויזואליות בתוך המסילה
    # השתמשתי ב-repeating-linear-gradient כדי לצייר את הקווים
    slider.setStyleSheet("""
        QSlider {
            min-height: 50px;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #444, stop:1 #444); /* צבע המסילה */
            border-radius: 3px;
            /* יצירת השנתות כקווקוו לבן על המסילה */
            background-image: repeating-linear-gradient(to right, 
                              white, white 1px, 
                              transparent 1px, transparent 10%); 
        }
        QSlider::handle:horizontal {
            background: #38bdf8; /* צבע תכלת מודרני */
            border: 2px solid white;
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 9px;
        }
    """)
    
    # עדכון הטקסט בזמן אמת
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
        self.subject_input = QLineEdit()
        self.name_input = QLineEdit()
        self.sex_combo = QComboBox()
        self.age_input = QSpinBox()
        self.dynamic_panel = panel()
        self.dynamic_layout = QVBoxLayout(self.dynamic_panel)
        self.error_label = message("", "errorText")

        self.root.addWidget(title("התחלת מפגש חדש"))
        self.root.addWidget(self.dynamic_panel)
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
        self.subject_combo.addItems([str(pid) for pid in participant_ids])
        add_labeled(self.dynamic_layout, "Participant ID", self.subject_combo)
        self.dynamic_layout.addWidget(
            message(
                f"יום הסדנה: {research_day['day_number']} | "
                f"{research_day.get('condition', 'research')}"
            )
        )

        continue_button = QPushButton("המשך")
        continue_button.clicked.connect(lambda: self._continue_research(research_day))
        self.dynamic_layout.addWidget(continue_button, alignment=Qt.AlignLeft)

    def _continue_research(self, research_day):
        subject_id = self.subject_combo.currentText()
        participant = get_research_participant(subject_id)
        if not participant:
            self.set_error("המשתתף שנבחר לא נמצא.")
            return

        create_or_update_subject_profile(
            subject_id,
            name=participant.get("name"),
            sex=participant.get("sex", "unknown"),
            age=participant.get("age", 0),
        )

        if self.app.controller.load_subject(subject_id):
            self.app.state = {
                "screen": "questionnaire",
                "session_id": subject_id,
                "research_context": research_day,
                "baseline_capture": research_day["is_baseline_day"],
            }
            self.app.result = None
            self.app.navigate("questionnaire")

    def _build_manual_mode(self):
        available_ids = get_all_subject_ids()

        mode_box = QGroupBox("בחר מצב הפעלה")
        mode_layout = QHBoxLayout(mode_box)
        existing_button = QRadioButton(EXISTING_USER_MODE)
        new_button = QRadioButton(NEW_USER_MODE)
        existing_button.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(existing_button)
        self.mode_group.addButton(new_button)
        mode_layout.addWidget(existing_button)
        mode_layout.addWidget(new_button)
        self.dynamic_layout.addWidget(mode_box)

        self.subject_input = QLineEdit()
        self.subject_input.setPlaceholderText("אנא הזן מספר אישי")
        add_labeled(self.dynamic_layout, "מספר אישי", self.subject_input)

        self.name_input = QLineEdit()
        self.sex_combo = QComboBox()
        self.sex_combo.addItems(list(SEX_OPTIONS.keys()))
        self.age_input = QSpinBox()
        self.age_input.setRange(1, 120)
        self.age_input.setValue(18)

        profile_box = QGroupBox("פרופיל משתתף חדש")
        profile_layout = QGridLayout(profile_box)
        profile_layout.addWidget(QLabel("שם מלא"), 0, 0)
        profile_layout.addWidget(self.name_input, 0, 1)
        profile_layout.addWidget(QLabel("מין"), 1, 0)
        profile_layout.addWidget(self.sex_combo, 1, 1)
        profile_layout.addWidget(QLabel("גיל"), 2, 0)
        profile_layout.addWidget(self.age_input, 2, 1)
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

        # Remove in production the available_ids. The output is currently in place to guide testing with a limited set of mock participants.
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

    def _continue(self):
        if self.sleep_last_slider.value() >= 7 and self.sleep_previous_slider.value() >= 7:
            self.app.state["baseline_capture"] = True
            self.app.navigate("game")
            return
        self.set_error("רמת הערנות שלך לא מתאימה לייצירת משתתף חדש, אנא חזור לאחר שישנת במשך שני לילות רצופים שינה מלאה.")


class GameScreen(BaseScreen):
    def __init__(self, app_window):
        super().__init__(app_window)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        # Remove before production. The audio_only mode is currently in place to allow testing the voice session features without needing to start FlightGear, which can be slow and resource intensive.
        self.audio_only = QCheckBox("הרצת בדיקת קול בלבד (ללא הפעלת המשחק)")
        self.start_button = QPushButton("התחל משחק")
        self.stop_button = QPushButton("סיים משחק")
        self.status_label = message("המשחק מוכן")
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

        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        self.root.addLayout(buttons)
        self.root.addWidget(self.status_label)
        self.root.addWidget(self.voice_label)
        self.root.addWidget(self.error_label)
        self.root.addStretch()

        self.start_button.clicked.connect(self.start_session)
        self.stop_button.clicked.connect(self.stop_session)

    def activate(self):
        self.error_label.clear()
        self._sync_buttons()
        if self.app.fg_pid or self.app.voice_only_running:
            self.timer.start()
        else:
            self.timer.stop()
            self.status_label.setText("Ready")
            self.voice_label.clear()

    def start_session(self):
        self.error_label.clear()
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
        if self.app.fg_pid:
            ok, error = terminate_session_process(self.app.fg_pid)
            if not ok:
                self.set_error(f"Failed to stop session: {error}")
                return

        finalize_voice_session(self.app.controller, self.app.voice_session)
        self.app.voice_session = None
        self.app.fg_pid = 0
        self.app.voice_only_running = False
        self.app.fg_started_at = None
        self.app.result = None
        self.timer.stop()
        self.app.navigate("result")

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
                self.app.fg_pid = 0
                self.app.fg_started_at = None
                self.set_error(
                    "FlightGear closed too quickly. Check the FlightGear path and run "
                    "logging_fg_start_ver5.py from a terminal for details."
                )
            else:
                finalize_voice_session(self.app.controller, self.app.voice_session)
                self.app.voice_session = None
                self.app.fg_pid = 0
                self.app.fg_started_at = None
                self.timer.stop()
                self.app.navigate("result")
                return

        runtime = int(time.time() - self.app.fg_started_at) if self.app.fg_started_at else 0
        mode = "Audio only" if self.app.voice_only_running else "Game running"
        self.status_label.setText(f"{mode} | {runtime} seconds")

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
        self.start_button.setDisabled(running)
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
        self.content.addWidget(message(f"דוח תוצאות עבור משתתף: {subject_id}"))

        score_panel = panel()
        score_panel.setMinimumHeight(260)
        score_layout = QVBoxLayout(score_panel)
        score_layout.setContentsMargins(24, 24, 24, 28)
        score_label = QLabel("ציון עייפות")
        score_label.setAlignment(Qt.AlignCenter)
        score_label.setFont(QFont("Segoe UI", 24, QFont.Bold))
        score_label.setStyleSheet("font-size: 20px; font-weight: 800;")
        score_value = QLabel(f"{score:.2f}" if isinstance(score, (int, float)) else "Unavailable")
        score_value.setAlignment(Qt.AlignCenter)
        score_value.setMinimumHeight(150)
        score_value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        score_value.setFont(QFont("Segoe UI", 132, QFont.Bold))
        if isinstance(score, (int, float)):
            score_color = get_score_color(score)
            score_panel.setStyleSheet(
                f"""
                QFrame#panel {{
                    background: {SURFACE};
                    border: 3px solid {score_color};
                    border-radius: 8px;
                }}
                """
            )
            score_value.setStyleSheet(
                f"""
                QLabel {{
                    color: {score_color};
                    font-size: 132px;
                    font-weight: 900;
                    line-height: 1;
                }}
                """
            )
        else:
            score_value.setStyleSheet(
                """
                QLabel {
                    font-size: 72px;
                    font-weight: 900;
                    line-height: 1;
                }
                """
            )
        score_layout.addWidget(score_label)
        score_layout.addWidget(score_value)
        self.content.addWidget(score_panel)

        export_rows, graph_rows = build_result_export_rows(result)
        ordered_rows = self._ordered_graph_rows(graph_rows)
        if ordered_rows:
            self.content.addWidget(self._build_chart(ordered_rows))
            self.content.addWidget(self._build_table(ordered_rows, export_rows))
        else:
            self.content.addWidget(message("No graph data available."))

        csv_text = pd.DataFrame(export_rows).to_csv(index=False)
        path = save_report_once(subject_id, csv_text, result=result, controller=self.app.controller)
        if path:
            self.saved_path = path

        new_button = QPushButton("התחל מפגש חדש")
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
        figure = Figure(figsize=(11, 5.2), facecolor=BACKGROUND)
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
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        canvas.setMinimumHeight(440)
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
        table.setMinimumHeight(170)
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

        self.stack = QStackedWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.stack)
        self.setCentralWidget(scroll)

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
    app = QApplication(sys.argv)
    app.setApplicationName("ER Force")
    window = FatigueApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

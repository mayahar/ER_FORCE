BACKGROUND = "#001122"
SURFACE = "#002244"
SURFACE_DARK = "#001a33"
BORDER = "#004466"
PRIMARY = "#0066cc"
PRIMARY_HOVER = "#004499"
ACCENT = "#66aaff"
TEXT = "#ffffff"
MUTED = "#bfd7ff"
WARNING_BG = "#332200"
WARNING = "#ffcc66"
ERROR_BG = "#441111"
ERROR_BORDER = "#ff3333"
ERROR_TEXT = "#ff6666"
POSITIVE = "#84cc16"
NEGATIVE = "#ef4444"


APP_STYLESHEET = f"""
QMainWindow, QWidget {{
    background: {BACKGROUND};
    color: {TEXT};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 14px;
}}

QLabel#title {{
    color: {ACCENT};
    font-size: 34px;
    font-weight: 800;
    padding: 12px 0 24px;
}}

QLabel#subtitle {{
    color: {MUTED};
    font-size: 17px;
}}

QFrame#panel {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

QFrame#warningPanel {{
    background: {WARNING_BG};
    border: 1px solid {WARNING};
    border-radius: 8px;
}}

QLabel#warningText {{
    color: {WARNING};
    font-size: 16px;
    font-weight: 700;
}}

QLabel#errorText {{
    color: {ERROR_TEXT};
    font-weight: 700;
}}

QPushButton {{
    background: {PRIMARY};
    color: {TEXT};
    border: 0;
    border-radius: 6px;
    padding: 10px 18px;
    font-weight: 700;
    min-height: 22px;
}}

QPushButton:hover {{
    background: {PRIMARY_HOVER};
}}

QPushButton:disabled {{
    background: #36506a;
    color: #b7c0cc;
}}

QLineEdit, QSpinBox, QComboBox {{
    background: {SURFACE_DARK};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px;
}}

QSlider::groove:horizontal {{
    height: 8px;
    background: {SURFACE_DARK};
    border-radius: 4px;
}}

QSlider::handle:horizontal {{
    width: 18px;
    margin: -6px 0;
    border-radius: 9px;
    background: {ACCENT};
}}

QRadioButton, QCheckBox {{
    spacing: 8px;
}}

QTableWidget {{
    background: {SURFACE_DARK};
    color: {TEXT};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
}}

QHeaderView::section {{
    background: {SURFACE};
    color: {TEXT};
    padding: 7px;
    border: 1px solid {BORDER};
    font-weight: 700;
}}
"""


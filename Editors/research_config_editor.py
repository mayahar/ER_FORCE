import sys
import os
import json
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QCheckBox, 
                             QLineEdit, QDateEdit, QTableWidget, QTableWidgetItem, 
                             QGroupBox, QFormLayout, QSpinBox, QComboBox, QMessageBox)
from PySide6.QtCore import Qt, QDate

class ResearchConfigEditor(QMainWindow):
    def __init__(self, file_path="core/research_config.json"):
        super().__init__()
        self.file_path = os.path.abspath(file_path)
        self.setWindowTitle("🔬 עורך ניסוי ומערך מחקר - PySide6")
        self.resize(900, 650)
        self.setLayoutDirection(Qt.RightToLeft)
        
        self.load_json_data()
        self.init_ui()
        
    def load_json_data(self):
        if not os.path.exists(self.file_path):
            QMessageBox.critical(self, "שגיאה", f"הקובץ {self.file_path} לא נמצא!")
            sys.exit(1)
        with open(self.file_path, "r", encoding="utf-8") as f:
            self.config_data = json.load(f)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.main_layout = QVBoxLayout(main_widget)
        
        # --- חלק 1: הגדרות כלליות ומצב ניסוי ---
        top_group = QGroupBox("⚙️ הגדרות ניסוי כלליות")
        top_layout = QFormLayout(top_group)
        
        self.chk_enabled = QCheckBox("הפעל מצב מחקר (Enabled)")
        self.chk_enabled.setChecked(self.config_data.get("enabled", False))
        top_layout.addRow(self.chk_enabled)
        
        self.txt_study_id = QLineEdit(self.config_data.get("study_id", ""))
        top_layout.addRow("מזהה מחקר (study_id):", self.txt_study_id)
        
        # המרת תאריך מתוך ה-JSON ל-QDate
        date_str = self.config_data.get("start_date", "2026-05-11")
        py_date = QDate.fromString(date_str, "yyyy-MM-dd")
        self.date_start = QDateEdit(py_date)
        self.date_start.setCalendarPopup(True)
        top_layout.addRow("תאריך תחילת המחקר:", self.date_start)
        
        self.txt_output_dir = QLineEdit(self.config_data.get("output_dir", ""))
        top_layout.addRow("תיקיית פלט תוצאות:", self.txt_output_dir)
        
        self.main_layout.addWidget(top_group)
        
        # --- חלק 2: ניהול משתתפים קיימים ---
        self.main_layout.addWidget(QLabel("<h3>👥 משתתפי המחקר הנוכחיים בדאטאבייס</h3>"))
        self.table_participants = QTableWidget()
        self.table_participants.setColumnCount(5)
        self.table_participants.setHorizontalHeaderLabels(["ID", "שם", "מין", "גיל", "פעולות"])
        self.main_layout.addWidget(self.table_participants)
        
        self.populate_participants_table()
        
        # --- חלק 3: טופס הוספת נבדק חדש ---
        add_group = QGroupBox("➕ הוספת נבדק חדש")
        add_layout = QHBoxLayout(add_group)
        
        self.spin_new_id = QSpinBox()
        self.spin_new_id.setRange(1, 99999)
        self.spin_new_id.setValue(103)
        
        self.txt_new_name = QLineEdit("Participant 103")
        
        self.combo_sex = QComboBox()
        self.combo_sex.addItems(["unknown", "male", "female"])
        
        self.spin_age = QSpinBox()
        self.spin_age.setRange(0, 120)
        self.spin_age.setValue(18)
        
        btn_add_participant = QPushButton("הוסף נבדק")
        btn_add_participant.setStyleSheet("background-color: #3498db; color: white;")
        btn_add_participant.clicked.connect(self.add_new_participant)
        
        add_layout.addWidget(QLabel("ID:"))
        add_layout.addWidget(self.spin_new_id)
        add_layout.addWidget(QLabel("שם:"))
        add_layout.addWidget(self.txt_new_name)
        add_layout.addWidget(QLabel("מין:"))
        add_layout.addWidget(self.combo_sex)
        add_layout.addWidget(QLabel("גיל:"))
        add_layout.addWidget(self.spin_age)
        add_layout.addWidget(btn_add_participant)
        
        self.main_layout.addWidget(add_group)
        
        # --- חלק 4: כפתור שמירה סופי ---
        btn_save_json = QPushButton("💾 שמור ועדכן קובץ research_config.json")
        btn_save_json.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; font-size: 14px; padding: 10px;")
        btn_save_json.clicked.connect(self.save_json_to_disk)
        self.main_layout.addWidget(btn_save_json)

    def populate_participants_table(self):
        participants = self.config_data.get("participants", [])
        self.table_participants.setRowCount(len(participants))
        
        for row, p in enumerate(participants):
            self.table_participants.setItem(row, 0, QTableWidgetItem(str(p["id"])))
            self.table_participants.setItem(row, 1, QTableWidgetItem(p["name"]))
            self.table_participants.setItem(row, 2, QTableWidgetItem(p["sex"]))
            self.table_participants.setItem(row, 3, QTableWidgetItem(str(p["age"])))
            
            # כפתור מחיקה לכל שורה
            btn_delete = QPushButton("❌ מחק")
            btn_delete.setStyleSheet("background-color: #e74c3c; color: white; max-width: 60px;")
            btn_delete.clicked.connect(lambda checked=False, r=row: self.delete_participant(r))
            self.table_participants.setCellWidget(row, 4, btn_delete)
            
        self.table_participants.resizeColumnsToContents()

    def delete_participant(self, row_index):
        # הסרה מרשימת הדאטאבייס הפנימית
        self.config_data["participants"].pop(row_index)
        # ריענון הטבלה בממשק
        self.populate_participants_table()

    def add_new_participant(self):
        new_id = self.spin_new_id.value()
        new_name = self.txt_new_name.text()
        new_sex = self.combo_sex.currentText()
        new_age = self.spin_age.value()
        
        # בדיקה שה-ID לא קיים כבר במערכת
        if any(p["id"] == new_id for p in self.config_data["participants"]):
            QMessageBox.warning(self, "שגיאה", "מזהה נבדק (ID) זה כבר קיים במערכת!")
            return
            
        self.config_data["participants"].append({
            "id": new_id,
            "name": new_name,
            "sex": new_sex,
            "age": new_age
        })
        
        self.populate_participants_table()
        # קידום אוטומטי של ה-ID הבא לנוחיות המשתמש
        self.spin_new_id.setValue(new_id + 1)
        self.txt_new_name.setText(f"Participant {new_id + 1}")

    def save_json_to_disk(self):
        # עדכון השדות הראשיים מהפקדים לפני השמירה
        self.config_data["enabled"] = self.chk_enabled.isChecked()
        self.config_data["study_id"] = self.txt_study_id.text()
        self.config_data["start_date"] = self.date_start.date().toString("yyyy-MM-dd")
        self.config_data["output_dir"] = self.txt_output_dir.text()
        
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "הצלחה", "הקובץ research_config.json עודכן ונשמר בהצלחה!")
        except Exception as e:
            QMessageBox.critical(self, "שגיאה", f"שמירת הקובץ נכשלה:\n{str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = ResearchConfigEditor()
    editor.show()
    sys.exit(app.exec())
import sys
import os
import json
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTableWidget, QTableWidgetItem, 
                             QPushButton, QLabel, QDoubleSpinBox, QMessageBox,
                             QGroupBox)
from PySide6.QtCore import Qt

class FatigueFeaturesEditor(QMainWindow):
    def __init__(self, file_path="score/fatigue_features.json"):
        super().__init__()
        self.file_path = os.path.abspath(file_path)
        self.setWindowTitle("🛠️ עורך הגדרות משקלים ומאפייני עייפות (JSON) - PySide6")
        self.resize(1050, 720)
        self.setLayoutDirection(Qt.RightToLeft)
        
        self.load_json_data()
        self.init_ui()
        
    def load_json_data(self):
        """טעינה ישירה, נקייה ובטוחה מקובץ ה-JSON"""
        if not os.path.exists(self.file_path):
            QMessageBox.critical(self, "שגיאה", f"הקובץ {self.file_path} לא נמצא!\nוודא שהעורך ממוקם באותה תיקייה איתו.")
            sys.exit(1)
            
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                self.config_data = json.load(f)
            
            self.features = self.config_data["FEATURES"]
            self.modality_weights = self.config_data["MODALITY_WEIGHTS"]
        except Exception as e:
            QMessageBox.critical(self, "שגיאת טעינה", f"קובץ ה-JSON פגום או לא תקין:\n{str(e)}")
            sys.exit(1)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # --- חלק 1: משקלים גלובליים ---
        modality_group = QGroupBox("🌐 משקלים גלובליים למודליטיז (Modality Aggregation Weights)")
        modality_layout = QHBoxLayout(modality_group)
        
        self.modality_inputs = {}
        for modality, weight in self.modality_weights.items():
            v_box = QVBoxLayout()
            v_box.addWidget(QLabel(f"משקל {modality}:"))
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 2.0)
            spin.setSingleStep(0.01)
            spin.setDecimals(3)
            spin.setValue(weight)
            modality_layout.addLayout(v_box)
            self.modality_inputs[modality] = spin
            
        main_layout.addWidget(modality_group)
        
        # --- חלק 2: טבלת המאפיינים ---
        main_layout.addWidget(QLabel("<h3>📊 עריכת מדדי מאפיינים (Features Metrics)</h3>"))
        
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "שם המאפיין", "מודליטי", "משקל (Weight)", 
            "כיוון (Direction)", "שינוי צפוי", "טווח חוקי (Min, Max)"
        ])
        self.table.setRowCount(len(self.features))
        
        self.feature_widgets = {}
        
        for row, (f_name, cfg) in enumerate(self.features.items()):
            self.table.setItem(row, 0, QTableWidgetItem(f_name))
            self.table.setItem(row, 1, QTableWidgetItem(cfg["modality"]))
            
            # משקל
            spin_weight = QDoubleSpinBox()
            spin_weight.setRange(0.0, 2.0)
            spin_weight.setSingleStep(0.01)
            spin_weight.setValue(float(cfg["weight"]))
            self.table.setCellWidget(row, 2, spin_weight)
            
            # כיוון
            spin_dir = QDoubleSpinBox()
            spin_dir.setRange(-1, 1)
            spin_dir.setSingleStep(2)
            spin_dir.setDecimals(0)
            spin_dir.setValue(int(cfg["direction"]))
            self.table.setCellWidget(row, 3, spin_dir)
            
            # שינוי צפוי
            spin_change = QDoubleSpinBox()
            spin_change.setRange(0.0, 5000.0)
            spin_change.setDecimals(3)
            spin_change.setSingleStep(0.01)
            spin_change.setValue(float(cfg["expected_change"]))
            self.table.setCellWidget(row, 4, spin_change)
            
            # טווחים
            range_widget = QWidget()
            range_layout = QHBoxLayout(range_widget)
            range_layout.setContentsMargins(0, 0, 0, 0)
            
            min_r, max_r = cfg["MEASUREMENT_VALID_RANGES"]
            spin_min = QDoubleSpinBox()
            spin_min.setRange(-99999.0, 99999.0)
            spin_min.setValue(float(min_r))
            
            spin_max = QDoubleSpinBox()
            spin_max.setRange(-99999.0, 99999.0)
            spin_max.setValue(float(max_r))
            
            range_layout.addWidget(QLabel("מיו:"))
            range_layout.addWidget(spin_min)
            range_layout.addWidget(QLabel("מקס:"))
            range_layout.addWidget(spin_max)
            self.table.setCellWidget(row, 5, range_widget)
            
            self.feature_widgets[f_name] = {
                "weight": spin_weight,
                "direction": spin_dir,
                "expected_change": spin_change,
                "min": spin_min,
                "max": spin_max
            }
            
        self.table.resizeColumnsToContents()
        main_layout.addWidget(self.table)
        
        # --- חלק 3: כפתור שמירה ---
        btn_save = QPushButton("💾 שמור ועדכן שינויים ישירות בקובץ fatigue_features.json")
        btn_save.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; font-size: 14px; padding: 12px;")
        btn_save.clicked.connect(self.save_to_file)
        main_layout.addWidget(btn_save)

    def save_to_file(self):
        """עדכון השדות הרלוונטיים בלבד בתוך ה-JSON המקורי ושמירתו מחדש"""
        try:
            # 1. עדכון FEATURES מתוך הממשק (מבלי לפגוע בשדות אחרים כמו std או scoring)
            for f_name, widgets in self.feature_widgets.items():
                if f_name in self.features:
                    self.features[f_name]["weight"] = round(widgets["weight"].value(), 2)
                    self.features[f_name]["direction"] = int(widgets["direction"].value())
                    self.features[f_name]["expected_change"] = round(widgets["expected_change"].value(), 3)
                    self.features[f_name]["MEASUREMENT_VALID_RANGES"] = [
                        round(widgets["min"].value(), 2), 
                        round(widgets["max"].value(), 2)
                    ]
            
            # 2. עדכון MODALITY_WEIGHTS מתוך הממשק
            for modality, spin in self.modality_inputs.items():
                if modality in self.modality_weights:
                    self.modality_weights[modality] = round(spin.value(), 3)
            
            # 3. שמירה פיזית של כל מבנה הנתונים השלם לקובץ ה-JSON
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
                
            QMessageBox.information(self, "הצלחה", "הקובץ fatigue_features.json עודכן ונשמר בהצלחה בבטחה מלאה!")
            
            # טעינה מחדש של הנתונים כדי לשמור על סנכרון הממשק
            self.load_json_data()
            
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בשמירה", f"שמירת הקובץ נכשלה:\n{str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = FatigueFeaturesEditor()
    editor.show()
    sys.exit(app.exec())
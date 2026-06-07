import json
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def _read_only_item(text):
    item = QTableWidgetItem(str(text))
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


class NullableNumberEditor(QWidget):
    def __init__(self, value=None, label="פעיל"):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.enabled = QCheckBox(label)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(0.0, 999999.0)
        self.spin.setDecimals(6)
        self.spin.setSingleStep(0.01)

        has_value = value is not None
        self.enabled.setChecked(has_value)
        self.spin.setEnabled(has_value)
        if has_value:
            self.spin.setValue(float(value))

        self.enabled.toggled.connect(self.spin.setEnabled)
        layout.addWidget(self.enabled)
        layout.addWidget(self.spin)

    def value(self):
        if not self.enabled.isChecked():
            return None
        return round(self.spin.value(), 6)


class StdEditor(QWidget):
    def __init__(self, std_value):
        super().__init__()
        self.is_gendered = isinstance(std_value, dict)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        if self.is_gendered:
            self.male = NullableNumberEditor(std_value.get("male"), "זכר")
            self.female = NullableNumberEditor(std_value.get("female"), "נקבה")
            layout.addWidget(self.male)
            layout.addWidget(self.female)
        else:
            self.scalar = NullableNumberEditor(std_value, "סטיית תקן")
            layout.addWidget(self.scalar)

    def value(self):
        if self.is_gendered:
            return {
                "male": self.male.value(),
                "female": self.female.value(),
            }
        return self.scalar.value()


class FatigueFeaturesEditor(QMainWindow):
    def __init__(self, file_path="score/fatigue_features.json"):
        super().__init__()
        self.file_path = os.path.abspath(file_path)
        self.setWindowTitle("עורך משקלים ומאפייני עייפות")
        self.resize(1220, 760)
        self.setLayoutDirection(Qt.RightToLeft)

        self.load_json_data()
        self.init_ui()

    def load_json_data(self):
        if not os.path.exists(self.file_path):
            QMessageBox.critical(
                self,
                "שגיאה",
                f"הקובץ לא נמצא:\n{self.file_path}",
            )
            sys.exit(1)

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                self.config_data = json.load(f)

            self.features = self.config_data["FEATURES"]
            self.modality_weights = self.config_data["MODALITY_WEIGHTS"]
        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאת טעינה",
                f"קובץ ה-JSON פגום או לא תקין:\n{exc}",
            )
            sys.exit(1)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        modality_group = QGroupBox("משקלי מודולים")
        modality_layout = QHBoxLayout(modality_group)
        modality_layout.setSpacing(16)

        self.modality_inputs = {}
        for modality, weight in self.modality_weights.items():
            box = QVBoxLayout()
            box.addWidget(QLabel(f"משקל {modality}:"))

            spin = QDoubleSpinBox()
            spin.setRange(0.0, 2.0)
            spin.setSingleStep(0.01)
            spin.setDecimals(3)
            spin.setValue(float(weight))
            box.addWidget(spin)

            modality_layout.addLayout(box)
            self.modality_inputs[modality] = spin

        main_layout.addWidget(modality_group)

        title = QLabel("<h3>עריכת פיצ׳רים</h3>")
        main_layout.addWidget(title)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            [
                "שם הפיצ׳ר",
                "מודול",
                "משקל",
                "כיוון",
                "שינוי צפוי",
                "סטיית תקן",
                "טווח חוקי",
            ]
        )
        self.table.setRowCount(len(self.features))
        self.table.setLayoutDirection(Qt.RightToLeft)
        self.table.verticalHeader().setVisible(False)

        self.feature_widgets = {}
        for row, (feature_name, cfg) in enumerate(self.features.items()):
            self.table.setItem(row, 0, _read_only_item(feature_name))
            self.table.setItem(row, 1, _read_only_item(cfg.get("modality", "")))

            spin_weight = QDoubleSpinBox()
            spin_weight.setRange(0.0, 2.0)
            spin_weight.setSingleStep(0.01)
            spin_weight.setDecimals(3)
            spin_weight.setValue(float(cfg.get("weight", 0.0)))
            self.table.setCellWidget(row, 2, spin_weight)

            spin_direction = QDoubleSpinBox()
            spin_direction.setRange(-1, 1)
            spin_direction.setSingleStep(2)
            spin_direction.setDecimals(0)
            spin_direction.setValue(int(cfg.get("direction", 1)))
            self.table.setCellWidget(row, 3, spin_direction)

            spin_expected_change = QDoubleSpinBox()
            spin_expected_change.setRange(0.0, 5000.0)
            spin_expected_change.setDecimals(6)
            spin_expected_change.setSingleStep(0.01)
            spin_expected_change.setValue(float(cfg.get("expected_change", 0.0)))
            self.table.setCellWidget(row, 4, spin_expected_change)

            std_editor = StdEditor(cfg.get("std"))
            self.table.setCellWidget(row, 5, std_editor)

            range_widget = QWidget()
            range_layout = QHBoxLayout(range_widget)
            range_layout.setContentsMargins(0, 0, 0, 0)
            range_layout.setSpacing(6)

            valid_range = cfg.get("MEASUREMENT_VALID_RANGES") or [0.0, 0.0]
            min_range, max_range = valid_range

            spin_min = QDoubleSpinBox()
            spin_min.setRange(-999999.0, 999999.0)
            spin_min.setDecimals(3)
            spin_min.setValue(float(min_range))

            spin_max = QDoubleSpinBox()
            spin_max.setRange(-999999.0, 999999.0)
            spin_max.setDecimals(3)
            spin_max.setValue(float(max_range))

            range_layout.addWidget(QLabel("מינ׳:"))
            range_layout.addWidget(spin_min)
            range_layout.addWidget(QLabel("מקס׳:"))
            range_layout.addWidget(spin_max)
            self.table.setCellWidget(row, 6, range_widget)

            self.feature_widgets[feature_name] = {
                "weight": spin_weight,
                "direction": spin_direction,
                "expected_change": spin_expected_change,
                "std": std_editor,
                "min": spin_min,
                "max": spin_max,
            }

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.resizeRowsToContents()
        main_layout.addWidget(self.table)

        btn_save = QPushButton("שמור ועדכן את fatigue_features.json")
        btn_save.setStyleSheet(
            "background-color: #2ecc71; color: white; font-weight: bold; "
            "font-size: 14px; padding: 12px;"
        )
        btn_save.clicked.connect(self.save_to_file)
        main_layout.addWidget(btn_save)

    def save_to_file(self):
        try:
            for feature_name, widgets in self.feature_widgets.items():
                if feature_name not in self.features:
                    continue

                min_value = widgets["min"].value()
                max_value = widgets["max"].value()
                if min_value >= max_value:
                    raise ValueError(
                        f"טווח לא תקין עבור {feature_name}: מינימום חייב להיות קטן ממקסימום"
                    )

                self.features[feature_name]["weight"] = round(
                    widgets["weight"].value(),
                    3,
                )
                self.features[feature_name]["direction"] = int(
                    widgets["direction"].value()
                )
                self.features[feature_name]["expected_change"] = round(
                    widgets["expected_change"].value(),
                    6,
                )
                self.features[feature_name]["std"] = widgets["std"].value()
                self.features[feature_name]["MEASUREMENT_VALID_RANGES"] = [
                    round(min_value, 3),
                    round(max_value, 3),
                ]

            for modality, spin in self.modality_inputs.items():
                if modality in self.modality_weights:
                    self.modality_weights[modality] = round(spin.value(), 3)

            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(
                self,
                "הצלחה",
                "הקובץ fatigue_features.json עודכן ונשמר בהצלחה.",
            )
            self.load_json_data()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאה בשמירה",
                f"שמירת הקובץ נכשלה:\n{exc}",
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = FatigueFeaturesEditor()
    editor.show()
    sys.exit(app.exec())

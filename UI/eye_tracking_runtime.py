"""Eye tracking session helpers for Tobii Pro Glasses 3 via REST API."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
import requests

import numpy as np

# שומרים על אותם מייבאים של האנלייזר הקיים שלך
from eye_tracking_analysis.eye_movement_analyzer import EyeMovementAnalyzer
from score.eye_features import apply_controller_eye_features

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RECORDINGS_DIR = REPO_ROOT / "eye_tracking_analysis" / "recordings"

SKIP_EYE_CALIBRATION = False
GLASSES_IP = "TG03B-0123456789.local"

class EyeTrackingRuntime:
    def __init__(self):
        self.analyzer: EyeMovementAnalyzer | None = None
        self.active = False
        self.last_error = ""
        self.export_paths: dict[str, str] | None = None
        self.raw_sample_count = 0
        self.tracker_connected = False
        self.tracker_label = "Tobii Pro Glasses 3"
        self.calibration_passed = False
        self.calibration_message = ""
        self.calibration_preview_path = None
        
        # משתנה לשמירת מזהה ההקלטה הנוכחית מהמשקפיים
        self.current_recording_uuid = None

    def ensure_tracker(self) -> bool:
        """בודק האם המשקפיים זמינים ברשת"""
        try:
            response = requests.get(f"http://{GLASSES_IP}/rest/system/status", timeout=2.0)
            if response.status_code == 200:
                self.tracker_connected = True
                self.last_error = ""
                return True
        except Exception:
            pass
        
        self.tracker_connected = False
        self.last_error = "לא נמצאו משקפי Tobii ברשת. ודא חיבור ל-Wi-Fi של המשקפיים."
        return False

    def start(self, camera_index: int = 0, subject_id: str | None = None) -> tuple[bool, str]:
        """מפעיל את ההקלטה במשקפיים באופן אלחוטי בתחילת המשחק"""
        if not self.ensure_tracker():
            return False, self.last_error

        try:
            # יצירת הקלטה חדשה וקבלת ה-UUID שלה
            res = requests.post(f"http://{GLASSES_IP}/rest/recorder!start", json=[], timeout=3.0)
            if res.status_code == 200:
                # ה-API מחזיר את ה-UUID של ההקלטה שהחלה
                self.current_recording_uuid = res.json()
                self.active = True
                self.last_error = ""
                return True, ""
            else:
                return False, f"שגיאת שרת משקפיים: {res.status_code}"
        except Exception as e:
            self.active = False
            self.last_error = f"נכשלה הפעלת הקלטה: {str(e)}"
            return False, self.last_error

    def stop(self, controller: Any | None = None) -> tuple[dict[str, Any] | None, str]:
        """עוצר את ההקלטה, מושך את ה-RAW Data מיידית דרך הרשת ומנתח עייפות"""
        if not self.active or not self.current_recording_uuid:
            return None, "אין הקלטה פעילה לעצירה"

        try:
            # 1. עצירת ההקלטה במשקפיים
            requests.post(f"http://{GLASSES_IP}/rest/recorder!stop", json=[], timeout=3.0)
            self.active = False
            
            # 2. משיכה מיידית של קובץ ה-Gaze הגולמי (RAW) מהמשקפיים דרך הרשת
            # המשקפיים חושפים את הקבצים בפורמת JSON Lines (שורה לכל דגימה)
            gaze_url = f"http://{GLASSES_IP}/projects/default/recordings/{self.current_recording_uuid}/gaze"
            gaze_res = requests.get(gaze_url, timeout=10.0)
            
            if gaze_res.status_code != 200:
                return None, f"נכשלה משיכת נתונים גולמיים מהמשקפיים. קוד: {gaze_res.status_code}"

            # 3. פארסינג של ה-RAW Data לתוך מערכים שהאנלייזר הקיים שלך מכיר
            timestamps = []
            gaze_left_x, gaze_left_y = [], []
            gaze_right_x, gaze_right_y = [], []
            pupil_left, pupil_right = [] , []

            for line in gaze_res.text.splitlines():
                if not line.strip():
                    continue
                packet = json.loads(line)
                
                # סינון חבילות מסוג gaze בלבד
                if packet.get("type") == "gaze" and "data" in packet:
                    data = packet["data"]
                    # המרת זמן לשניות (המשקפיים מספקים במיקרו-שניות)
                    timestamps.append(packet["timestamp"] / 1000000.0)
                    
                    # קריאת נתוני המבט הדו-מימדיים (Gaze2D)
                    g2d = data.get("gaze2d", [np.nan, np.nan])
                    gaze_left_x.append(g2d[0])
                    gaze_left_y.append(g2d[1])
                    
                    # במשקפיים המבט הוא משולב או כללי, נשכפל לימין ושמאל לצורך תאימות לאנלייזר הקיים שלך
                    gaze_right_x.append(g2d[0])
                    gaze_right_y.append(g2d[1])
                    
                    # קוטר אישון (Pupil Diameter)
                    pupil_left.append(data.get("pd", np.nan))
                    pupil_right.append(data.get("pd", np.nan))

            self.raw_sample_count = len(timestamps)
            if self.raw_sample_count == 0:
                return {}, "לא נאספו דגימות תנועות עיניים במהלך המשחק"

            # 4. התאמת המבנה לפורמט של ה-EyeMovementAnalyzer המקורי שלך
            mock_session_data = {
                "timestamp": np.array(timestamps),
                "left_gaze_point_on_display_area_x": np.array(gaze_left_x),
                "left_gaze_point_on_display_area_y": np.array(gaze_left_y),
                "right_gaze_point_on_display_area_x": np.array(gaze_right_x),
                "right_gaze_point_on_display_area_y": np.array(gaze_right_y),
                "left_pupil_diameter": np.array(pupil_left),
                "right_pupil_diameter": np.array(pupil_right),
            }

            # 5. הרצת האנליזה הקיימת שלך למדדי עייפות
            self.analyzer = EyeMovementAnalyzer(mock_session_data)
            features, fixations, saccades, metrics, err = self._analyze_extracted_data()
            
            if err:
                return None, err

            # 6. עדכון הקונטרולר הקיים
            if controller is not None:
                apply_controller_eye_features(controller, features)

            return features, ""

        except Exception as e:
            return None, f"שגיאה בעיבוד נתוני המשקפיים בסיום המשחק: {str(e)}"

    def _analyze_extracted_data(self) -> tuple[dict[str, Any] | None, Any, Any, Any, str]:
        """מריץ את ה-Pipeline הקיים של האנלייזר שלך (העתק מדויק מהקוד המקורי)"""
        try:
            fixations = self.analyzer.get_fixations()
            saccades = self.analyzer.get_saccades()
            metrics = self.analyzer.get_metrics()
        except Exception as e:
            return None, None, None, None, f"אנליזת תנועות עיניים נכשלה: {str(e)}"

        timestamps = self.analyzer.data.get("timestamp", np.array([]))
        fixation_duration = float(np.sum(fixations["duration"])) if fixations.size > 0 else 0.0
        fixation_count = float(fixations.size)
        saccade_count = float(saccades.size)
        total_duration = float(timestamps[-1] - timestamps[0]) if timestamps.size > 1 else 0.0

        features = {
            "fixation_duration": float(fixation_duration),
            "fixation_count": float(fixation_count),
            "saccade_count": float(saccade_count),
            "analysis": {
                "total_duration": self._metric_value(metrics, "total_duration", default=total_duration),
                "fixations_per_minute": float(fixation_count),
                "saccades_per_minute": float(saccade_count),
                "fixation_duration_per_minute": float(fixation_duration),
                "mean_fixation_duration": self._metric_value(metrics, "mean_fixation_duration"),
                "mean_saccade_velocity": self._metric_value(metrics, "mean_saccade_velocity"),
            },
        }
        return features, fixations, saccades, metrics, ""

    @staticmethod
    def _metric_value(metrics, *names, default=0.0) -> float:
        for name in names:
            if hasattr(metrics, name):
                try:
                    value = float(getattr(metrics, name))
                except (TypeError, ValueError):
                    continue
                if np.isfinite(value):
                    return value
        return default

    def reset(self) -> None:
        self.active = False
        self.current_recording_uuid = None
        self.raw_sample_count = 0
        self.last_error = ""

    def reset_calibration(self) -> None:
        self.calibration_passed = False
        self.calibration_message = ""